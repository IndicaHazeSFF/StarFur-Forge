"""Local metadata registry for future isolated CYOA adventure workspaces.

This module deliberately creates *only* a registry record and a workspace
manifest.  It does not mount an adventure, call a model, create a database,
write an event log, or touch shared assistant memory.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Callable


REGISTRY_SCHEMA_VERSION = 1
ADVENTURE_SCHEMA_VERSION = 1
REGISTRY_FILENAME = "registry.json"
MANIFEST_FILENAME = "manifest.json"
_MAX_TITLE_LENGTH = 120
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,95}$")


class AdventureRegistryError(ValueError):
    """Base error for an invalid adventure-registry operation."""


class AdventureNotFoundError(AdventureRegistryError):
    """Raised when a requested registered adventure does not exist."""


class AdventureAmbiguousError(AdventureRegistryError):
    """Reserved for future non-exact title resolution."""


def normalize_adventure_title(value: object) -> str:
    """Return a bounded display title; never use a title as a filesystem path."""
    if not isinstance(value, str):
        raise TypeError("adventure title must be a string")
    title = " ".join(value.strip().split())
    if not title:
        raise AdventureRegistryError("adventure title cannot be empty")
    if len(title) > _MAX_TITLE_LENGTH:
        raise AdventureRegistryError(f"adventure title must be at most {_MAX_TITLE_LENGTH} characters")
    return title


def _stable_adventure_id(title: str) -> str:
    """Create a readable opaque ID independent of the workspace path supplied."""
    words = re.findall(r"[a-z0-9]+", title.casefold())
    slug = "-".join(words)[:72] or "adventure"
    digest = hashlib.sha256(title.casefold().encode("utf-8")).hexdigest()[:12]
    adventure_id = f"{slug}-{digest}"
    if not _ID_PATTERN.fullmatch(adventure_id):  # Defensive invariant for future edits.
        raise AdventureRegistryError("generated adventure identifier is invalid")
    return adventure_id


@dataclass(frozen=True)
class AdventureRecord:
    """Public, small registry entry; story state remains outside this record."""

    adventure_id: str
    title: str
    created_at: str
    status: str = "available"

    def __post_init__(self) -> None:
        if not isinstance(self.adventure_id, str) or not _ID_PATTERN.fullmatch(self.adventure_id):
            raise AdventureRegistryError("adventure identifier is invalid")
        object.__setattr__(self, "title", normalize_adventure_title(self.title))
        if not isinstance(self.created_at, str) or not self.created_at:
            raise AdventureRegistryError("adventure creation time is required")
        if self.status != "available":
            raise AdventureRegistryError("unsupported adventure registry status")

    @classmethod
    def from_dict(cls, value: object) -> "AdventureRecord":
        if not isinstance(value, dict):
            raise AdventureRegistryError("registry record must be an object")
        try:
            return cls(
                adventure_id=value["adventure_id"],
                title=value["title"],
                created_at=value["created_at"],
                status=value.get("status", "available"),
            )
        except KeyError as exc:
            raise AdventureRegistryError("registry record is incomplete") from exc


class AdventureRegistry:
    """Exact-title registry for local, future adventure workspaces.

    ``root`` is supplied by Core in a later mounting slice.  It is not derived
    from a user title or conversation key.  All filesystem writes occur only in
    ``create`` and are constrained beneath that root.
    """

    def __init__(self, root: str | Path, *, now: Callable[[], datetime] | None = None) -> None:
        self.root = Path(root)
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def registry_path(self) -> Path:
        return self.root / REGISTRY_FILENAME

    def workspace_path(self, adventure_id: str) -> Path:
        if not isinstance(adventure_id, str) or not _ID_PATTERN.fullmatch(adventure_id):
            raise AdventureRegistryError("adventure identifier is invalid")
        return self.root / adventure_id

    def list(self) -> list[AdventureRecord]:
        if not self.registry_path.exists():
            return []
        try:
            raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdventureRegistryError("adventure registry cannot be read") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            raise AdventureRegistryError("adventure registry schema is unsupported")
        entries = raw.get("adventures")
        if not isinstance(entries, list):
            raise AdventureRegistryError("adventure registry entries are invalid")
        records = [AdventureRecord.from_dict(entry) for entry in entries]
        if len({record.adventure_id for record in records}) != len(records):
            raise AdventureRegistryError("adventure registry has duplicate identifiers")
        return sorted(records, key=lambda record: (record.title.casefold(), record.adventure_id))

    def resolve_title(self, title: object) -> AdventureRecord:
        """Resolve only an exact normalized title; do not guess or create."""
        normalized = normalize_adventure_title(title)
        matches = [record for record in self.list() if record.title.casefold() == normalized.casefold()]
        if not matches:
            raise AdventureNotFoundError(f"adventure not found: {normalized}")
        if len(matches) > 1:
            raise AdventureAmbiguousError(f"multiple adventures match: {normalized}")
        return matches[0]

    def create(self, title: object) -> AdventureRecord:
        """Create only workspace metadata, rejecting an accidental duplicate world."""
        normalized = normalize_adventure_title(title)
        try:
            existing = self.resolve_title(normalized)
        except AdventureNotFoundError:
            existing = None
        if existing is not None:
            raise AdventureRegistryError(
                f"an adventure named {existing.title!r} already exists; resume it explicitly"
            )

        record = AdventureRecord(
            adventure_id=_stable_adventure_id(normalized),
            title=normalized,
            created_at=self._now().astimezone(UTC).isoformat(),
        )
        workspace = self.workspace_path(record.adventure_id)
        if workspace.exists():
            raise AdventureRegistryError("adventure workspace already exists")
        workspace.mkdir(parents=True, exist_ok=False)
        manifest = {
            "schema_version": ADVENTURE_SCHEMA_VERSION,
            "adventure_id": record.adventure_id,
            "title": record.title,
            "created_at": record.created_at,
            "storage": {
                "event_log": "not_created",
                "database": "not_created",
                "semantic_index": "not_created",
            },
        }
        self._write_json(workspace / MANIFEST_FILENAME, manifest)
        records = self.list() + [record]
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_json(
            self.registry_path,
            {"schema_version": REGISTRY_SCHEMA_VERSION, "adventures": [asdict(item) for item in records]},
        )
        return record

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = [
    "ADVENTURE_SCHEMA_VERSION", "AdventureAmbiguousError", "AdventureNotFoundError",
    "AdventureRecord", "AdventureRegistry", "AdventureRegistryError", "MANIFEST_FILENAME",
    "REGISTRY_FILENAME", "REGISTRY_SCHEMA_VERSION", "normalize_adventure_title",
]
