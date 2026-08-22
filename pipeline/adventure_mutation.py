"""Pure typed mutation envelopes for future authoritative adventure events.

This module deliberately validates data only.  It does not read or write an
event log, infer mutations from narration, call a provider, or attach a
mutation to the current schema-v1 event representation.  That incremental
adapter belongs to a later A3 slice.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from pipeline.adventure_resource_state import AdventureResourceOperation, AdventureResourceStateError


EVENT_ENVELOPE_SCHEMA_VERSION = 2
EVENT_SOURCE_CORE_EXPLICIT = "core_explicit"
MUTATION_STATE_SET = "state_set"
MUTATION_RELATIONSHIP_SET = "relationship_set"
MUTATION_KNOWLEDGE_SET = "knowledge_set"
MUTATION_RESOURCE_CHANGE = "resource_change"
MUTATION_KINDS = frozenset({
    MUTATION_STATE_SET,
    MUTATION_RELATIONSHIP_SET,
    MUTATION_KNOWLEDGE_SET,
    MUTATION_RESOURCE_CHANGE,
})

_EVENT_ID_PATTERN = re.compile(r"^AE-[0-9]{6}$")
_REQUEST_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{7,95}$")
_STATE_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DIMENSION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_SUMMARY_LENGTH = 500
_MAX_DETAILS_LENGTH = 4_000
_MAX_VALUE_LENGTH = 500
_MAX_SUBJECT_LENGTH = 96
_KNOWLEDGE_STATUSES = frozenset({"knows", "believes", "uncertain"})


class AdventureMutationError(ValueError):
    """Raised when a mutation envelope is not explicit, bounded, and typed."""


def _text(value: object, *, field: str, maximum: int, collapse: bool = False) -> str:
    if not isinstance(value, str):
        raise AdventureMutationError(f"{field} must be text")
    normalized = " ".join(value.split()) if collapse else value.strip()
    if not normalized:
        raise AdventureMutationError(f"{field} cannot be empty")
    if len(normalized) > maximum:
        raise AdventureMutationError(f"{field} must be at most {maximum} characters")
    return normalized


def _optional_text(value: object, *, field: str, maximum: int) -> str | None:
    return None if value is None else _text(value, field=field, maximum=maximum)


def _event_id(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _EVENT_ID_PATTERN.fullmatch(value):
        raise AdventureMutationError(f"{field} is invalid")
    return value


def _resource_value(value: object) -> object:
    """Keep a schema-v2 resource payload JSON-safe before catalog validation."""
    try:
        return json.loads(json.dumps(value, separators=(",", ":")))
    except (TypeError, ValueError) as error:
        raise AdventureMutationError("resource value must be JSON-compatible") from error


@dataclass(frozen=True)
class AdventureMutation:
    """One explicit structured state change, independent of narrative prose."""

    kind: str
    state_key: str | None = None
    state_value: str | None = None
    relationship_subject: str | None = None
    relationship_dimension: str | None = None
    relationship_value: str | None = None
    knowledge_subject: str | None = None
    knowledge_status: str | None = None
    knowledge_fact: str | None = None
    resource_id: str | None = None
    resource_operation: str | None = None
    resource_value: object = None

    def __post_init__(self) -> None:
        if self.kind not in MUTATION_KINDS:
            raise AdventureMutationError("mutation kind is unsupported")
        state_values = (self.state_key, self.state_value)
        relationship_values = (self.relationship_subject, self.relationship_dimension, self.relationship_value)
        knowledge_values = (self.knowledge_subject, self.knowledge_status, self.knowledge_fact)
        resource_values = (self.resource_id, self.resource_operation, self.resource_value)
        if self.kind == MUTATION_STATE_SET:
            if any(value is not None for value in (*relationship_values, *knowledge_values, *resource_values)):
                raise AdventureMutationError("state mutation cannot contain another mutation payload")
            if any(value is None for value in state_values):
                raise AdventureMutationError("state mutation requires key and value")
            key = _text(self.state_key, field="state key", maximum=64).casefold()
            if not _STATE_KEY_PATTERN.fullmatch(key):
                raise AdventureMutationError("state key is invalid")
            object.__setattr__(self, "state_key", key)
            object.__setattr__(self, "state_value", _text(
                self.state_value, field="state value", maximum=_MAX_VALUE_LENGTH, collapse=True
            ))
            return
        if self.kind == MUTATION_RELATIONSHIP_SET:
            if any(value is not None for value in (*state_values, *knowledge_values, *resource_values)):
                raise AdventureMutationError("relationship mutation cannot contain another mutation payload")
            if any(value is None for value in relationship_values):
                raise AdventureMutationError("relationship mutation requires subject, dimension, and value")
            object.__setattr__(self, "relationship_subject", _text(
                self.relationship_subject, field="relationship subject", maximum=_MAX_SUBJECT_LENGTH, collapse=True
            ))
            dimension = _text(self.relationship_dimension, field="relationship dimension", maximum=64).casefold()
            if not _DIMENSION_PATTERN.fullmatch(dimension):
                raise AdventureMutationError("relationship dimension is invalid")
            object.__setattr__(self, "relationship_dimension", dimension)
            object.__setattr__(self, "relationship_value", _text(
                self.relationship_value, field="relationship value", maximum=_MAX_VALUE_LENGTH, collapse=True
            ))
            return
        if self.kind == MUTATION_KNOWLEDGE_SET:
            if any(value is not None for value in (*state_values, *relationship_values, *resource_values)):
                raise AdventureMutationError("knowledge mutation cannot contain another mutation payload")
            if any(value is None for value in knowledge_values):
                raise AdventureMutationError("knowledge mutation requires subject, status, and fact")
            object.__setattr__(self, "knowledge_subject", _text(
                self.knowledge_subject, field="knowledge subject", maximum=_MAX_SUBJECT_LENGTH, collapse=True
            ))
            status = _text(self.knowledge_status, field="knowledge status", maximum=32).casefold()
            if status not in _KNOWLEDGE_STATUSES:
                raise AdventureMutationError("knowledge status is unsupported")
            object.__setattr__(self, "knowledge_status", status)
            object.__setattr__(self, "knowledge_fact", _text(
                self.knowledge_fact, field="knowledge fact", maximum=_MAX_VALUE_LENGTH, collapse=True
            ))
            return
        if any(value is not None for value in (*state_values, *relationship_values, *knowledge_values)):
            raise AdventureMutationError("resource mutation cannot contain another mutation payload")
        if self.resource_id is None or self.resource_operation is None:
            raise AdventureMutationError("resource mutation requires identifier and operation")
        try:
            operation = AdventureResourceOperation(
                self.resource_id, self.resource_operation, _resource_value(self.resource_value)
            )
        except AdventureResourceStateError as error:
            raise AdventureMutationError("resource mutation is invalid") from error
        object.__setattr__(self, "resource_id", operation.resource_id)
        object.__setattr__(self, "resource_operation", operation.operation)
        object.__setattr__(self, "resource_value", operation.value)
        return

    def to_dict(self) -> dict[str, object]:
        if self.kind == MUTATION_STATE_SET:
            return {"kind": self.kind, "key": self.state_key, "value": self.state_value}
        if self.kind == MUTATION_RELATIONSHIP_SET:
            return {
                "kind": self.kind,
                "subject": self.relationship_subject,
                "dimension": self.relationship_dimension,
                "value": self.relationship_value,
            }
        if self.kind == MUTATION_KNOWLEDGE_SET:
            return {
                "kind": self.kind,
                "subject": self.knowledge_subject,
                "status": self.knowledge_status,
                "fact": self.knowledge_fact,
            }
        return {
            "kind": self.kind,
            "id": self.resource_id,
            "operation": self.resource_operation,
            "value": self.resource_value,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureMutation":
        if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
            raise AdventureMutationError("mutation payload is invalid")
        kind = value["kind"]
        if kind == MUTATION_STATE_SET:
            return cls(kind=kind, state_key=value.get("key"), state_value=value.get("value"))
        if kind == MUTATION_RELATIONSHIP_SET:
            return cls(
                kind=kind,
                relationship_subject=value.get("subject"),
                relationship_dimension=value.get("dimension"),
                relationship_value=value.get("value"),
            )
        if kind == MUTATION_KNOWLEDGE_SET:
            return cls(
                kind=kind,
                knowledge_subject=value.get("subject"),
                knowledge_status=value.get("status"),
                knowledge_fact=value.get("fact"),
            )
        if kind == MUTATION_RESOURCE_CHANGE:
            return cls(
                kind=kind,
                resource_id=value.get("id"),
                resource_operation=value.get("operation"),
                resource_value=value.get("value"),
            )
        raise AdventureMutationError("mutation kind is unsupported")


@dataclass(frozen=True)
class AdventureEventEnvelope:
    """A future schema-v2 event representation with explicit provenance."""

    sequence: int
    event_id: str
    event_type: str
    recorded_at: str
    summary: str
    details: str | None
    request_id: str | None = None
    supersedes_event_id: str | None = None
    mutation: AdventureMutation | None = None
    source: str = EVENT_SOURCE_CORE_EXPLICIT
    schema_version: int = EVENT_ENVELOPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureMutationError("event sequence must be a positive integer")
        expected = f"AE-{self.sequence:06d}"
        if self.event_id != expected:
            raise AdventureMutationError("event identifier does not match its sequence")
        _event_id(self.event_id, field="event identifier")
        object.__setattr__(self, "event_type", _text(
            self.event_type, field="event type", maximum=64, collapse=True
        ))
        if not isinstance(self.recorded_at, str) or not self.recorded_at:
            raise AdventureMutationError("event recording time is required")
        object.__setattr__(self, "summary", _text(
            self.summary, field="summary", maximum=_MAX_SUMMARY_LENGTH, collapse=True
        ))
        object.__setattr__(self, "details", _optional_text(
            self.details, field="details", maximum=_MAX_DETAILS_LENGTH
        ))
        if self.request_id is not None:
            request_id = _text(self.request_id, field="event request identifier", maximum=96).casefold()
            if not _REQUEST_ID_PATTERN.fullmatch(request_id):
                raise AdventureMutationError("event request identifier is invalid")
            object.__setattr__(self, "request_id", request_id)
        if self.supersedes_event_id is not None:
            supersedes = _event_id(self.supersedes_event_id, field="superseded event identifier")
            if supersedes == self.event_id:
                raise AdventureMutationError("an event cannot supersede itself")
            object.__setattr__(self, "supersedes_event_id", supersedes)
        if self.mutation is not None and not isinstance(self.mutation, AdventureMutation):
            raise AdventureMutationError("event mutation must be an AdventureMutation")
        if self.source != EVENT_SOURCE_CORE_EXPLICIT:
            raise AdventureMutationError("event source is not permitted")
        if self.schema_version != EVENT_ENVELOPE_SCHEMA_VERSION:
            raise AdventureMutationError("event envelope schema is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "recorded_at": self.recorded_at,
            "summary": self.summary,
            "details": self.details,
            "request_id": self.request_id,
            "supersedes_event_id": self.supersedes_event_id,
            "mutation": None if self.mutation is None else self.mutation.to_dict(),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureEventEnvelope":
        if not isinstance(value, dict):
            raise AdventureMutationError("event envelope must be an object")
        mutation_value = value.get("mutation")
        return cls(
            sequence=value.get("sequence"),
            event_id=value.get("event_id"),
            event_type=value.get("event_type"),
            recorded_at=value.get("recorded_at"),
            summary=value.get("summary"),
            details=value.get("details"),
            request_id=value.get("request_id"),
            supersedes_event_id=value.get("supersedes_event_id"),
            mutation=None if mutation_value is None else AdventureMutation.from_dict(mutation_value),
            source=value.get("source", EVENT_SOURCE_CORE_EXPLICIT),
            schema_version=value.get("schema_version"),
        )


__all__ = [
    "AdventureEventEnvelope", "AdventureMutation", "AdventureMutationError",
    "EVENT_ENVELOPE_SCHEMA_VERSION", "EVENT_SOURCE_CORE_EXPLICIT",
    "MUTATION_KINDS", "MUTATION_KNOWLEDGE_SET", "MUTATION_RELATIONSHIP_SET", "MUTATION_RESOURCE_CHANGE",
    "MUTATION_STATE_SET",
]
