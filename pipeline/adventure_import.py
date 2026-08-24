"""Reviewed external-document staging isolated from authoritative adventure state.

An import record preserves only the user-selected, already validated candidate
claims and provenance needed for a later typed adventure-import policy.  It is
not an event, state mutation, transcript, prompt fact, memory, or replay input.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Callable, Iterator, Mapping, Sequence

from pipeline.adventure_registry import AdventureRecord, AdventureRegistry, AdventureRegistryError
from pipeline.document_intake import DocumentMemoryCandidate, PreparedDocument

try:  # POSIX production (including WSL); Windows uses the fallback below.
    import fcntl
except ImportError:  # pragma: no cover - Windows-only standard-library fallback.
    fcntl = None


IMPORT_SCHEMA_VERSION = 1
IMPORT_FILENAME = "imports.jsonl"
IMPORT_WRITE_LOCK_FILENAME = ".imports.write.lock"
MAX_IMPORT_CANDIDATES = 128
MAX_IMPORT_TEXT_LENGTH = 8_000
_IMPORT_ID_PATTERN = re.compile(r"^AI-[0-9]{6}$")
_CANDIDATE_ID_PATTERN = re.compile(r"^C-[0-9]{3,}$")


class AdventureImportError(ValueError):
    """Raised when an adventure import cannot be validated or staged safely."""


def _required_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AdventureImportError(f"adventure import {field} must be text")
    text = value.strip()
    if not text:
        raise AdventureImportError(f"adventure import {field} cannot be empty")
    if "\x00" in text:
        raise AdventureImportError(f"adventure import {field} cannot contain NUL")
    if len(text) > maximum:
        raise AdventureImportError(f"adventure import {field} must be at most {maximum} characters")
    return text


def _optional_text(value: object, *, field: str, maximum: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AdventureImportError(f"adventure import {field} must be text")
    text = value.strip()
    if "\x00" in text:
        raise AdventureImportError(f"adventure import {field} cannot contain NUL")
    if len(text) > maximum:
        raise AdventureImportError(f"adventure import {field} must be at most {maximum} characters")
    return text


def _candidate_snapshot(candidate_id: object, candidate: DocumentMemoryCandidate) -> dict[str, object]:
    if not isinstance(candidate_id, str) or not _CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        raise AdventureImportError("adventure import candidate identifier is invalid")
    if not isinstance(candidate, DocumentMemoryCandidate):
        raise AdventureImportError("adventure import candidate is invalid")
    proposal = candidate.proposal
    fields = ("subject", "memory_type", "summary", "details", "importance", "confidence", "retention", "domain", "source")
    if set(proposal) - {"store", *fields}:
        raise AdventureImportError("adventure import candidate proposal fields are invalid")
    try:
        snapshot = {
            "candidate_id": candidate_id,
            "subject": _required_text(proposal["subject"], field="candidate subject", maximum=500),
            "memory_type": _required_text(proposal["memory_type"], field="candidate type", maximum=100),
            "summary": _required_text(proposal["summary"], field="candidate summary", maximum=MAX_IMPORT_TEXT_LENGTH),
            "details": _optional_text(proposal.get("details"), field="candidate details", maximum=MAX_IMPORT_TEXT_LENGTH),
            "importance": float(proposal["importance"]),
            "confidence": float(proposal["confidence"]),
            "retention": _required_text(proposal["retention"], field="candidate retention", maximum=100),
            "domain": _required_text(proposal["domain"], field="candidate domain", maximum=300),
            "source": _required_text(proposal["source"], field="candidate source", maximum=300),
            "source_reference": _required_text(candidate.source_reference, field="source reference", maximum=2_000),
            "chunk_id": _required_text(candidate.chunk_id, field="chunk identifier", maximum=2_000),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise AdventureImportError("adventure import candidate proposal is invalid") from error
    if not 0.0 <= snapshot["importance"] <= 1.0 or not 0.0 <= snapshot["confidence"] <= 1.0:
        raise AdventureImportError("adventure import candidate score is invalid")
    return snapshot


@dataclass(frozen=True)
class AdventureImportRecord:
    """One explicitly staged, non-canonical reviewed-document selection."""

    sequence: int
    import_id: str
    review_id: str
    source_id: str
    source_name: str
    source_hash: str
    source_profile: str
    candidates: tuple[Mapping[str, object], ...]
    staged_at: str
    schema_version: int = IMPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureImportError("adventure import sequence must be a positive integer")
        if self.import_id != f"AI-{self.sequence:06d}" or not _IMPORT_ID_PATTERN.fullmatch(self.import_id):
            raise AdventureImportError("adventure import identifier is invalid")
        for field, maximum in (("review_id", 100), ("source_id", 2_000), ("source_name", 500), ("source_hash", 200), ("source_profile", 100)):
            object.__setattr__(self, field, _required_text(getattr(self, field), field=field, maximum=maximum))
        if not isinstance(self.candidates, tuple) or not self.candidates or len(self.candidates) > MAX_IMPORT_CANDIDATES:
            raise AdventureImportError("adventure import candidates are invalid")
        normalized = tuple(_snapshot_from_dict(value) for value in self.candidates)
        if len({item["candidate_id"] for item in normalized}) != len(normalized):
            raise AdventureImportError("adventure import candidate identifiers must be unique")
        object.__setattr__(self, "candidates", normalized)
        _required_text(self.staged_at, field="staging time", maximum=100)
        try:
            datetime.fromisoformat(self.staged_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise AdventureImportError("adventure import staging time is invalid") from error
        if self.schema_version != IMPORT_SCHEMA_VERSION:
            raise AdventureImportError("adventure import schema is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "import_id": self.import_id,
            "review_id": self.review_id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_hash": self.source_hash,
            "source_profile": self.source_profile,
            "candidates": [dict(candidate) for candidate in self.candidates],
            "staged_at": self.staged_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureImportRecord":
        if not isinstance(value, dict):
            raise AdventureImportError("adventure import record must be an object")
        expected = {"schema_version", "sequence", "import_id", "review_id", "source_id", "source_name", "source_hash", "source_profile", "candidates", "staged_at"}
        if set(value) != expected or not isinstance(value["candidates"], list):
            raise AdventureImportError("adventure import record fields are invalid")
        return cls(
            schema_version=value["schema_version"], sequence=value["sequence"], import_id=value["import_id"],
            review_id=value["review_id"], source_id=value["source_id"], source_name=value["source_name"],
            source_hash=value["source_hash"], source_profile=value["source_profile"],
            candidates=tuple(value["candidates"]), staged_at=value["staged_at"],
        )


def _snapshot_from_dict(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise AdventureImportError("adventure import candidate snapshot is invalid")
    expected = {"candidate_id", "subject", "memory_type", "summary", "details", "importance", "confidence", "retention", "domain", "source", "source_reference", "chunk_id"}
    if set(value) != expected:
        raise AdventureImportError("adventure import candidate snapshot fields are invalid")
    # Reuse the same full validation shape without retaining an observation body.
    candidate_id = value["candidate_id"]
    if not isinstance(candidate_id, str) or not _CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        raise AdventureImportError("adventure import candidate identifier is invalid")
    result = dict(value)
    for field in ("subject", "memory_type", "summary", "retention", "domain", "source", "source_reference", "chunk_id"):
        maximum = MAX_IMPORT_TEXT_LENGTH if field in {"summary", "details"} else 2_000
        result[field] = _required_text(result[field], field=f"candidate {field}", maximum=maximum)
    result["details"] = _optional_text(result["details"], field="candidate details", maximum=MAX_IMPORT_TEXT_LENGTH)
    for field in ("importance", "confidence"):
        if isinstance(result[field], bool) or not isinstance(result[field], (int, float)) or not 0.0 <= float(result[field]) <= 1.0:
            raise AdventureImportError("adventure import candidate score is invalid")
        result[field] = float(result[field])
    return result


class AdventureImportLog:
    """Append-only non-canonical staging log for an existing adventure workspace."""

    def __init__(self, registry: AdventureRegistry, record: AdventureRecord, *, now: Callable[[], datetime] | None = None) -> None:
        if not isinstance(registry, AdventureRegistry) or not isinstance(record, AdventureRecord):
            raise TypeError("registry and record must be adventure registry records")
        try:
            if registry.resolve_title(record.title) != record:
                raise AdventureImportError("adventure record does not match the registry")
        except AdventureRegistryError as error:
            raise AdventureImportError("adventure workspace is not registered") from error
        self._workspace = registry.workspace_path(record.adventure_id)
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        return self._workspace / IMPORT_FILENAME

    @property
    def lock_path(self) -> Path:
        return self._workspace / IMPORT_WRITE_LOCK_FILENAME

    def records(self) -> list[AdventureImportRecord]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise AdventureImportError("adventure import log cannot be read") from error
        records: list[AdventureImportRecord] = []
        for sequence, line in enumerate(lines, start=1):
            try:
                record = AdventureImportRecord.from_dict(json.loads(line))
            except (json.JSONDecodeError, AdventureImportError) as error:
                raise AdventureImportError("adventure import log is invalid") from error
            if record.sequence != sequence:
                raise AdventureImportError("adventure import log sequence is invalid")
            records.append(record)
        return records

    def stage(self, *, review_id: object, document: PreparedDocument, selected: Sequence[tuple[str, DocumentMemoryCandidate]]) -> AdventureImportRecord:
        if not isinstance(document, PreparedDocument):
            raise TypeError("document must be a PreparedDocument")
        if not isinstance(review_id, str) or not review_id.strip():
            raise AdventureImportError("review identifier is required")
        if not isinstance(selected, Sequence) or not selected or len(selected) > MAX_IMPORT_CANDIDATES:
            raise AdventureImportError("selected review candidates are invalid")
        snapshots = tuple(_candidate_snapshot(candidate_id, candidate) for candidate_id, candidate in selected)
        if any(candidate["domain"] != document.domain for candidate in snapshots):
            raise AdventureImportError("candidate domain does not match the reviewed document")
        with self._write_guard():
            existing = self.records()
            if any(
                record.review_id == review_id.strip()
                and record.source_id == document.source_id
                and record.source_hash == document.content_hash
                and record.candidates == snapshots
                for record in existing
            ):
                return next(
                    record for record in existing
                    if record.review_id == review_id.strip()
                    and record.source_id == document.source_id
                    and record.source_hash == document.content_hash
                    and record.candidates == snapshots
                )
            sequence = len(existing) + 1
            record = AdventureImportRecord(
                sequence=sequence, import_id=f"AI-{sequence:06d}", review_id=review_id.strip(),
                source_id=document.source_id, source_name=document.source_name,
                source_hash=document.content_hash, source_profile=document.profile,
                candidates=snapshots, staged_at=self._now().astimezone(UTC).isoformat(),
            )
            self._replace_records((*existing, record))
            return record

    @contextmanager
    def _write_guard(self) -> Iterator[None]:
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR)
        except OSError as error:
            raise AdventureImportError("adventure import lock cannot be acquired") from error
        try:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:  # pragma: no cover - Windows-only standard-library fallback.
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                    os.fsync(descriptor)
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            os.close(descriptor)
            raise AdventureImportError("adventure import is busy") from error
        try:
            yield
        finally:
            try:
                if fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                else:  # pragma: no cover - Windows-only standard-library fallback.
                    import msvcrt
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            finally:
                os.close(descriptor)

    def _replace_records(self, records: Sequence[AdventureImportRecord]) -> None:
        temporary = self.path.with_suffix(".jsonl.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    handle.write(json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise AdventureImportError("adventure import log cannot be written") from error


__all__ = [
    "AdventureImportError", "AdventureImportLog", "AdventureImportRecord", "IMPORT_FILENAME",
    "IMPORT_SCHEMA_VERSION", "IMPORT_WRITE_LOCK_FILENAME", "MAX_IMPORT_CANDIDATES",
]
