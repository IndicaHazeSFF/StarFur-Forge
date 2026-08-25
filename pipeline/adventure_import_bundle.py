"""Non-canonical grouping for related reviewed adventure-document imports.

Bundles make a user-selected set such as ``details.md`` plus an exported
conversation inspectable as one import unit.  They never create story events,
state, replay facts, memories, or prompt context.
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


IMPORT_BUNDLE_SCHEMA_VERSION = 1
IMPORT_BUNDLE_FILENAME = "import_bundles.jsonl"
IMPORT_BUNDLE_LOCK_FILENAME = ".import_bundles.write.lock"
_BUNDLE_ID = re.compile(r"^AB-[0-9]{6}$")
_IMPORT_ID = re.compile(r"^AI-[0-9]{6}$")
_MAX_TITLE_LENGTH = 120
_MAX_IMPORTS = 32


class AdventureImportBundleError(ValueError):
    """Raised when non-canonical reviewed-document grouping is invalid."""


def _title(value: object) -> str:
    if not isinstance(value, str):
        raise AdventureImportBundleError("import bundle title must be text")
    result = " ".join(value.split())
    if not result or len(result) > _MAX_TITLE_LENGTH:
        raise AdventureImportBundleError("import bundle title is invalid")
    return result


def _import_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or not 2 <= len(value) <= _MAX_IMPORTS:
        raise AdventureImportBundleError("import bundle must contain between 2 and 32 imports")
    result = []
    for item in value:
        if not isinstance(item, str) or not _IMPORT_ID.fullmatch(item.strip().upper()):
            raise AdventureImportBundleError("import bundle import identifier is invalid")
        result.append(item.strip().upper())
    if len(set(result)) != len(result):
        raise AdventureImportBundleError("import bundle import identifiers must be unique")
    return tuple(result)


@dataclass(frozen=True)
class AdventureImportBundle:
    sequence: int
    bundle_id: str
    title: str
    import_ids: tuple[str, ...]
    created_at: str
    schema_version: int = IMPORT_BUNDLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureImportBundleError("import bundle sequence is invalid")
        if self.bundle_id != f"AB-{self.sequence:06d}" or not _BUNDLE_ID.fullmatch(self.bundle_id):
            raise AdventureImportBundleError("import bundle identifier is invalid")
        object.__setattr__(self, "title", _title(self.title))
        object.__setattr__(self, "import_ids", _import_ids(self.import_ids))
        if not isinstance(self.created_at, str) or not self.created_at:
            raise AdventureImportBundleError("import bundle time is required")
        try:
            datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise AdventureImportBundleError("import bundle time is invalid") from error
        if self.schema_version != IMPORT_BUNDLE_SCHEMA_VERSION:
            raise AdventureImportBundleError("import bundle schema is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "bundle_id": self.bundle_id,
            "title": self.title,
            "import_ids": list(self.import_ids),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureImportBundle":
        if not isinstance(value, dict) or set(value) != {
            "schema_version", "sequence", "bundle_id", "title", "import_ids", "created_at",
        } or not isinstance(value["import_ids"], list):
            raise AdventureImportBundleError("import bundle fields are invalid")
        return cls(
            schema_version=value["schema_version"], sequence=value["sequence"],
            bundle_id=value["bundle_id"], title=value["title"],
            import_ids=tuple(value["import_ids"]), created_at=value["created_at"],
        )


class AdventureImportBundleLog:
    """Append-only, user-authored grouping for staged review imports."""

    def __init__(self, registry: AdventureRegistry, record: AdventureRecord, *, now: Callable[[], datetime] | None = None) -> None:
        if not isinstance(registry, AdventureRegistry) or not isinstance(record, AdventureRecord):
            raise TypeError("registry and record must be adventure registry records")
        try:
            if registry.resolve_title(record.title) != record:
                raise AdventureImportBundleError("adventure record does not match the registry")
        except AdventureRegistryError as error:
            raise AdventureImportBundleError("adventure workspace is not registered") from error
        self._registry, self._record = registry, record
        self._workspace = registry.workspace_path(record.adventure_id)
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        return self._workspace / IMPORT_BUNDLE_FILENAME

    @property
    def lock_path(self) -> Path:
        return self._workspace / IMPORT_BUNDLE_LOCK_FILENAME

    def records(self) -> list[AdventureImportBundle]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            raise AdventureImportBundleError("import bundle log cannot be read") from error
        result = []
        for sequence, line in enumerate(lines, 1):
            try:
                bundle = AdventureImportBundle.from_dict(json.loads(line))
            except (json.JSONDecodeError, AdventureImportBundleError) as error:
                raise AdventureImportBundleError("import bundle log is invalid") from error
            if bundle.sequence != sequence:
                raise AdventureImportBundleError("import bundle log sequence is invalid")
            result.append(bundle)
        return result

    def create(self, title: object, import_ids: object) -> AdventureImportBundle:
        title, import_ids = _title(title), _import_ids(import_ids)
        try:
            staged = {item.import_id for item in AdventureImportLog(self._registry, self._record).records()}
        except AdventureImportError as error:
            raise AdventureImportBundleError("staged adventure imports cannot be read") from error
        if not set(import_ids).issubset(staged):
            raise AdventureImportBundleError("import bundle references a missing staged import")
        with self._guard():
            existing = self.records()
            for bundle in existing:
                if bundle.title.casefold() == title.casefold():
                    if bundle.title == title and bundle.import_ids == import_ids:
                        return bundle
                    raise AdventureImportBundleError("an import bundle with that title already exists")
            bundle = AdventureImportBundle(
                sequence=len(existing) + 1, bundle_id=f"AB-{len(existing) + 1:06d}",
                title=title, import_ids=import_ids,
                created_at=self._now().astimezone(UTC).isoformat(),
            )
            self._replace((*existing, bundle))
            return bundle

    def inspect(self, identifier: object) -> AdventureImportBundle:
        if not isinstance(identifier, str) or not identifier.strip():
            raise AdventureImportBundleError("import bundle identifier is required")
        requested = identifier.strip()
        for bundle in self.records():
            if bundle.bundle_id == requested.upper():
                return bundle
        raise AdventureImportBundleError("import bundle not found")

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
            raise AdventureImportBundleError("import bundle is busy") from error
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

    def _replace(self, records: tuple[AdventureImportBundle, ...]) -> None:
        temporary = self.path.with_suffix(".jsonl.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                for bundle in records:
                    handle.write(json.dumps(bundle.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise AdventureImportBundleError("import bundle log cannot be written") from error


__all__ = [
    "AdventureImportBundle", "AdventureImportBundleError", "AdventureImportBundleLog",
    "IMPORT_BUNDLE_FILENAME",
]
