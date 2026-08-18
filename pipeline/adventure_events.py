"""Validated append-only event storage for one isolated adventure workspace.

This module is deliberately a storage primitive, not a narrator or state
machine. Core must explicitly provide a validated event; ordinary chat,
shared assistant memory, and providers cannot write this log. Derived state
and prompt mounting are separate later slices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Callable

from pipeline.adventure_registry import AdventureRecord, AdventureRegistry, AdventureRegistryError, MANIFEST_FILENAME


EVENT_LOG_SCHEMA_VERSION = 1
EVENT_LOG_FILENAME = "events.jsonl"
EVENT_SOURCE_CORE_EXPLICIT = "core_explicit"
EVENT_TYPES = frozenset({
    "choice", "discovery", "promise", "lie", "relationship_change", "emotional_transition",
    "state_change", "unresolved_hook", "character_knowledge", "inventory_change", "location_change",
})
_MAX_SUMMARY_LENGTH = 500
_MAX_DETAILS_LENGTH = 4_000
_MAX_STATE_VALUE_LENGTH = 500
_STATE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_RELATIONSHIP_SUBJECT_LENGTH = 96
_MAX_RELATIONSHIP_VALUE_LENGTH = 160
_RELATIONSHIP_DIMENSION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_KNOWLEDGE_SUBJECT_LENGTH = 96
_MAX_KNOWLEDGE_FACT_LENGTH = 500
KNOWLEDGE_STATUSES = frozenset({"knows", "believes", "uncertain"})


class AdventureEventLogError(ValueError):
    """Raised when an adventure event log cannot be safely read or changed."""


def _required_text(value: object, *, field: str, maximum: int, collapse: bool = False) -> str:
    if not isinstance(value, str):
        raise AdventureEventLogError(f"event {field} must be text")
    normalized = " ".join(value.split()) if collapse else value.strip()
    if not normalized:
        raise AdventureEventLogError(f"event {field} cannot be empty")
    if len(normalized) > maximum:
        raise AdventureEventLogError(f"event {field} must be at most {maximum} characters")
    return normalized


def _optional_text(value: object, *, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    return _required_text(value, field=field, maximum=maximum)


def normalize_state_key(value: object) -> str:
    """Normalize one explicit story-state key; it is never derived from prose."""
    if not isinstance(value, str):
        raise AdventureEventLogError("state key must be text")
    key = value.strip().casefold()
    if not _STATE_KEY_PATTERN.fullmatch(key):
        raise AdventureEventLogError("state key must use lowercase letters, numbers, and underscores")
    return key


def normalize_relationship_dimension(value: object) -> str:
    """Normalize one explicit relationship dimension; it is never inferred."""
    if not isinstance(value, str):
        raise AdventureEventLogError("relationship dimension must be text")
    dimension = value.strip().casefold()
    if not _RELATIONSHIP_DIMENSION_PATTERN.fullmatch(dimension):
        raise AdventureEventLogError("relationship dimension must use lowercase letters, numbers, and underscores")
    return dimension


def normalize_knowledge_status(value: object) -> str:
    """Normalize a character's explicit epistemic status."""
    if not isinstance(value, str):
        raise AdventureEventLogError("knowledge status must be text")
    status = value.strip().casefold()
    if status not in KNOWLEDGE_STATUSES:
        allowed = ", ".join(sorted(KNOWLEDGE_STATUSES))
        raise AdventureEventLogError(f"knowledge status must be one of: {allowed}")
    return status


