"""Deterministic qualitative relationship projection for one adventure."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

from pipeline.adventure_events import AdventureEvent


MAX_CONTEXT_RELATIONSHIP_FACTS = 12


@dataclass(frozen=True)
class AdventureRelationshipFact:
    """The latest explicit qualitative fact for one character dimension."""

    subject: str
    dimension: str
    value: str
    source_event_id: str


def derive_adventure_relationships(
    events: Iterable[AdventureEvent], *, limit: int = MAX_CONTEXT_RELATIONSHIP_FACTS
) -> tuple[AdventureRelationshipFact, ...]:
    """Project only explicit relationship-change records; never infer narration."""
    if not isinstance(limit, int) or not 1 <= limit <= MAX_CONTEXT_RELATIONSHIP_FACTS:
        raise ValueError(f"relationship fact limit must be between 1 and {MAX_CONTEXT_RELATIONSHIP_FACTS}")
    values = tuple(events)
    if not all(isinstance(event, AdventureEvent) for event in values):
        raise TypeError("adventure relationship events must be AdventureEvents")
    latest: dict[tuple[str, str], AdventureRelationshipFact] = {}
    for event in sorted(values, key=lambda item: item.sequence):
        if event.event_type != "relationship_change" or event.relationship_subject is None:
            continue
        key = (event.relationship_subject.casefold(), event.relationship_dimension)
        latest[key] = AdventureRelationshipFact(
            subject=event.relationship_subject,
            dimension=event.relationship_dimension,
            value=event.relationship_value,
            source_event_id=event.event_id,
        )
    return tuple(latest[key] for key in sorted(latest)[:limit])


__all__ = [
    "AdventureRelationshipFact", "MAX_CONTEXT_RELATIONSHIP_FACTS", "derive_adventure_relationships",
]
