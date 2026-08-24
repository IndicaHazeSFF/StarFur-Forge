"""Explicit user mapping of staged document candidates to future adventure uses.

Mappings are planning records only. They make no event/state/memory write and
cannot infer a destination from candidate prose or model output.
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

from pipeline.adventure_import import AdventureImportError, AdventureImportLog
from pipeline.adventure_registry import AdventureRecord, AdventureRegistry, AdventureRegistryError

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows-only fallback.
    fcntl = None


IMPORT_MAPPING_SCHEMA_VERSION = 1
IMPORT_MAPPING_FILENAME = "import_mappings.jsonl"
IMPORT_MAPPING_LOCK_FILENAME = ".import_mappings.write.lock"
IMPORT_MAPPING_DESTINATIONS = frozenset({"premise", "state", "relationship", "knowledge", "resource", "exclude"})
_MAPPING_ID = re.compile(r"^IM-[0-9]{6}$")
_IMPORT_ID = re.compile(r"^AI-[0-9]{6}$")
_CANDIDATE_ID = re.compile(r"^C-[0-9]{3,}$")


class AdventureImportMappingError(ValueError):
    """Raised when a candidate mapping is malformed or unsafe."""


@dataclass(frozen=True)
class AdventureImportMapping:
    sequence: int
    mapping_id: str
    import_id: str
    candidate_id: str
    destination: str
    mapped_at: str
    schema_version: int = IMPORT_MAPPING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureImportMappingError("import mapping sequence is invalid")
        if self.mapping_id != f"IM-{self.sequence:06d}" or not _MAPPING_ID.fullmatch(self.mapping_id):
            raise AdventureImportMappingError("import mapping identifier is invalid")
        if not isinstance(self.import_id, str) or not _IMPORT_ID.fullmatch(self.import_id):
            raise AdventureImportMappingError("import mapping import identifier is invalid")
        if not isinstance(self.candidate_id, str) or not _CANDIDATE_ID.fullmatch(self.candidate_id):
            raise AdventureImportMappingError("import mapping candidate identifier is invalid")
        if self.destination not in IMPORT_MAPPING_DESTINATIONS:
            raise AdventureImportMappingError("import mapping destination is unsupported")
        if not isinstance(self.mapped_at, str) or not self.mapped_at:
            raise AdventureImportMappingError("import mapping time is required")
        try:
            datetime.fromisoformat(self.mapped_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise AdventureImportMappingError("import mapping time is invalid") from error
        if self.schema_version != IMPORT_MAPPING_SCHEMA_VERSION:
            raise AdventureImportMappingError("import mapping schema is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version, "sequence": self.sequence,
            "mapping_id": self.mapping_id, "import_id": self.import_id,
            "candidate_id": self.candidate_id, "destination": self.destination,
            "mapped_at": self.mapped_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureImportMapping":
        if not isinstance(value, dict) or set(value) != {"schema_version", "sequence", "mapping_id", "import_id", "candidate_id", "destination", "mapped_at"}:
            raise AdventureImportMappingError("import mapping fields are invalid")
        return cls(**value)


class AdventureImportMappingLog:
    """Append-only, latest-choice-wins mapping history for one workspace."""

    def __init__(self, registry: AdventureRegistry, record: AdventureRecord, *, now: Callable[[], datetime] | None = None) -> None:
        if not isinstance(registry, AdventureRegistry) or not isinstance(record, AdventureRecord):
            raise TypeError("registry and record must be adventure registry records")
        try:
            if registry.resolve_title(record.title) != record:
                raise AdventureImportMappingError("adventure record does not match the registry")
        except AdventureRegistryError as error:
            raise AdventureImportMappingError("adventure workspace is not registered") from error
        self._registry, self._record = registry, record
        self._workspace = registry.workspace_path(record.adventure_id)
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        return self._workspace / IMPORT_MAPPING_FILENAME

    @property
    def lock_path(self) -> Path:
        return self._workspace / IMPORT_MAPPING_LOCK_FILENAME

    def records(self) -> list[AdventureImportMapping]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise AdventureImportMappingError("import mapping log cannot be read") from error
        result = []
        for sequence, line in enumerate(lines, 1):
            try:
                item = AdventureImportMapping.from_dict(json.loads(line))
            except (json.JSONDecodeError, AdventureImportMappingError) as error:
                raise AdventureImportMappingError("import mapping log is invalid") from error
            if item.sequence != sequence:
                raise AdventureImportMappingError("import mapping log sequence is invalid")
            result.append(item)
        return result

    def current(self, import_id: object) -> dict[str, AdventureImportMapping]:
        normalized = self._validate_candidate(import_id, None)[0]
        return {item.candidate_id: item for item in self.records() if item.import_id == normalized}

    def map(self, import_id: object, candidate_id: object, destination: object) -> AdventureImportMapping:
        normalized_import, normalized_candidate = self._validate_candidate(import_id, candidate_id)
        if not isinstance(destination, str) or destination.casefold() not in IMPORT_MAPPING_DESTINATIONS:
            raise AdventureImportMappingError("import mapping destination is unsupported")
        destination = destination.casefold()
        with self._guard():
            existing = self.records()
            current = {item.candidate_id: item for item in existing if item.import_id == normalized_import}.get(normalized_candidate)
            if current is not None and current.destination == destination:
                return current
            item = AdventureImportMapping(
                sequence=len(existing) + 1, mapping_id=f"IM-{len(existing) + 1:06d}",
                import_id=normalized_import, candidate_id=normalized_candidate, destination=destination,
                mapped_at=self._now().astimezone(UTC).isoformat(),
            )
            self._replace((*existing, item))
            return item

    def _validate_candidate(self, import_id: object, candidate_id: object | None) -> tuple[str, str | None]:
        if not isinstance(import_id, str) or not _IMPORT_ID.fullmatch(import_id.strip().upper()):
            raise AdventureImportMappingError("import mapping import identifier is invalid")
        import_id = import_id.strip().upper()
        try:
            record = next(item for item in AdventureImportLog(self._registry, self._record).records() if item.import_id == import_id)
        except StopIteration as error:
            raise AdventureImportMappingError("staged adventure import not found") from error
        if candidate_id is None:
            return import_id, None
        if not isinstance(candidate_id, str) or not _CANDIDATE_ID.fullmatch(candidate_id.strip().upper()):
            raise AdventureImportMappingError("import mapping candidate identifier is invalid")
        candidate_id = candidate_id.strip().upper()
        if candidate_id not in {candidate["candidate_id"] for candidate in record.candidates}:
            raise AdventureImportMappingError("staged import candidate not found")
        return import_id, candidate_id

    @contextmanager
    def _guard(self) -> Iterator[None]:
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR)
        try:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:  # pragma: no cover
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"\0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            os.close(descriptor)
            raise AdventureImportMappingError("import mapping is busy") from error
        try:
            yield
        finally:
            try:
                if fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                else:  # pragma: no cover
                    import msvcrt
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            finally:
                os.close(descriptor)

    def _replace(self, records: tuple[AdventureImportMapping, ...]) -> None:
        temporary = self.path.with_suffix(".jsonl.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                for item in records:
                    handle.write(json.dumps(item.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise AdventureImportMappingError("import mapping log cannot be written") from error


__all__ = ["AdventureImportMapping", "AdventureImportMappingError", "AdventureImportMappingLog", "IMPORT_MAPPING_DESTINATIONS"]
