"""Deterministic, bounded replay-spine selection for adventure event logs.

The append-only log remains authoritative. This module merely selects a small,
chronological subset of validated events for prompt context, preserving early
setup plus the newest important continuity categories before ordinary recency.
"""

from __future__ import annotations

from collections.abc import Iterable

from pipeline.adventure_correction import resolve_active_adventure_events
from pipeline.adventure_events import AdventureEvent


DEFAULT_REPLAY_SPINE_LIMIT = 8
MAX_REPLAY_SPINE_LIMIT = 12
_PRIORITY_EVENT_TYPES = (
    "unresolved_hook",
    "promise",
    "lie",
    "relationship_change",
    "character_knowledge",
    "discovery",
    "choice",
    "location_change",
    "inventory_change",
    "state_change",
    "emotional_transition",
)


def select_replay_spine(
    events: Iterable[AdventureEvent], *, limit: int = DEFAULT_REPLAY_SPINE_LIMIT
) -> tuple[AdventureEvent, ...]:
    """Select bounded chronological replay facts without mutating the log.

    The first event anchors the premise. The latest event from each high-value
    continuity category is retained in priority order, then the newest remaining
    events fill unused capacity. Returned facts are re-sorted by sequence so the
    model receives a coherent timeline rather than priority order.
    """
    if not isinstance(limit, int) or not 1 <= limit <= MAX_REPLAY_SPINE_LIMIT:
        raise ValueError(f"replay spine limit must be between 1 and {MAX_REPLAY_SPINE_LIMIT}")
    raw_events = tuple(events)
    if not all(isinstance(event, AdventureEvent) for event in raw_events):
        raise TypeError("replay spine events must be AdventureEvents")
    if len({event.sequence for event in raw_events}) != len(raw_events):
        raise ValueError("replay spine event sequences must be unique")
    values = tuple(
        event for event in resolve_active_adventure_events(raw_events).active_events
        if event.event_type != "retraction"
    )
    ordered = tuple(sorted(values, key=lambda event: event.sequence))
    if not ordered:
        return ()

    selected: set[int] = {ordered[0].sequence}
    for event_type in _PRIORITY_EVENT_TYPES:
        if len(selected) >= limit:
            break
        latest = next((event for event in reversed(ordered) if event.event_type == event_type), None)
        if latest is not None:
            selected.add(latest.sequence)

    for event in reversed(ordered):
        if len(selected) >= limit:
            break
        selected.add(event.sequence)

    return tuple(event for event in ordered if event.sequence in selected)


__all__ = ["DEFAULT_REPLAY_SPINE_LIMIT", "MAX_REPLAY_SPINE_LIMIT", "select_replay_spine"]
