"""Opt-in POSIX/WSL private annotation source/metadata storage.

Trusted Core/local-maintenance callers only; no application worker is enabled.
The optional explicit local CLI and internal processor are separate adapters.
The caller supplies an existing host-owned private root.
Files are bounded plaintext, not encrypted or tamper-proof against their owner.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import stat
from threading import RLock
from typing import Callable

from pipeline.document_intake import DocumentAnnotationResult, PreparedDocument, prepare_document_text
from pipeline.document_job_results import (
    MAX_RESULT_CANDIDATES, AnnotationJobResultError, decode_annotation_job_result,
    encode_annotation_job_result, validate_chunk_checkpoint,
)
from pipeline.document_jobs import (
    AnnotationJobMetadata, AnnotationJobPolicyError, annotation_job_accessible,
    recover_annotation_job, resume_annotation_job,
)
from pipeline.document_job_status import AnnotationJobProgress, AnnotationJobProgressError
from pipeline.document_job_runtime import (
    AnnotationJobRuntimeError, AnnotationRuntimeEvidence, validate_runtime_fingerprint,
)

try:
    import fcntl
except ImportError:  # Windows remains unavailable pending its own ACL/handle gate.
    fcntl = None


JOB_ID_RE = re.compile(r"AJ-[0-9a-f]{32}\Z")
MAX_JOB_RECORD_BYTES = 4 * 1024 * 1024
MAX_JOB_COUNT = 32
MAX_STORE_BYTES = 64 * 1024 * 1024
_LOCK = ".annotation-jobs.owner.lock"
STORAGE_VERSION = 2
RUNTIME_STORAGE_VERSION = 3


class AnnotationJobStoreError(ValueError):
    """Closed, content-free persistence failure."""


@dataclass(frozen=True)
class AnnotationJobStatus:
    job_id: str
    metadata: AnnotationJobMetadata


@dataclass(frozen=True)
class AnnotationJobAttempt:
    """Process-local state binding, never provider authorization or stop proof."""
    job_id: str
    owner_epoch: str
    attempt_id: str


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise AnnotationJobStoreError("job record is invalid")
        result[key] = value
    return result


def _encoded(value: object) -> bytes:
    try:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise AnnotationJobStoreError("job record is invalid") from None
    if len(data) > MAX_JOB_RECORD_BYTES:
        raise AnnotationJobStoreError("job record exceeds capacity")
    return data


def _prepared_digest(document: PreparedDocument) -> str:
    return sha256(_encoded(asdict(document))).hexdigest()


class AnnotationJobStore:
    """One lifetime owner, atomic per-job records, fixed retention.

    Directory-relative no-follow operations protect fixed names. This assumes
    trusted same-user filesystem ownership, not hostile-host isolation. Expiry
    denies returning source; validation/recovery may read the private record.
    Cleanup is explicit in this foundation, not a background retention service.
    """

    def __init__(self, root: Path | str, *, clock: Callable[[], datetime] | None = None):
        if os.name != "posix" or fcntl is None or not hasattr(os, "O_NOFOLLOW"):
            raise AnnotationJobStoreError("private job storage is unsupported on this host")
        self._root = Path(os.path.abspath(root))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._thread_lock = RLock()
        self._epoch = secrets.token_hex(32)
        self._pid = os.getpid()
        self._directory = None
        self._owner = None
        self._closed = True
        try:
            for parent in (self._root, *self._root.parents):
                if stat.S_ISLNK(parent.lstat().st_mode):
                    raise AnnotationJobStoreError("private job root is invalid")
            self._directory = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            details = os.fstat(self._directory)
            if details.st_uid != os.getuid() or details.st_mode & 0o077:
                raise AnnotationJobStoreError("private job root must be owner-only")
            self._root_identity = (details.st_dev, details.st_ino)
            self._owner = self._open(_LOCK, os.O_RDWR | os.O_CREAT)
            fcntl.flock(self._owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._closed = False
            # Only an exclusive later owner may fence unfinished intent.
            self._recover()
            self.cleanup_expired()
        except (OSError, ValueError, TypeError):
            self.close()
            raise AnnotationJobStoreError("private job store could not be opened") from None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self) -> None:
        with self._thread_lock:
            self._closed = True
            for attribute in ("_owner", "_directory"):
                descriptor = getattr(self, attribute, None)
                if descriptor is not None:
                    os.close(descriptor)
                    setattr(self, attribute, None)

    def _open(self, name: str, flags: int) -> int:
        descriptor = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK,
                             0o600, dir_fd=self._directory)
        try:
            details = os.fstat(descriptor)
            if (not stat.S_ISREG(details.st_mode) or details.st_nlink != 1
                    or details.st_uid != os.getuid() or details.st_mode & 0o077):
                raise AnnotationJobStoreError("private job file is invalid")
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    @contextmanager
    def _guard(self):
        with self._thread_lock:
            try:
                if self._closed or self._pid != os.getpid():
                    raise AnnotationJobStoreError("private job owner is inactive")
                details = self._root.lstat()
                if ((details.st_dev, details.st_ino) != self._root_identity
                        or not stat.S_ISDIR(details.st_mode) or details.st_mode & 0o077
                        or details.st_uid != os.getuid()):
                    raise AnnotationJobStoreError("private job root changed")
                held = os.fstat(self._owner)
                named = os.stat(_LOCK, dir_fd=self._directory, follow_symlinks=False)
                if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
                    raise AnnotationJobStoreError("private job owner changed")
                yield
            except (OSError, AnnotationJobPolicyError, AnnotationJobResultError,
                    AnnotationJobProgressError, AnnotationJobRuntimeError, UnicodeError, RecursionError):
                raise AnnotationJobStoreError("private job operation failed safely") from None

    @staticmethod
    def _name(job_id: str) -> str:
        if not isinstance(job_id, str) or JOB_ID_RE.fullmatch(job_id) is None:
            raise AnnotationJobStoreError("job identifier is invalid")
        return job_id + ".json"

    def _records(self) -> list[str]:
        entries = os.listdir(self._directory)
        # A crash may leave a private replacement whose completion is unknown.
        # Do not guess whether to replay/promote/delete it in this foundation.
        if any(name.startswith(".annotation-job-") and name.endswith(".pending") for name in entries):
            raise AnnotationJobStoreError("job replacement requires explicit recovery")
        names = sorted(name for name in entries
                       if name.startswith("AJ-") and name.endswith(".json"))
        if len(names) > MAX_JOB_COUNT:
            raise AnnotationJobStoreError("job store exceeds capacity")
        size = 0
        for name in names:
            self._name(name[:-5])
            descriptor = self._open(name, os.O_RDONLY)
            try:
                record_size = os.fstat(descriptor).st_size
                if record_size > MAX_JOB_RECORD_BYTES:
                    raise AnnotationJobStoreError("job record exceeds capacity")
                size += record_size
            finally:
                os.close(descriptor)
        if size > MAX_STORE_BYTES:
            raise AnnotationJobStoreError("job store exceeds capacity")
        return names

    def _read(self, job_id: str) -> dict:
        descriptor = self._open(self._name(job_id), os.O_RDONLY)
        with os.fdopen(descriptor, "rb") as stream:
            data = stream.read(MAX_JOB_RECORD_BYTES + 1)
        if len(data) > MAX_JOB_RECORD_BYTES:
            raise AnnotationJobStoreError("job record exceeds capacity")
        try:
            record = json.loads(data, object_pairs_hook=_pairs,
                                parse_constant=lambda _value: _invalid())
            legacy_fields = {"schema_version", "job_id", "submitted_at", "state", "source", "attempt_epoch"}
            if type(record) is not dict:
                raise ValueError
            if set(record) == legacy_fields:
                # Source-only v1 records predate results/checkpoints. Normalize
                # in memory; reads never rewrite or invent recovered output.
                record = {**record, "storage_version": STORAGE_VERSION, "result": None, "checkpoints": []}
            if (set(record) != legacy_fields | {"storage_version", "result", "checkpoints"}
                    or type(record["storage_version"]) is not int
                    or record["storage_version"] not in {STORAGE_VERSION, RUNTIME_STORAGE_VERSION}
                    or record["job_id"] != job_id):
                raise ValueError
            metadata = self._metadata(record)
            if type(record["source"]) is not dict or set(record["source"]) != {
                "filename", "content", "domain", "profile", "prepared_digest",
            }:
                raise ValueError
            source = record["source"]
            if (not all(isinstance(value, str) for value in source.values())
                    or len(source["filename"]) > 255 or len(source["domain"]) > 128
                    or len(source["profile"]) > 64
                    or re.fullmatch(r"[0-9a-f]{64}", source["prepared_digest"]) is None):
                raise ValueError
            epoch = record["attempt_epoch"]
            if metadata.state == "running":
                if not isinstance(epoch, str) or re.fullmatch(r"[0-9a-f]{64}", epoch) is None:
                    raise ValueError
            elif epoch is not None:
                raise ValueError
            # Validate source/chunk identity before recovery can rewrite state.
            # A code/chunking change requires an explicit future migration,
            # never silently accepting a different prepared source.
            document = prepare_document_text(source["content"], source["filename"],
                                             domain=source["domain"], profile=source["profile"])
            if _prepared_digest(document) != source["prepared_digest"]:
                raise ValueError
            self._validate_saved_output(record, document)
            return record
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise AnnotationJobStoreError("job record is invalid") from None

    @staticmethod
    def _metadata(record: dict) -> AnnotationJobMetadata:
        return AnnotationJobMetadata(datetime.fromisoformat(record["submitted_at"]),
                                     record["state"], record["schema_version"])

    @staticmethod
    def _document(record: dict) -> PreparedDocument:
        source = record["source"]
        return prepare_document_text(source["content"], source["filename"],
                                     domain=source["domain"], profile=source["profile"])

    @staticmethod
    def _checkpoint_result(record: dict, document: PreparedDocument) -> DocumentAnnotationResult:
        by_chunk = {item["chunk_id"]: item["result"] for item in record["checkpoints"]}
        candidates, failures = [], []
        for chunk in document.chunks:
            if chunk.chunk_id not in by_chunk:
                raise AnnotationJobStoreError("annotation checkpoints are incomplete")
            result = validate_chunk_checkpoint(document, chunk.chunk_id, by_chunk[chunk.chunk_id])
            candidates.extend(result.candidates)
            failures.extend(result.failures)
        return DocumentAnnotationResult(tuple(candidates), tuple(failures))

    @classmethod
    def _validate_saved_output(cls, record: dict, document: PreparedDocument) -> None:
        checkpoints = record["checkpoints"]
        if type(checkpoints) is not list or len(checkpoints) > len(document.chunks):
            raise AnnotationJobStoreError("annotation checkpoints are invalid")
        seen = set()
        candidate_count = 0
        for checkpoint in checkpoints:
            if type(checkpoint) is not dict:
                raise AnnotationJobStoreError("annotation checkpoints are invalid")
            fields = {"chunk_id", "result"}
            if record["storage_version"] == RUNTIME_STORAGE_VERSION and "runtime_fingerprint" in checkpoint:
                fields.add("runtime_fingerprint")
                validate_runtime_fingerprint(checkpoint["runtime_fingerprint"])
            if set(checkpoint) != fields:
                raise AnnotationJobStoreError("annotation checkpoints are invalid")
            chunk_id = checkpoint["chunk_id"]
            validate_chunk_checkpoint(document, chunk_id, checkpoint["result"])
            candidate_count += len(checkpoint["result"]["candidates"])
            if candidate_count > MAX_RESULT_CANDIDATES:
                raise AnnotationJobStoreError("annotation checkpoints exceed result capacity")
            if chunk_id in seen:
                raise AnnotationJobStoreError("annotation checkpoints are invalid")
            seen.add(chunk_id)
        result = record["result"]
        if result is None:
            if record["state"] == "completed":
                raise AnnotationJobStoreError("annotation result is missing")
        else:
            if record["state"] not in {"completed", "expired"}:
                raise AnnotationJobStoreError("annotation result state is invalid")
            decode_annotation_job_result(document, result)
            if checkpoints:
                combined = encode_annotation_job_result(document, cls._checkpoint_result(record, document))
                if result != combined:
                    raise AnnotationJobStoreError("annotation result conflicts with checkpoints")

    def _write(self, record: dict, *, new: bool = False, require_unexpired: bool = False) -> None:
        data = _encoded(record)
        filename = self._name(record["job_id"])
        names = self._records()
        if new and (filename in names or len(names) >= MAX_JOB_COUNT):
            raise AnnotationJobStoreError("job store cannot admit another record")
        size = len(data)
        for name in names:
            if name != filename:
                descriptor = self._open(name, os.O_RDONLY)
                try:
                    size += os.fstat(descriptor).st_size
                finally:
                    os.close(descriptor)
        if size > MAX_STORE_BYTES:
            raise AnnotationJobStoreError("job store exceeds capacity")
        pending = ".annotation-job-" + secrets.token_hex(16) + ".pending"
        descriptor = self._open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if require_unexpired and not annotation_job_accessible(self._metadata(record), now=self._clock()):
                raise AnnotationJobStoreError("annotation job has expired")
            os.replace(pending, filename, src_dir_fd=self._directory, dst_dir_fd=self._directory)
            os.fsync(self._directory)
        finally:
            # Only this call's unpredictable, Core-created pending file.
            try:
                os.unlink(pending, dir_fd=self._directory)
            except FileNotFoundError:
                pass

    def _recover(self) -> None:
        with self._guard():
            # Validate the full set before any rewrite; no partial repair.
            records = [self._read(name[:-5]) for name in self._records()]
            now = self._clock()
            updates = []
            for record in records:
                recovered = recover_annotation_job(self._metadata(record), now=now)
                if recovered.state != record["state"]:
                    updates.append({**record, "state": recovered.state, "attempt_epoch": None})
            for record in updates:
                self._write(record)

    def submit(self, content: str, filename: str, *, domain="personal", profile="assistant_note") -> AnnotationJobStatus:
        # Pure intake validation runs before any record is created.
        try:
            document = prepare_document_text(content, filename, domain=domain, profile=profile)
            if len(document.source_name) > 255 or len(document.domain) > 128:
                raise ValueError
            metadata = AnnotationJobMetadata(self._clock())
            record = {
                "schema_version": metadata.schema_version,
                "storage_version": STORAGE_VERSION, "result": None, "checkpoints": [],
                "job_id": "AJ-" + secrets.token_hex(16),
                "submitted_at": metadata.submitted_at.isoformat(), "state": "queued",
                "attempt_epoch": None,
                "source": {"filename": document.source_name, "content": content,
                           "domain": document.domain, "profile": document.profile,
                           "prepared_digest": _prepared_digest(document)},
            }
        except (ValueError, TypeError, UnicodeError):
            raise AnnotationJobStoreError("job source is invalid") from None
        with self._guard():
            self._write(record, new=True, require_unexpired=True)
        return AnnotationJobStatus(record["job_id"], metadata)

    def status(self, job_id: str) -> AnnotationJobStatus:
        with self._guard():
            metadata = self._metadata(self._read(job_id))
            if not annotation_job_accessible(metadata, now=self._clock()):
                metadata = AnnotationJobMetadata(metadata.submitted_at, "expired")
            return AnnotationJobStatus(job_id, metadata)

    def _progress(self, record: dict, *, now: datetime) -> AnnotationJobProgress:
        metadata = self._metadata(record)
        if not annotation_job_accessible(metadata, now=now):
            raise AnnotationJobStoreError("annotation job has expired")
        total = len(self._document(record).chunks)
        checkpoints = record["checkpoints"]
        result = record["result"]
        if result is not None:
            candidates, failures = len(result["candidates"]), len(result["failures"])
        else:
            candidates = sum(len(item["result"]["candidates"]) for item in checkpoints)
            failures = sum(len(item["result"]["failures"]) for item in checkpoints)
        return AnnotationJobProgress(
            job_id=record["job_id"], metadata=metadata, total_chunks=total,
            checkpointed_chunks=len(checkpoints),
            pending_chunks=0 if metadata.state == "completed" else total - len(checkpoints),
            candidate_count=candidates, failed_chunks=failures,
            result_available=metadata.state == "completed",
        )

    def progress(self, job_id: str) -> AnnotationJobProgress:
        """Internal passive snapshot, not a public endpoint or authorization check.

        Uses already saved source/results and pure validation; never probes a
        provider or changes job state. Expired progress is unavailable.
        """
        with self._guard():
            record = self._read(job_id)
            snapshot = self._progress(record, now=self._clock())
            if not annotation_job_accessible(snapshot.metadata, now=self._clock()):
                raise AnnotationJobStoreError("annotation job has expired")
            return snapshot

    def list_progress(self) -> tuple[AnnotationJobProgress, ...]:
        """Trusted-store listing only; no conversation key authenticates a reader.

        Validate all records before returning any snapshot; omit expired jobs.
        The local operator CLI separately binds host ownership and acknowledged
        maintenance. Shared user-facing listing still needs access policy.
        """
        with self._guard():
            records = [self._read(name[:-5]) for name in self._records()]
            now = self._clock()
            snapshots = [self._progress(record, now=now) for record in records
                         if annotation_job_accessible(self._metadata(record), now=now)]
            final_now = self._clock()
            snapshots = [item for item in snapshots if annotation_job_accessible(item.metadata, now=final_now)]
            return tuple(sorted(snapshots,
                                key=lambda item: (item.metadata.submitted_at, item.job_id), reverse=True))

    def read_source(self, job_id: str) -> PreparedDocument:
        with self._guard():
            record = self._read(job_id)
            if not annotation_job_accessible(self._metadata(record), now=self._clock()):
                raise AnnotationJobStoreError("annotation job has expired")
            source = record["source"]
            try:
                document = prepare_document_text(source["content"], source["filename"],
                                                 domain=source["domain"], profile=source["profile"])
                if _prepared_digest(document) != source["prepared_digest"]:
                    raise ValueError
            except (ValueError, TypeError):
                raise AnnotationJobStoreError("job source failed validation") from None
            return document

    def resume(self, job_id: str) -> AnnotationJobStatus:
        with self._guard():
            record = self._read(job_id)
            metadata = resume_annotation_job(self._metadata(record), now=self._clock())
            self._write({**record, "state": metadata.state, "attempt_epoch": None}, require_unexpired=True)
            return AnnotationJobStatus(job_id, metadata)

    def mark_running(self, job_id: str) -> AnnotationJobAttempt:
        """Record launch intent only; actual provider admission remains separate."""
        with self._guard():
            record = self._read(job_id)
            if record["state"] != "queued" or not annotation_job_accessible(self._metadata(record), now=self._clock()):
                raise AnnotationJobStoreError("job is not eligible for launch intent")
            attempt_id = secrets.token_hex(32)
            self._write({**record, "state": "running", "attempt_epoch": attempt_id}, require_unexpired=True)
            return AnnotationJobAttempt(job_id, self._epoch, attempt_id)

    def interrupt(self, attempt: AnnotationJobAttempt) -> None:
        with self._guard():
            record = self._current_attempt(attempt)
            self._write({**record, "state": "interrupted", "attempt_epoch": None})

    def _current_attempt(self, attempt: AnnotationJobAttempt) -> dict:
        if type(attempt) is not AnnotationJobAttempt or attempt.owner_epoch != self._epoch:
            raise AnnotationJobStoreError("job attempt belongs to another owner")
        record = self._read(attempt.job_id)
        if record["state"] != "running" or record["attempt_epoch"] != attempt.attempt_id:
            raise AnnotationJobStoreError("job attempt is no longer current")
        return record

    def _unexpired_attempt(self, attempt: AnnotationJobAttempt) -> dict:
        record = self._current_attempt(attempt)
        if not annotation_job_accessible(self._metadata(record), now=self._clock()):
            raise AnnotationJobStoreError("annotation job has expired")
        return record

    def next_chunk(self, attempt: AnnotationJobAttempt) -> tuple[PreparedDocument, str] | None:
        """Read the next unfinished original chunk for one current run intent.

        This internal plan is not provider admission, scheduling or disclosure
        consent. No checkpoint/state is changed just by reading it.
        """
        with self._guard():
            record = self._unexpired_attempt(attempt)
            document = self._document(record)
            saved = {item["chunk_id"] for item in record["checkpoints"]}
            selected = next((chunk.chunk_id for chunk in document.chunks if chunk.chunk_id not in saved), None)
            if not annotation_job_accessible(self._metadata(record), now=self._clock()):
                raise AnnotationJobStoreError("annotation job has expired")
            return (document, selected) if selected is not None else None

    def complete(self, attempt: AnnotationJobAttempt, result: DocumentAnnotationResult) -> None:
        """Persist validated full-run output, never approve its claims or write memory.

        Completed means processing ended, not extraction quality or factual
        correctness. Results may include explicit failed chunks or no candidates.
        """
        with self._guard():
            record = self._unexpired_attempt(attempt)
            document = self._document(record)
            output = encode_annotation_job_result(document, result)
            completed = {**record, "state": "completed", "attempt_epoch": None, "result": output}
            self._validate_saved_output(completed, document)
            self._write(completed, require_unexpired=True)

    def read_result(self, job_id: str) -> DocumentAnnotationResult:
        """Explicit internal read; returns newly validated, detached candidate data."""
        with self._guard():
            record = self._read(job_id)
            if not annotation_job_accessible(self._metadata(record), now=self._clock()):
                raise AnnotationJobStoreError("annotation job has expired")
            if record["state"] != "completed" or record["result"] is None:
                raise AnnotationJobStoreError("annotation job has no completed result")
            return decode_annotation_job_result(self._document(record), record["result"])

    def save_checkpoint(self, attempt: AnnotationJobAttempt, chunk_id: str, result: DocumentAnnotationResult,
                        *, runtime_fingerprint: str | None = None) -> None:
        """Save one completed chunk exactly once; empty and failed are distinct.

        Retry of identical checkpoint data is idempotent. Conflicting data or a
        stale attempt cannot overwrite evidence from an earlier chunk attempt.
        """
        if runtime_fingerprint is not None:
            try:
                validate_runtime_fingerprint(runtime_fingerprint)
            except AnnotationJobRuntimeError:
                raise AnnotationJobStoreError("annotation runtime evidence is invalid") from None
        with self._guard():
            record = self._unexpired_attempt(attempt)
            document = self._document(record)
            output = encode_annotation_job_result(document, result)
            validate_chunk_checkpoint(document, chunk_id, output)
            saved = {"chunk_id": chunk_id, "result": output}
            if runtime_fingerprint is not None:
                saved["runtime_fingerprint"] = runtime_fingerprint
            for checkpoint in record["checkpoints"]:
                if checkpoint["chunk_id"] == chunk_id:
                    if checkpoint == saved:
                        return
                    raise AnnotationJobStoreError("annotation checkpoint conflicts with saved output")
            updated = {**record, "checkpoints": record["checkpoints"] + [saved]}
            if runtime_fingerprint is not None:
                updated["storage_version"] = RUNTIME_STORAGE_VERSION
            self._validate_saved_output(updated, document)
            self._write(updated, require_unexpired=True)

    def runtime_evidence(self, job_id: str) -> AnnotationRuntimeEvidence:
        """Internal saved-config coverage only; no source/result/hash exposure.

        Legacy/unbound checkpoints remain unknown, never retroactively filled.
        Equal declared fingerprints do not attest actual model bytes or truth.
        """
        with self._guard():
            record = self._read(job_id)
            metadata = self._metadata(record)
            if not annotation_job_accessible(metadata, now=self._clock()):
                raise AnnotationJobStoreError("annotation job has expired")
            fingerprints = [item["runtime_fingerprint"] for item in record["checkpoints"]
                            if "runtime_fingerprint" in item]
            evidence = AnnotationRuntimeEvidence(len(record["checkpoints"]), len(fingerprints), len(set(fingerprints)))
            if not annotation_job_accessible(metadata, now=self._clock()):
                raise AnnotationJobStoreError("annotation job has expired")
            return evidence

    def pending_chunk_ids(self, job_id: str) -> tuple[str, ...]:
        """Internal work plan only; never schedules, admits or calls a provider."""
        with self._guard():
            record = self._read(job_id)
            if not annotation_job_accessible(self._metadata(record), now=self._clock()):
                raise AnnotationJobStoreError("annotation job has expired")
            if record["state"] == "completed":
                return ()
            saved = {checkpoint["chunk_id"] for checkpoint in record["checkpoints"]}
            return tuple(chunk.chunk_id for chunk in self._document(record).chunks if chunk.chunk_id not in saved)

    def finish_checkpoints(self, attempt: AnnotationJobAttempt) -> None:
        """Explicitly assemble all chunk outcomes; never regenerate missing work."""
        with self._guard():
            record = self._unexpired_attempt(attempt)
            document = self._document(record)
            result = self._checkpoint_result(record, document)
            self.complete(attempt, result)

    def delete(self, job_id: str) -> None:
        """Explicit trusted deletion of one nonrunning record; never cancel work."""
        with self._guard():
            record = self._read(job_id)
            if record["state"] == "running":
                raise AnnotationJobStoreError("running intent must be interrupted before deletion")
            os.unlink(self._name(job_id), dir_fd=self._directory)
            os.fsync(self._directory)

    def cleanup_expired(self) -> int:
        """Explicit retention sweep; unknown files and running intent are retained."""
        with self._guard():
            records = [self._read(name[:-5]) for name in self._records()]
            now = self._clock()
            selected = [record for record in records if record["state"] != "running"
                        and not annotation_job_accessible(self._metadata(record), now=now)]
            for record in selected:
                os.unlink(self._name(record["job_id"]), dir_fd=self._directory)
            if selected:
                os.fsync(self._directory)
            return len(selected)


def _invalid():
    raise AnnotationJobStoreError("job record is invalid")