@dataclass(frozen=True)
class AdventureEvent:
    """One authoritative, replayable story fact in sequence order."""

    sequence: int
    event_id: str
    event_type: str
    summary: str
    details: str | None
    recorded_at: str
    state_key: str | None = None
    state_value: str | None = None
    relationship_subject: str | None = None
    relationship_dimension: str | None = None
    relationship_value: str | None = None
    knowledge_subject: str | None = None
    knowledge_status: str | None = None
    knowledge_fact: str | None = None
    source: str = EVENT_SOURCE_CORE_EXPLICIT
    schema_version: int = EVENT_LOG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureEventLogError("event sequence must be a positive integer")
        if self.event_id != f"AE-{self.sequence:06d}":
            raise AdventureEventLogError("event identifier does not match its sequence")
        if self.event_type not in EVENT_TYPES:
            raise AdventureEventLogError("event type is unsupported")
        object.__setattr__(self, "summary", _required_text(
            self.summary, field="summary", maximum=_MAX_SUMMARY_LENGTH, collapse=True
        ))
        object.__setattr__(self, "details", _optional_text(
            self.details, field="details", maximum=_MAX_DETAILS_LENGTH
        ))
        if self.state_key is None and self.state_value is None:
            pass
        elif self.state_key is None or self.state_value is None:
            raise AdventureEventLogError("state change requires both key and value")
        elif self.event_type != "state_change":
            raise AdventureEventLogError("structured state is allowed only for state_change events")
        else:
            object.__setattr__(self, "state_key", normalize_state_key(self.state_key))
            object.__setattr__(self, "state_value", _required_text(
                self.state_value, field="state value", maximum=_MAX_STATE_VALUE_LENGTH, collapse=True
            ))
        relationship_values = (self.relationship_subject, self.relationship_dimension, self.relationship_value)
        if all(value is None for value in relationship_values):
            pass
        elif any(value is None for value in relationship_values):
            raise AdventureEventLogError("relationship change requires subject, dimension, and value")
        elif self.event_type != "relationship_change":
            raise AdventureEventLogError("structured relationship is allowed only for relationship_change events")
        else:
            object.__setattr__(self, "relationship_subject", _required_text(
                self.relationship_subject, field="relationship subject", maximum=_MAX_RELATIONSHIP_SUBJECT_LENGTH, collapse=True
            ))
            object.__setattr__(self, "relationship_dimension", normalize_relationship_dimension(self.relationship_dimension))
            object.__setattr__(self, "relationship_value", _required_text(
                self.relationship_value, field="relationship value", maximum=_MAX_RELATIONSHIP_VALUE_LENGTH, collapse=True
            ))
        knowledge_values = (self.knowledge_subject, self.knowledge_status, self.knowledge_fact)
        if all(value is None for value in knowledge_values):
            pass
        elif any(value is None for value in knowledge_values):
            raise AdventureEventLogError("character knowledge requires subject, status, and fact")
        elif self.event_type != "character_knowledge":
            raise AdventureEventLogError("structured knowledge is allowed only for character_knowledge events")
        else:
            object.__setattr__(self, "knowledge_subject", _required_text(
                self.knowledge_subject, field="knowledge subject", maximum=_MAX_KNOWLEDGE_SUBJECT_LENGTH, collapse=True
            ))
            object.__setattr__(self, "knowledge_status", normalize_knowledge_status(self.knowledge_status))
            object.__setattr__(self, "knowledge_fact", _required_text(
                self.knowledge_fact, field="knowledge fact", maximum=_MAX_KNOWLEDGE_FACT_LENGTH, collapse=True
            ))
        if not isinstance(self.recorded_at, str) or not self.recorded_at:
            raise AdventureEventLogError("event recording time is required")
        if self.source != EVENT_SOURCE_CORE_EXPLICIT:
            raise AdventureEventLogError("event source is not permitted")
        if self.schema_version != EVENT_LOG_SCHEMA_VERSION:
            raise AdventureEventLogError("event log schema is unsupported")

    @classmethod
    def from_dict(cls, value: object) -> "AdventureEvent":
        if not isinstance(value, dict):
            raise AdventureEventLogError("event log entry must be an object")
        try:
            return cls(
                sequence=value["sequence"], event_id=value["event_id"], event_type=value["event_type"],
                summary=value["summary"], details=value.get("details"), recorded_at=value["recorded_at"],
                state_key=value.get("state_key"), state_value=value.get("state_value"),
                relationship_subject=value.get("relationship_subject"),
                relationship_dimension=value.get("relationship_dimension"), relationship_value=value.get("relationship_value"),
                knowledge_subject=value.get("knowledge_subject"), knowledge_status=value.get("knowledge_status"),
                knowledge_fact=value.get("knowledge_fact"),
                source=value.get("source", EVENT_SOURCE_CORE_EXPLICIT),
                schema_version=value.get("schema_version", EVENT_LOG_SCHEMA_VERSION),
            )
        except KeyError as exc:
            raise AdventureEventLogError("event log entry is incomplete") from exc


@dataclass(frozen=True)
class AdventureEventDraft:
    """A validated, sequence-free event held before one explicit turn commit."""

    event_type: str
    summary: str
    details: str | None = None
    state_key: str | None = None
    state_value: str | None = None
    relationship_subject: str | None = None
    relationship_dimension: str | None = None
    relationship_value: str | None = None
    knowledge_subject: str | None = None
    knowledge_status: str | None = None
    knowledge_fact: str | None = None

    def __post_init__(self) -> None:
        # Reuse the authoritative field validation while deliberately omitting
        # sequence/time, which belong to the eventual append operation.
        validated = AdventureEvent(
            sequence=1, event_id="AE-000001", event_type=self.event_type, summary=self.summary,
            details=self.details, recorded_at="draft",
            state_key=self.state_key, state_value=self.state_value,
            relationship_subject=self.relationship_subject, relationship_dimension=self.relationship_dimension,
            relationship_value=self.relationship_value,
            knowledge_subject=self.knowledge_subject, knowledge_status=self.knowledge_status,
            knowledge_fact=self.knowledge_fact,
        )
        for field_name in (
            "event_type", "summary", "details", "state_key", "state_value",
            "relationship_subject", "relationship_dimension", "relationship_value",
            "knowledge_subject", "knowledge_status", "knowledge_fact",
        ):
            object.__setattr__(self, field_name, getattr(validated, field_name))


