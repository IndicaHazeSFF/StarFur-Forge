"""Durable, privacy-bounded tool-run intent/outcome journal.

This is deliberately not an executor, grant store, or security audit log.  It
records only enough Core-issued identity to prevent a restart from replaying an
ambiguous effect.  A recovered nonterminal intent becomes ``outcome_unknown``;
it never regains authorization and this module never invokes a callback.

Every admitted identity is bound to one Core-created owner epoch and opaque
invocation fingerprint.  One OS-held lifetime lease owns admission and restart
reconciliation, so another live process cannot fence its unfinished work.
Historical identities are never readmitted.  The journal intentionally does
not compact them yet; reaching capacity fails closed without deleting history.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
from threading import RLock
import time
from typing import Callable, Iterator, Mapping

from .tool_audit import TOOL_LIFECYCLE_STATES
from .tool_grants import IDENTITY_RE, INVOCATION_ID_RE, ToolInvocation
from .tool_registry import MAX_TOOL_ID_CHARACTERS, TOOL_ID_RE

try:  # POSIX production, including WSL.
    import fcntl
except ImportError:  # pragma: no cover - Windows standard-library fallback.
    fcntl = None


TOOL_RUN_JOURNAL_SCHEMA_VERSION = 2
TOOL_RUN_JOURNAL_FILENAME = "tool-runs.jsonl"
TOOL_RUN_JOURNAL_LOCK_FILENAME = ".tool-runs.write.lock"
TOOL_RUN_OWNER_LOCK_FILENAME = ".tool-runs.owner.lock"
MAX_TOOL_RUN_RECORDS = 1024
MAX_TOOL_RUN_JOURNAL_RECORDS = 4096
MAX_TOOL_RUN_RECORD_BYTES = 2048
MAX_TOOL_RUN_JOURNAL_BYTES = MAX_TOOL_RUN_JOURNAL_RECORDS * MAX_TOOL_RUN_RECORD_BYTES
MAX_TOOL_RUN_JSON_DEPTH = 2
MAX_TOOL_RUN_REASON_LENGTH = 64
TERMINAL_RUN_STATES = frozenset({
    "completed", "failed", "denied", "cancelled", "timed_out", "outcome_unknown",
})
RUN_REASONS = frozenset({
    "submitted", "completed", "failed", "denied", "cancelled", "timed_out",
    "owner_session_expired", "restart_reconciliation",
})
RUN_STATE_REASONS = {
    "awaiting_approval": frozenset({"submitted"}),
    "completed": frozenset({"completed"}),
    "failed": frozenset({"failed"}),
    "denied": frozenset({"denied"}),
    "cancelled": frozenset({"cancelled"}),
    "timed_out": frozenset({"timed_out"}),
    "outcome_unknown": frozenset({"owner_session_expired", "restart_reconciliation"}),
}
OWNER_EPOCH_RE = re.compile(r"^TO-[A-Za-z0-9_-]{1,64}$")
BINDING_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


class ToolRunJournalError(ValueError):
    """Raised when a durable journal cannot be safely read or updated."""


class ToolRunReplayError(ToolRunJournalError):
    """Raised when a previously admitted run identity is submitted again."""


class ToolRunOwnerLease:
    """Opaque process-local proof that Core holds the journal owner lock."""

    __slots__ = (
        "_owner_id", "_owner_epoch", "_descriptor", "_journal_token",
        "_process_id", "_released",
    )

    def __init__(
        self, owner_id: str, owner_epoch: str, descriptor: int,
        journal_token: object,
    ) -> None:
        self._owner_id = owner_id
        self._owner_epoch = owner_epoch
        self._descriptor = descriptor
        self._journal_token = journal_token
        self._process_id = os.getpid()
        self._released = False

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @property
    def owner_epoch(self) -> str:
        return self._owner_epoch

    @property
    def active(self) -> bool:
        return not self._released and self._process_id == os.getpid()


def _invocation_fingerprint(invocation: ToolInvocation) -> str:
    """Bind durable admission to exact authority context without storing payloads."""
    encoded = json.dumps(
        invocation.binding_tuple(),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_timestamp(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 <= float(value) < 10**12
    ):
        raise ToolRunJournalError(f"tool run {label} is invalid")
    return float(value)


def _json_depth(value: object) -> int:
    if isinstance(value, Mapping):
        return 1 + max((_json_depth(item) for item in value.values()), default=0)
    if isinstance(value, (list, tuple)):
        return 1 + max((_json_depth(item) for item in value), default=0)
    return 0


def _is_reparse_or_symlink(path: Path, metadata: os.stat_result | None = None) -> bool:
    details = os.lstat(path) if metadata is None else metadata
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag)


@dataclass(frozen=True)
class ToolRunRecord:
    """One bounded durable state transition without proposal/output payloads."""

    sequence: int
    kind: str
    run_id: str
    tool_id: str
    tool_version: int
    session_instance_id: str
    binding_fingerprint: str
    owner_id: str
    owner_epoch: str
    expires_at: float
    state: str
    reason: str
    timestamp: float

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise ToolRunJournalError("tool run sequence is invalid")
        if self.kind not in {"intent", "outcome"}:
            raise ToolRunJournalError("tool run record kind is invalid")
        if not isinstance(self.run_id, str) or not INVOCATION_ID_RE.fullmatch(self.run_id):
            raise ToolRunJournalError("tool run identifier is invalid")
        if (
            not isinstance(self.tool_id, str)
            or len(self.tool_id) > MAX_TOOL_ID_CHARACTERS
            or not TOOL_ID_RE.fullmatch(self.tool_id)
        ):
            raise ToolRunJournalError("tool run tool identifier is invalid")
        if (
            isinstance(self.tool_version, bool)
            or not isinstance(self.tool_version, int)
            or not 1 <= self.tool_version <= 999
        ):
            raise ToolRunJournalError("tool run version is invalid")
        if not isinstance(self.session_instance_id, str) or not IDENTITY_RE.fullmatch(self.session_instance_id):
            raise ToolRunJournalError("tool run session binding is invalid")
        if (
            not isinstance(self.binding_fingerprint, str)
            or not BINDING_FINGERPRINT_RE.fullmatch(self.binding_fingerprint)
        ):
            raise ToolRunJournalError("tool run binding fingerprint is invalid")
        if not isinstance(self.owner_id, str) or not IDENTITY_RE.fullmatch(self.owner_id):
            raise ToolRunJournalError("tool run owner identifier is invalid")
        if not isinstance(self.owner_epoch, str) or not OWNER_EPOCH_RE.fullmatch(self.owner_epoch):
            raise ToolRunJournalError("tool run owner epoch is invalid")
        _valid_timestamp(self.expires_at, "expiry")
        if self.state not in TOOL_LIFECYCLE_STATES:
            raise ToolRunJournalError("tool run state is invalid")
        if self.kind == "intent" and self.state != "awaiting_approval":
            raise ToolRunJournalError("tool run intent state is invalid")
        if self.kind == "outcome" and self.state not in TERMINAL_RUN_STATES:
            raise ToolRunJournalError("tool run outcome state is invalid")
        if not isinstance(self.reason, str) or self.reason not in RUN_REASONS or len(self.reason) > MAX_TOOL_RUN_REASON_LENGTH:
            raise ToolRunJournalError("tool run reason is invalid")
        if self.reason not in RUN_STATE_REASONS.get(self.state, ()):
            raise ToolRunJournalError("tool run reason does not match its state")
        object.__setattr__(self, "expires_at", _valid_timestamp(self.expires_at, "expiry"))
        object.__setattr__(self, "timestamp", _valid_timestamp(self.timestamp, "timestamp"))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": TOOL_RUN_JOURNAL_SCHEMA_VERSION,
            "sequence": self.sequence,
            "kind": self.kind,
            "run_id": self.run_id,
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "session_instance_id": self.session_instance_id,
            "binding_fingerprint": self.binding_fingerprint,
            "owner_id": self.owner_id,
            "owner_epoch": self.owner_epoch,
            "expires_at": self.expires_at,
            "state": self.state,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ToolRunRecord":
        if not isinstance(value, dict) or set(value) != {
            "schema_version", "sequence", "kind", "run_id", "tool_id", "tool_version",
            "session_instance_id", "binding_fingerprint", "owner_id", "owner_epoch",
            "expires_at", "state", "reason", "timestamp",
        }:
            raise ToolRunJournalError("tool run journal record is invalid")
        schema_version = value.get("schema_version")
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != TOOL_RUN_JOURNAL_SCHEMA_VERSION
        ):
            raise ToolRunJournalError("tool run journal schema version is invalid")
        return cls(
            value["sequence"], value["kind"], value["run_id"], value["tool_id"],
            value["tool_version"], value["session_instance_id"], value["binding_fingerprint"],
            value["owner_id"], value["owner_epoch"], value["expires_at"], value["state"],
            value["reason"], value["timestamp"],
        )


class ToolRunJournal:
    """Core-owned append-only replacement journal with no execution path."""

    def __init__(
        self, root: Path | str, *, clock: Callable[[], float] = time.time,
        maximum_records: int = MAX_TOOL_RUN_RECORDS,
        owner_epoch_factory: Callable[[], str] | None = None,
    ) -> None:
        self._root = Path(root)
        if not self._root.is_absolute():
            raise ToolRunJournalError("tool run journal root must be absolute")
        self._validate_root()
        if not callable(clock):
            raise TypeError("tool run journal clock is invalid")
        if owner_epoch_factory is not None and not callable(owner_epoch_factory):
            raise TypeError("tool run owner epoch factory is invalid")
        if (
            isinstance(maximum_records, bool)
            or not isinstance(maximum_records, int)
            or not 2 <= maximum_records <= MAX_TOOL_RUN_JOURNAL_RECORDS
        ):
            raise ValueError("tool run journal limit is invalid")
        self._clock = clock
        self._owner_epoch_factory = owner_epoch_factory or (
            lambda: f"TO-{secrets.token_hex(16)}"
        )
        self._maximum_records = maximum_records
        self._thread_lock = RLock()
        self._journal_token = object()
        self._owner_lease: ToolRunOwnerLease | None = None

    @property
    def path(self) -> Path:
        return self._root / TOOL_RUN_JOURNAL_FILENAME

    @property
    def pending_path(self) -> Path:
        return self._root / f"{TOOL_RUN_JOURNAL_FILENAME}.pending"

    @property
    def lock_path(self) -> Path:
        return self._root / TOOL_RUN_JOURNAL_LOCK_FILENAME

    @property
    def owner_lock_path(self) -> Path:
        return self._root / TOOL_RUN_OWNER_LOCK_FILENAME

    def acquire_owner(self, owner_id: str) -> ToolRunOwnerLease:
        """Acquire one process-lifetime recovery/admission lease without authority."""
        if not isinstance(owner_id, str) or not IDENTITY_RE.fullmatch(owner_id):
            raise ToolRunJournalError("tool run owner identifier is invalid")
        with self._thread_lock:
            if self._owner_lease is not None and self._owner_lease.active:
                raise ToolRunJournalError("tool run journal already has an active owner")
            self._validate_root()
            self._validate_file_path(self.owner_lock_path, allow_missing=True)
            descriptor = -1
            try:
                flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
                descriptor = self._open_protected_file(self.owner_lock_path, flags, 0o600)
                self._acquire_owner_lock(descriptor)
                owner_epoch = self._owner_epoch_factory()
                if not isinstance(owner_epoch, str) or not OWNER_EPOCH_RE.fullmatch(owner_epoch):
                    raise ToolRunJournalError("tool run owner epoch is invalid")
                lease = ToolRunOwnerLease(
                    owner_id, owner_epoch, descriptor, self._journal_token,
                )
                self._owner_lease = lease
                return lease
            except OSError as error:
                if descriptor >= 0:
                    os.close(descriptor)
                raise ToolRunJournalError("tool run journal owner lease is unavailable") from error
            except Exception:
                if descriptor >= 0:
                    try:
                        self._release_owner_lock(descriptor)
                    except OSError:
                        pass
                    os.close(descriptor)
                raise

    def release_owner(self, owner: ToolRunOwnerLease) -> None:
        """Release this process's owner lease; it never changes admitted history."""
        with self._thread_lock:
            self._require_owner(owner)
            try:
                self._release_owner_lock(owner._descriptor)
            except OSError as error:
                raise ToolRunJournalError("tool run journal owner lease cannot be released") from error
            finally:
                os.close(owner._descriptor)
                owner._released = True
                self._owner_lease = None

    def records(self) -> tuple[ToolRunRecord, ...]:
        with self._locked():
            self._recover_pending_locked()
            return tuple(self._read_records(self.path))

    def record_intent(
        self, invocation: ToolInvocation, *, owner: ToolRunOwnerLease,
    ) -> ToolRunRecord:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("tool run invocation is invalid")
        fingerprint = _invocation_fingerprint(invocation)
        with self._thread_lock:
            self._require_owner(owner)
            with self._locked():
                records = self._load_locked()
                existing = self._run_history(records, invocation.invocation_id)
                if existing:
                    if existing[0].binding_fingerprint != fingerprint:
                        raise ToolRunReplayError(
                            "tool run identifier conflicts with historical admission"
                        )
                    raise ToolRunReplayError("tool run identifier was already admitted")
                record = ToolRunRecord(
                    len(records) + 1, "intent", invocation.invocation_id, invocation.tool_id,
                    invocation.tool_version, invocation.session_instance_id, fingerprint,
                    owner.owner_id, owner.owner_epoch, invocation.expires_at,
                    "awaiting_approval", "submitted", _valid_timestamp(self._clock(), "clock"),
                )
                self._replace_locked(records + [record])
                return record

    def record_outcome(
        self, invocation: ToolInvocation, *, owner: ToolRunOwnerLease,
        state: str, reason: str,
    ) -> ToolRunRecord:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("tool run invocation is invalid")
        if state not in TERMINAL_RUN_STATES or reason not in RUN_STATE_REASONS.get(state, ()):
            raise ToolRunJournalError("tool run outcome is invalid")
        fingerprint = _invocation_fingerprint(invocation)
        with self._thread_lock:
            self._require_owner(owner)
            with self._locked():
                records = self._load_locked()
                history = self._run_history(records, invocation.invocation_id)
                if not history:
                    raise ToolRunJournalError("tool run intent is missing")
                intent = history[0]
                if (
                    intent.binding_fingerprint != fingerprint
                    or intent.owner_id != owner.owner_id
                    or intent.owner_epoch != owner.owner_epoch
                ):
                    raise ToolRunJournalError("tool run outcome conflicts with intent ownership")
                if len(history) > 1:
                    outcome = history[-1]
                    if outcome.state == state and outcome.reason == reason:
                        return outcome
                    raise ToolRunJournalError("tool run already has a conflicting outcome")
                outcome = ToolRunRecord(
                    len(records) + 1, "outcome", intent.run_id, intent.tool_id,
                    intent.tool_version, intent.session_instance_id, intent.binding_fingerprint,
                    intent.owner_id, intent.owner_epoch, intent.expires_at, state, reason,
                    _valid_timestamp(self._clock(), "clock"),
                )
                self._replace_locked(records + [outcome])
                return outcome

    def reconcile(
        self, *, owner: ToolRunOwnerLease, now: float | None = None,
    ) -> tuple[ToolRunRecord, ...]:
        """Fence expired/current or prior-owner intents; never restore authority."""
        timestamp = _valid_timestamp(self._clock() if now is None else now, "reconciliation time")
        with self._thread_lock:
            self._require_owner(owner)
            with self._locked():
                records = self._load_locked()
                unresolved: list[ToolRunRecord] = []
                seen: dict[str, list[ToolRunRecord]] = {}
                for record in records:
                    seen.setdefault(record.run_id, []).append(record)
                for history in seen.values():
                    if len(history) != 1:
                        continue
                    intent = history[0]
                    same_owner = (
                        intent.owner_id == owner.owner_id
                        and intent.owner_epoch == owner.owner_epoch
                    )
                    if same_owner and timestamp < intent.expires_at:
                        continue
                    reason = (
                        "owner_session_expired" if same_owner else "restart_reconciliation"
                    )
                    unresolved.append(ToolRunRecord(
                        len(records) + len(unresolved) + 1, "outcome", intent.run_id,
                        intent.tool_id, intent.tool_version, intent.session_instance_id,
                        intent.binding_fingerprint, intent.owner_id, intent.owner_epoch,
                        intent.expires_at, "outcome_unknown", reason, timestamp,
                    ))
                if unresolved:
                    self._replace_locked(records + unresolved)
                return tuple(unresolved)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._thread_lock:
            self._validate_root()
            self._validate_file_path(self.lock_path, allow_missing=True)
            try:
                flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
                descriptor = self._open_protected_file(self.lock_path, flags, 0o600)
            except OSError as error:
                raise ToolRunJournalError("tool run journal lock cannot be acquired") from error
            try:
                self._acquire_lock(descriptor)
                yield
            except OSError as error:
                raise ToolRunJournalError("tool run journal is busy or unavailable") from error
            finally:
                try:
                    self._release_lock(descriptor)
                finally:
                    os.close(descriptor)

    @staticmethod
    def _acquire_lock(descriptor: int) -> None:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            return
        import msvcrt  # pragma: no cover - Windows only.
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)

    @staticmethod
    def _release_lock(descriptor: int) -> None:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return
        import msvcrt  # pragma: no cover - Windows only.
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

    @staticmethod
    def _acquire_owner_lock(descriptor: int) -> None:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        import msvcrt  # pragma: no cover - Windows only.
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)

    @staticmethod
    def _release_owner_lock(descriptor: int) -> None:
        ToolRunJournal._release_lock(descriptor)

    def _require_owner(self, owner: ToolRunOwnerLease) -> None:
        if (
            not isinstance(owner, ToolRunOwnerLease)
            or owner._journal_token is not self._journal_token
            or self._owner_lease is not owner
            or not owner.active
        ):
            raise ToolRunJournalError("tool run journal owner lease is invalid or inactive")
        try:
            self._validate_open_file(self.owner_lock_path, owner._descriptor)
        except (OSError, ToolRunJournalError) as error:
            raise ToolRunJournalError("tool run journal owner lease is invalid or inactive") from error

    def _load_locked(self) -> list[ToolRunRecord]:
        self._recover_pending_locked()
        return self._read_records(self.path)

    def _validate_root(self) -> None:
        try:
            metadata = os.lstat(self._root)
        except OSError as error:
            raise ToolRunJournalError("tool run journal root is unavailable") from error
        if _is_reparse_or_symlink(self._root, metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise ToolRunJournalError("tool run journal root is not a protected directory")
        if os.name == "posix" and (
            metadata.st_uid != os.geteuid()
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise ToolRunJournalError("tool run journal root permissions are unsafe")

    @staticmethod
    def _validate_file_path(path: Path, *, allow_missing: bool) -> None:
        if not os.path.lexists(path):
            if allow_missing:
                return
            raise ToolRunJournalError("tool run journal file is unavailable")
        try:
            metadata = os.lstat(path)
        except OSError as error:
            raise ToolRunJournalError("tool run journal path cannot be inspected") from error
        if _is_reparse_or_symlink(path, metadata) or not stat.S_ISREG(metadata.st_mode):
            raise ToolRunJournalError("tool run journal path is not a protected regular file")
        if metadata.st_nlink != 1:
            raise ToolRunJournalError("tool run journal path has multiple links")

    @classmethod
    def _validate_open_file(cls, path: Path, descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ToolRunJournalError("tool run journal open file is unsafe")
        try:
            path_metadata = os.lstat(path)
        except OSError as error:
            raise ToolRunJournalError("tool run journal path changed during open") from error
        if (
            _is_reparse_or_symlink(path, path_metadata)
            or path_metadata.st_dev != metadata.st_dev
            or path_metadata.st_ino != metadata.st_ino
        ):
            raise ToolRunJournalError("tool run journal path changed during open")

    @classmethod
    def _open_protected_file(cls, path: Path, flags: int, mode: int = 0o600) -> int:
        descriptor = os.open(path, flags, mode)
        try:
            cls._validate_open_file(path, descriptor)
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    def _recover_pending_locked(self) -> None:
        if not os.path.lexists(self.pending_path):
            return
        self._validate_file_path(self.pending_path, allow_missing=False)
        pending = self._read_records(self.pending_path)
        current = self._read_records(self.path)
        if pending == current or self._is_prefix(pending, current):
            self.pending_path.unlink()
            self._sync_root_directory()
            return
        if self._is_prefix(current, pending):
            try:
                self._validate_file_path(self.pending_path, allow_missing=False)
                self._validate_file_path(self.path, allow_missing=True)
                os.replace(self.pending_path, self.path)
                self._validate_file_path(self.path, allow_missing=False)
                self._sync_root_directory()
            except OSError as error:
                raise ToolRunJournalError("tool run pending journal cannot be promoted") from error
            return
        raise ToolRunJournalError("tool run pending journal conflicts with authoritative journal")

    def _replace_locked(self, records: list[ToolRunRecord]) -> None:
        retained = self._retain(records)
        try:
            self._validate_root()
            self._validate_file_path(self.pending_path, allow_missing=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
            descriptor = self._open_protected_file(self.pending_path, flags, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                for record in retained:
                    handle.write(json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._validate_file_path(self.pending_path, allow_missing=False)
            self._validate_file_path(self.path, allow_missing=True)
            os.replace(self.pending_path, self.path)
            self._validate_file_path(self.path, allow_missing=False)
            self._sync_root_directory()
        except OSError as error:
            raise ToolRunJournalError("tool run journal cannot be written") from error

    def _retain(self, records: list[ToolRunRecord]) -> list[ToolRunRecord]:
        if len(records) > self._maximum_records:
            raise ToolRunJournalError(
                "tool run journal capacity is exhausted; replay-safe compaction is unavailable"
            )
        return list(records)

    def _sync_root_directory(self) -> None:
        """Persist a replacement directory entry where the platform exposes it."""
        if os.name != "posix":
            # Windows needs a later native worker/storage implementation with
            # documented write-through semantics.  We make no durability claim
            # from an unsupported directory fsync operation here.
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = -1
        try:
            descriptor = os.open(self._root, flags)
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise ToolRunJournalError("tool run journal root changed during synchronization")
            os.fsync(descriptor)
        except OSError as error:
            raise ToolRunJournalError("tool run journal directory cannot be synchronized") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    @staticmethod
    def _run_history(records: list[ToolRunRecord], run_id: str) -> list[ToolRunRecord]:
        return [record for record in records if record.run_id == run_id]

    @staticmethod
    def _is_prefix(prefix: list[ToolRunRecord], values: list[ToolRunRecord]) -> bool:
        return len(prefix) <= len(values) and values[:len(prefix)] == prefix

    def _read_records(self, path: Path) -> list[ToolRunRecord]:
        if not os.path.lexists(path):
            return []
        self._validate_file_path(path, allow_missing=False)
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = self._open_protected_file(path, flags)
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(64 * 1024, MAX_TOOL_RUN_JOURNAL_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_TOOL_RUN_JOURNAL_BYTES:
                    raise ToolRunJournalError("tool run journal size limit exceeded")
            os.close(descriptor)
            descriptor = -1
            try:
                text = b"".join(chunks).decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                raise ToolRunJournalError("tool run journal encoding is invalid") from error
        except OSError as error:
            raise ToolRunJournalError("tool run journal cannot be read") from error
        finally:
            if "descriptor" in locals() and descriptor >= 0:
                os.close(descriptor)
        if text and not text.endswith("\n"):
            raise ToolRunJournalError("tool run journal is truncated")
        records: list[ToolRunRecord] = []
        for line in text.splitlines():
            if len(line.encode("utf-8")) > MAX_TOOL_RUN_RECORD_BYTES:
                raise ToolRunJournalError("tool run journal record size limit exceeded")
            if len(records) >= MAX_TOOL_RUN_JOURNAL_RECORDS:
                raise ToolRunJournalError("tool run journal record limit exceeded")
            try:
                value = json.loads(
                    line,
                    object_pairs_hook=_reject_duplicate_keys,
                    parse_constant=_reject_nonfinite,
                )
                if _json_depth(value) > MAX_TOOL_RUN_JSON_DEPTH:
                    raise ToolRunJournalError("tool run journal JSON depth limit exceeded")
                record = ToolRunRecord.from_dict(value)
            except (json.JSONDecodeError, ToolRunJournalError) as error:
                raise ToolRunJournalError("tool run journal record is invalid") from error
            if record.sequence != len(records) + 1:
                raise ToolRunJournalError("tool run journal sequence is invalid")
            records.append(record)
        histories: dict[str, list[ToolRunRecord]] = {}
        for record in records:
            histories.setdefault(record.run_id, []).append(record)
        for history in histories.values():
            if history[0].kind != "intent" or len(history) > 2 or (len(history) == 2 and history[1].kind != "outcome"):
                raise ToolRunJournalError("tool run journal lifecycle is invalid")
            if len(history) == 2:
                intent, outcome = history
                if (
                    outcome.tool_id != intent.tool_id
                    or outcome.tool_version != intent.tool_version
                    or outcome.session_instance_id != intent.session_instance_id
                    or outcome.binding_fingerprint != intent.binding_fingerprint
                    or outcome.owner_id != intent.owner_id
                    or outcome.owner_epoch != intent.owner_epoch
                    or outcome.expires_at != intent.expires_at
                    or outcome.timestamp < intent.timestamp
                ):
                    raise ToolRunJournalError("tool run journal outcome binding is invalid")
        for previous, current in zip(records, records[1:]):
            if current.timestamp < previous.timestamp:
                raise ToolRunJournalError("tool run journal timestamps are not monotonic")
        return records


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ToolRunJournalError("tool run journal has duplicate keys")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> object:
    raise ToolRunJournalError(f"tool run journal non-finite number is invalid: {value}")


__all__ = [
    "MAX_TOOL_RUN_JOURNAL_BYTES", "MAX_TOOL_RUN_JOURNAL_RECORDS",
    "MAX_TOOL_RUN_JSON_DEPTH", "MAX_TOOL_RUN_RECORD_BYTES", "MAX_TOOL_RUN_RECORDS",
    "RUN_REASONS", "RUN_STATE_REASONS", "TERMINAL_RUN_STATES", "ToolRunJournal",
    "ToolRunJournalError", "ToolRunOwnerLease", "ToolRunRecord", "ToolRunReplayError",
]
