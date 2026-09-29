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

from pipeline.adventure_initiative import AdventureInitiativeError, AdventureParticipantRoster
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceError


REGISTRY_SCHEMA_VERSION = 1
ADVENTURE_SCHEMA_VERSION = 1
REGISTRY_FILENAME = "registry.json"
MANIFEST_FILENAME = "manifest.json"
RESOURCE_CATALOG_MANIFEST_KEY = "resource_catalog"
PARTICIPANT_ROSTER_MANIFEST_KEY = "participant_roster"
BRANCH_ORIGIN_MANIFEST_KEY = "branch_origin"
_MAX_TITLE_LENGTH = 120
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,95}$")
_CHECKPOINT_ID_PATTERN = re.compile(r"^CP-[0-9]{6}$")
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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

    def resource_catalog(self, record: AdventureRecord) -> AdventureResourceCatalog:
        """Read one validated declared catalog; legacy workspaces have none."""
        manifest = self._read_workspace_manifest(record)
        value = manifest.get(RESOURCE_CATALOG_MANIFEST_KEY)
        if value is None:
            return AdventureResourceCatalog(())
        try:
            return AdventureResourceCatalog.from_dict(value)
        except AdventureResourceError as error:
            raise AdventureRegistryError("adventure resource catalog is invalid") from error

    def configure_resource_catalog(
        self, record: AdventureRecord, catalog: AdventureResourceCatalog,
    ) -> AdventureResourceCatalog:
        """Persist one immutable scenario declaration before an event log exists.

        This is an internal package/Core setup boundary, not a chat command. A
        catalog cannot be rewritten after any authoritative event exists, so a
        later event reducer always has a stable resource schema.
        """
        if not isinstance(catalog, AdventureResourceCatalog):
            raise TypeError("adventure resource catalog must be an AdventureResourceCatalog")
        manifest = self._read_workspace_manifest(record)
        workspace = self.workspace_path(record.adventure_id)
        if (workspace / "events.jsonl").exists():
            raise AdventureRegistryError("resource catalog cannot change after the event log exists")
        existing = manifest.get(RESOURCE_CATALOG_MANIFEST_KEY)
        if existing is not None:
            try:
                loaded = AdventureResourceCatalog.from_dict(existing)
            except AdventureResourceError as error:
                raise AdventureRegistryError("adventure resource catalog is invalid") from error
            if loaded != catalog:
                raise AdventureRegistryError("adventure resource catalog is already configured")
            return loaded
        manifest[RESOURCE_CATALOG_MANIFEST_KEY] = catalog.to_dict()
        self._write_json(workspace / MANIFEST_FILENAME, manifest)
        return catalog

    def participant_roster(self, record: AdventureRecord) -> AdventureParticipantRoster:
        """Read one validated declared roster; legacy workspaces have none."""
        manifest = self._read_workspace_manifest(record)
        value = manifest.get(PARTICIPANT_ROSTER_MANIFEST_KEY)
        if value is None:
            return AdventureParticipantRoster(record.adventure_id, ())
        try:
            return AdventureParticipantRoster.from_dict(record.adventure_id, value)
        except AdventureInitiativeError as error:
            raise AdventureRegistryError("adventure participant roster is invalid") from error

    def configure_participant_roster(
        self, record: AdventureRecord, roster: AdventureParticipantRoster,
    ) -> AdventureParticipantRoster:
        """Persist one immutable scenario roster before an event log exists.

        This is a package/Core setup boundary, not a chat command. Participant
        identities are context labels only; the roster neither grants
        permissions nor creates persona/NPC actions or memory writes.
        """
        if not isinstance(roster, AdventureParticipantRoster):
            raise TypeError("adventure participant roster must be an AdventureParticipantRoster")
        if roster.adventure_id != record.adventure_id:
            raise AdventureRegistryError("adventure participant roster belongs to another workspace")
        manifest = self._read_workspace_manifest(record)
        workspace = self.workspace_path(record.adventure_id)
        if (workspace / "events.jsonl").exists():
            raise AdventureRegistryError("participant roster cannot change after the event log exists")
        existing = manifest.get(PARTICIPANT_ROSTER_MANIFEST_KEY)
        if existing is not None:
            try:
                loaded = AdventureParticipantRoster.from_dict(record.adventure_id, existing)
            except AdventureInitiativeError as error:
                raise AdventureRegistryError("adventure participant roster is invalid") from error
            if loaded != roster:
                raise AdventureRegistryError("adventure participant roster is already configured")
            return loaded
        manifest[PARTICIPANT_ROSTER_MANIFEST_KEY] = roster.to_dict()
        self._write_json(workspace / MANIFEST_FILENAME, manifest)
        return roster

    def configure_branch_origin(
        self, record: AdventureRecord, *, parent_adventure_id: object,
        parent_checkpoint_id: object, parent_event_count: object,
        parent_event_fingerprint: object,
    ) -> dict[str, object]:
        """Record one immutable provenance link for a checkpoint-derived workspace.

        This records lineage only.  It never grants the child access to the
        parent workspace, and it deliberately does not copy a parent's
        checkpoints or later event history.
        """
        origin = self._validated_branch_origin(
            record, parent_adventure_id, parent_checkpoint_id,
            parent_event_count, parent_event_fingerprint,
        )
        manifest = self._read_workspace_manifest(record)
        existing = manifest.get(BRANCH_ORIGIN_MANIFEST_KEY)
        if existing is not None:
            if existing != origin:
                raise AdventureRegistryError("adventure branch origin is already configured")
            return origin
        manifest[BRANCH_ORIGIN_MANIFEST_KEY] = origin
        self._write_json(self.workspace_path(record.adventure_id) / MANIFEST_FILENAME, manifest)
        return origin

    def branch_origin(self, record: AdventureRecord) -> dict[str, object] | None:
        """Return validated immutable lineage metadata, if this workspace has it."""
        manifest = self._read_workspace_manifest(record)
        value = manifest.get(BRANCH_ORIGIN_MANIFEST_KEY)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise AdventureRegistryError("adventure branch origin is invalid")
        try:
            return self._validated_branch_origin(
                record, value["parent_adventure_id"], value["parent_checkpoint_id"],
                value["parent_event_count"], value["parent_event_fingerprint"],
            )
        except KeyError as error:
            raise AdventureRegistryError("adventure branch origin is invalid") from error

    @staticmethod
    def _validated_branch_origin(
        record: AdventureRecord, parent_adventure_id: object,
        parent_checkpoint_id: object, parent_event_count: object,
        parent_event_fingerprint: object,
    ) -> dict[str, object]:
        if not isinstance(parent_adventure_id, str) or not _ID_PATTERN.fullmatch(parent_adventure_id):
            raise AdventureRegistryError("parent adventure identifier is invalid")
        if parent_adventure_id == record.adventure_id:
            raise AdventureRegistryError("an adventure cannot branch from itself")
        if not isinstance(parent_checkpoint_id, str) or not _CHECKPOINT_ID_PATTERN.fullmatch(parent_checkpoint_id):
            raise AdventureRegistryError("parent checkpoint identifier is invalid")
        if not isinstance(parent_event_count, int) or isinstance(parent_event_count, bool) or parent_event_count < 0:
            raise AdventureRegistryError("parent event count is invalid")
        if not isinstance(parent_event_fingerprint, str) or not _FINGERPRINT_PATTERN.fullmatch(parent_event_fingerprint):
            raise AdventureRegistryError("parent event fingerprint is invalid")
        return {
            "parent_adventure_id": parent_adventure_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "parent_event_count": parent_event_count,
            "parent_event_fingerprint": parent_event_fingerprint,
        }

    def _read_workspace_manifest(self, record: AdventureRecord) -> dict[str, object]:
        if not isinstance(record, AdventureRecord):
            raise TypeError("adventure record must be an AdventureRecord")
        try:
            resolved = self.resolve_title(record.title)
        except AdventureRegistryError as error:
            raise AdventureRegistryError("adventure workspace is not registered") from error
        if resolved != record:
            raise AdventureRegistryError("adventure record does not match the registry")
        path = self.workspace_path(record.adventure_id) / MANIFEST_FILENAME
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AdventureRegistryError("adventure manifest cannot be read") from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != ADVENTURE_SCHEMA_VERSION
            or manifest.get("adventure_id") != record.adventure_id
            or manifest.get("title") != record.title
            or not isinstance(manifest.get("storage"), dict)
        ):
            raise AdventureRegistryError("adventure manifest is invalid")
        return manifest

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = [
    "ADVENTURE_SCHEMA_VERSION", "AdventureAmbiguousError", "AdventureNotFoundError",
    "AdventureRecord", "AdventureRegistry", "AdventureRegistryError", "MANIFEST_FILENAME",
    "BRANCH_ORIGIN_MANIFEST_KEY", "REGISTRY_FILENAME", "REGISTRY_SCHEMA_VERSION", "RESOURCE_CATALOG_MANIFEST_KEY", "normalize_adventure_title",
]
