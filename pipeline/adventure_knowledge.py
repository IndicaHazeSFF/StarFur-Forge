"""Deterministic per-character knowledge projection for one adventure."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pipeline.adventure_events import AdventureEvent


MAX_CONTEXT_KNOWLEDGE_FACTS = 12


@dataclass(frozen=True)
class AdventureKnowledgeFact:
    """One character's latest explicit stance toward one story fact."""

    subject: str
    status: str
    fact: str
    source_event_id: str


def derive_adventure_knowledge(events: Iterable[AdventureEvent]) -> tuple[AdventureKnowledgeFact, ...]:
    """Rebuild complete character-scoped knowledge from event history."""
    values = tuple(events)
    if not all(isinstance(event, AdventureEvent) for event in values):
        raise TypeError("adventure knowledge events must be AdventureEvents")
    latest: dict[tuple[str, str], AdventureKnowledgeFact] = {}
    for event in sorted(values, key=lambda item: item.sequence):
        if event.event_type != "character_knowledge" or event.knowledge_subject is None:
            continue
        key = (event.knowledge_subject.casefold(), event.knowledge_fact.casefold())
        latest[key] = AdventureKnowledgeFact(
            subject=event.knowledge_subject,
            status=event.knowledge_status,
            fact=event.knowledge_fact,
            source_event_id=event.event_id,
        )
    return tuple(latest[key] for key in sorted(latest))


def select_adventure_knowledge_context(
    facts: Iterable[AdventureKnowledgeFact], *, limit: int = MAX_CONTEXT_KNOWLEDGE_FACTS,
) -> tuple[AdventureKnowledgeFact, ...]:
    """Select a deterministic bounded prompt/UI view without truncating truth."""
    if not isinstance(limit, int) or not 1 <= limit <= MAX_CONTEXT_KNOWLEDGE_FACTS:
        raise ValueError(f"knowledge fact limit must be between 1 and {MAX_CONTEXT_KNOWLEDGE_FACTS}")
    values = tuple(facts)
    if not all(isinstance(fact, AdventureKnowledgeFact) for fact in values):
        raise TypeError("adventure knowledge facts must be AdventureKnowledgeFacts")
    return values[:limit]


__all__ = [
    "AdventureKnowledgeFact", "MAX_CONTEXT_KNOWLEDGE_FACTS", "derive_adventure_knowledge",
    "select_adventure_knowledge_context",
]
