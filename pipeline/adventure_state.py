"""Deterministic current-story state projected from authoritative event records."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

from pipeline.adventure_events import AdventureEvent


MAX_CONTEXT_STATE_FACTS = 12


@dataclass(frozen=True)
class AdventureStateFact:
    """The latest explicit value for one story-state key."""

    key: str
    value: str
    source_event_id: str


def derive_adventure_state(events: Iterable[AdventureEvent]) -> tuple[AdventureStateFact, ...]:
    """Rebuild the complete latest-value state projection from event history."""
    values = tuple(events)
    if not all(isinstance(event, AdventureEvent) for event in values):
        raise TypeError("story-state events must be AdventureEvents")
    latest: dict[str, AdventureStateFact] = {}
    for event in sorted(values, key=lambda item: item.sequence):
        if event.event_type == "state_change" and event.state_key is not None:
            latest[event.state_key] = AdventureStateFact(
                key=event.state_key, value=event.state_value, source_event_id=event.event_id
            )
    return tuple(latest[key] for key in sorted(latest))


def select_adventure_state_context(
    facts: Iterable[AdventureStateFact], *, limit: int = MAX_CONTEXT_STATE_FACTS,
) -> tuple[AdventureStateFact, ...]:
    """Select a deterministic bounded prompt/UI view without truncating state."""
    if not isinstance(limit, int) or not 1 <= limit <= MAX_CONTEXT_STATE_FACTS:
        raise ValueError(f"state fact limit must be between 1 and {MAX_CONTEXT_STATE_FACTS}")
    values = tuple(facts)
    if not all(isinstance(fact, AdventureStateFact) for fact in values):
        raise TypeError("story-state facts must be AdventureStateFacts")
    return values[:limit]


__all__ = [
    "AdventureStateFact", "MAX_CONTEXT_STATE_FACTS", "derive_adventure_state",
    "select_adventure_state_context",
]
