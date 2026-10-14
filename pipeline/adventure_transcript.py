"""Typed transcript records kept separate from authoritative adventure events.

This first slice is intentionally pure: it validates one bounded record for
what was presented in an adventure without writing files, capturing chat,
deriving story facts, or affecting replay/state.  A later explicitly
permissioned store may retain these records according to a transcript policy.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Callable, Iterator

from pipeline.adventure_registry import AdventureRecord, AdventureRegistry, AdventureRegistryError

try:  # POSIX production (including WSL); Windows uses the fallback below.
    import fcntl
except ImportError:  # pragma: no cover - exercised only on Windows hosts.
    fcntl = None


TRANSCRIPT_SCHEMA_VERSION = 1
TRANSCRIPT_ROLES = frozenset({"user", "narrator"})
TRANSCRIPT_SOURCE_CORE_EXPLICIT = "core_explicit"
MAX_TRANSCRIPT_TEXT_LENGTH = 8_000
MAX_TRANSCRIPT_APPEND_RECORDS = 16
TRANSCRIPT_FILENAME = "transcript.jsonl"
TRANSCRIPT_WRITE_LOCK_FILENAME = ".transcript.write.lock"
_RECORD_ID_PATTERN = re.compile(r"^AT-[0-9]{6}$")


class AdventureTranscriptError(ValueError):
    """Raised when a transcript record is malformed or unsafe to retain."""


def _required_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AdventureTranscriptError(f"transcript {field} must be text")
    text = value.strip()
    if not text:
        raise AdventureTranscriptError(f"transcript {field} cannot be empty")
    if "\x00" in text:
        raise AdventureTranscriptError(f"transcript {field} cannot contain NUL")
    if len(text) > maximum:
        raise AdventureTranscriptError(f"transcript {field} must be at most {maximum} characters")
    return text


@dataclass(frozen=True)
class AdventureTranscriptRecord:
    """One bounded presentation record, never an authoritative story event."""

    sequence: int
    record_id: str
    role: str
    text: str
    recorded_at: str
    source: str = TRANSCRIPT_SOURCE_CORE_EXPLICIT
    schema_version: int = TRANSCRIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureTranscriptError("transcript sequence must be a positive integer")
        expected_id = f"AT-{self.sequence:06d}"
        if not isinstance(self.record_id, str) or not _RECORD_ID_PATTERN.fullmatch(self.record_id):
            raise AdventureTranscriptError("transcript identifier is invalid")
        if self.record_id != expected_id:
            raise AdventureTranscriptError("transcript identifier does not match its sequence")
        if not isinstance(self.role, str) or self.role not in TRANSCRIPT_ROLES:
            raise AdventureTranscriptError("transcript role is unsupported")
        object.__setattr__(self, "text", _required_text(
            self.text, field="text", maximum=MAX_TRANSCRIPT_TEXT_LENGTH,
        ))
        if not isinstance(self.recorded_at, str) or not self.recorded_at:
            raise AdventureTranscriptError("transcript recording time is required")
        try:
            datetime.fromisoformat(self.recorded_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise AdventureTranscriptError("transcript recording time is invalid") from error
        if self.source != TRANSCRIPT_SOURCE_CORE_EXPLICIT:
            raise AdventureTranscriptError("transcript source is not permitted")
        if self.schema_version != TRANSCRIPT_SCHEMA_VERSION:
            raise AdventureTranscriptError("transcript schema is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "record_id": self.record_id,
            "role": self.role,
            "text": self.text,
            "recorded_at": self.recorded_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureTranscriptRecord":
        if not isinstance(value, dict):
            raise AdventureTranscriptError("transcript record must be an object")
        expected_fields = {
            "schema_version", "sequence", "record_id", "role", "text", "recorded_at", "source",
        }
        if set(value) != expected_fields:
            raise AdventureTranscriptError("transcript record fields are invalid")
        return cls(
            schema_version=value["schema_version"],
            sequence=value["sequence"],
            record_id=value["record_id"],
            role=value["role"],
            text=value["text"],
            recorded_at=value["recorded_at"],
            source=value["source"],
        )


class AdventureTranscriptLog:
    """Append-only presentation storage for one registered adventure workspace.

    The transcript is intentionally not tied to the adventure manifest or
    event-log recovery path: it is optional, never authoritative, and cannot
    make a workspace claim story state it does not possess. Atomic replacement
    keeps a partial write from becoming readable transcript history.
    """

    def __init__(
        self, registry: AdventureRegistry, record: AdventureRecord,
        *, now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(registry, AdventureRegistry):
            raise TypeError("registry must be an AdventureRegistry")
        if not isinstance(record, AdventureRecord):
            raise TypeError("record must be an AdventureRecord")
        try:
            resolved = registry.resolve_title(record.title)
        except AdventureRegistryError as error:
            raise AdventureTranscriptError("adventure workspace is not registered") from error
        if resolved != record:
            raise AdventureTranscriptError("adventure record does not match the registry")
        self._workspace = registry.workspace_path(record.adventure_id)
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        return self._workspace / TRANSCRIPT_FILENAME

    @property
    def lock_path(self) -> Path:
        return self._workspace / TRANSCRIPT_WRITE_LOCK_FILENAME

    def records(self) -> list[AdventureTranscriptRecord]:
        """Return the validated optional transcript without creating storage."""
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise AdventureTranscriptError("adventure transcript cannot be read") from error
        records: list[AdventureTranscriptRecord] = []
        for expected_sequence, line in enumerate(lines, start=1):
            try:
                record = AdventureTranscriptRecord.from_dict(json.loads(line))
            except (json.JSONDecodeError, AdventureTranscriptError) as error:
                raise AdventureTranscriptError("adventure transcript is invalid") from error
            if record.sequence != expected_sequence:
                raise AdventureTranscriptError("adventure transcript sequence is invalid")
            records.append(record)
        return records

    def append(self, role: object, text: object) -> AdventureTranscriptRecord:
        """Explicitly append presentation text without creating a story event."""
        return self.append_many(((role, text),))[0]

    def append_many(self, entries: object) -> tuple[AdventureTranscriptRecord, ...]:
        """Atomically append one bounded explicit presentation batch.

        Every entry is validated before the one replacement write, so a
        malformed second item cannot leave a partial transcript pair behind.
        This remains presentation-only storage and never touches the event log.
        """
        if not isinstance(entries, tuple) or not 1 <= len(entries) <= MAX_TRANSCRIPT_APPEND_RECORDS:
            raise AdventureTranscriptError("transcript append batch is invalid")
        if any(not isinstance(entry, tuple) or len(entry) != 2 for entry in entries):
            raise AdventureTranscriptError("transcript append batch is invalid")
        with self._write_guard():
            existing = self.records()
            recorded_at = self._now().astimezone(UTC).isoformat()
            records = tuple(
                AdventureTranscriptRecord(
                    sequence=len(existing) + sequence,
                    record_id=f"AT-{len(existing) + sequence:06d}",
                    role=role,
                    text=text,
                    recorded_at=recorded_at,
                )
                for sequence, (role, text) in enumerate(entries, start=1)
            )
            self._replace_records((*existing, *records))
            return records

    @contextmanager
    def _write_guard(self) -> Iterator[None]:
        """Fail closed if another transcript writer is active for this workspace."""
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR)
        except OSError as error:
            raise AdventureTranscriptError("adventure transcript lock cannot be acquired") from error
        try:
            self._acquire_advisory_lock(descriptor)
        except OSError as error:
            os.close(descriptor)
            raise AdventureTranscriptError("adventure transcript is busy") from error
        try:
            yield
        finally:
            try:
                self._release_advisory_lock(descriptor)
            finally:
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    @staticmethod
    def _acquire_advisory_lock(descriptor: int) -> None:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        import msvcrt  # pragma: no cover - Windows-only standard-library fallback.

        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)

    @staticmethod
    def _release_advisory_lock(descriptor: int) -> None:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return
        import msvcrt  # pragma: no cover - Windows-only standard-library fallback.

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

    def _replace_records(self, records: tuple[AdventureTranscriptRecord, ...]) -> None:
        temporary = self.path.with_suffix(".jsonl.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                for record in records:
                    handle.write(json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise AdventureTranscriptError("adventure transcript cannot be written") from error


__all__ = [
    "AdventureTranscriptError",
    "AdventureTranscriptLog",
    "AdventureTranscriptRecord",
    "MAX_TRANSCRIPT_APPEND_RECORDS",
    "MAX_TRANSCRIPT_TEXT_LENGTH",
    "TRANSCRIPT_FILENAME",
    "TRANSCRIPT_ROLES",
    "TRANSCRIPT_SCHEMA_VERSION",
    "TRANSCRIPT_SOURCE_CORE_EXPLICIT",
    "TRANSCRIPT_WRITE_LOCK_FILENAME",
]