class AdventureEventLog:
    """Append-only storage bound to one registry-owned adventure workspace."""

    def __init__(self, registry: AdventureRegistry, record: AdventureRecord, *, now: Callable[[], datetime] | None = None) -> None:
        if not isinstance(registry, AdventureRegistry):
            raise TypeError("registry must be an AdventureRegistry")
        if not isinstance(record, AdventureRecord):
            raise TypeError("record must be an AdventureRecord")
        try:
            resolved = registry.resolve_title(record.title)
        except AdventureRegistryError as exc:
            raise AdventureEventLogError("adventure workspace is not registered") from exc
        if resolved != record:
            raise AdventureEventLogError("adventure record does not match the registry")
        self._registry = registry
        self._record = record
        self._workspace = registry.workspace_path(record.adventure_id)
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        return self._workspace / EVENT_LOG_FILENAME

    def events(self) -> list[AdventureEvent]:
        """Return the validated log without creating files or derived state."""
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise AdventureEventLogError("adventure event log cannot be read") from exc
        events: list[AdventureEvent] = []
        for expected_sequence, line in enumerate(lines, start=1):
            try:
                event = AdventureEvent.from_dict(json.loads(line))
            except (json.JSONDecodeError, AdventureEventLogError) as exc:
                raise AdventureEventLogError("adventure event log is invalid") from exc
            if event.sequence != expected_sequence:
                raise AdventureEventLogError("adventure event log sequence is invalid")
            events.append(event)
        return events

    def append(
        self, event_type: object, summary: object, *, details: object = None,
        state_key: object = None, state_value: object = None,
        relationship_subject: object = None, relationship_dimension: object = None, relationship_value: object = None,
        knowledge_subject: object = None, knowledge_status: object = None, knowledge_fact: object = None,
    ) -> AdventureEvent:
        """Append one Core-authored event through the same atomic batch path."""
        draft = AdventureEventDraft(
            event_type=event_type, summary=summary, details=details,
            state_key=state_key, state_value=state_value,
            relationship_subject=relationship_subject, relationship_dimension=relationship_dimension,
            relationship_value=relationship_value,
            knowledge_subject=knowledge_subject, knowledge_status=knowledge_status, knowledge_fact=knowledge_fact,
        )
        return self.append_many((draft,))[0]

    def append_many(self, drafts: object) -> list[AdventureEvent]:
        """Atomically append a bounded already-validated batch of drafts."""
        if not isinstance(drafts, (list, tuple)) or not drafts:
            raise AdventureEventLogError("event batch must contain at least one draft")
        if len(drafts) > 16 or not all(isinstance(draft, AdventureEventDraft) for draft in drafts):
            raise AdventureEventLogError("event batch must contain at most 16 validated drafts")
        existing = self.events()
        recorded_at = self._now().astimezone(UTC).isoformat()
        events = [
            AdventureEvent(
                sequence=len(existing) + index, event_id=f"AE-{len(existing) + index:06d}",
                event_type=draft.event_type, summary=draft.summary, details=draft.details, recorded_at=recorded_at,
                state_key=draft.state_key, state_value=draft.state_value,
                relationship_subject=draft.relationship_subject, relationship_dimension=draft.relationship_dimension,
                relationship_value=draft.relationship_value,
                knowledge_subject=draft.knowledge_subject, knowledge_status=draft.knowledge_status,
                knowledge_fact=draft.knowledge_fact,
            )
            for index, draft in enumerate(drafts, start=1)
        ]
        try:
            existing_text = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
            temporary = self.path.with_suffix(".jsonl.pending")
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(existing_text)
                for event in events:
                    handle.write(json.dumps(asdict(event), sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise AdventureEventLogError("adventure event log cannot be written") from exc
        self._mark_manifest_initialized()
        return events

    def _mark_manifest_initialized(self) -> None:
        manifest_path = self._workspace / MANIFEST_FILENAME
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdventureEventLogError("adventure manifest cannot be read") from exc
        if (
            not isinstance(manifest, dict)
            or manifest.get("adventure_id") != self._record.adventure_id
            or not isinstance(manifest.get("storage"), dict)
        ):
            raise AdventureEventLogError("adventure manifest is invalid")
        manifest["storage"]["event_log"] = "events.jsonl:v1"
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except OSError as exc:
            raise AdventureEventLogError("adventure manifest cannot be written") from exc


__all__ = [
    "AdventureEvent", "AdventureEventDraft", "AdventureEventLog", "AdventureEventLogError", "EVENT_LOG_FILENAME",
    "EVENT_LOG_SCHEMA_VERSION", "EVENT_SOURCE_CORE_EXPLICIT", "EVENT_TYPES", "KNOWLEDGE_STATUSES",
    "normalize_knowledge_status", "normalize_relationship_dimension", "normalize_state_key",
]
