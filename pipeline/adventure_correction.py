"""Pure active-event resolution for append-only adventure history.

Supersession is an audit relationship, not deletion.  This module consumes a
validated chronological event sequence and reports which records are active
for a future projection.  It deliberately does not read logs, write events,
infer corrections from prose, or expose a command.  Core-owned writers and
typed projections can adopt this resolver in later slices without changing
the historical record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, TypeVar


class AdventureCorrectionError(ValueError):
    """Raised when supersession references cannot form safe event history."""


class _AdventureEventLike(Protocol):
    sequence: int
    event_id: str
    supersedes_event_id: str | None


EventT = TypeVar("EventT", bound=_AdventureEventLike)


@dataclass(frozen=True)
class AdventureEventActivity:
    """One inspectable active/inactive result without modifying its event."""

    event_id: str
    active: bool
    superseded_by_event_id: str | None


@dataclass(frozen=True)
class AdventureActiveEventProjection:
    """Complete activity result plus the original active event objects."""

    activities: tuple[AdventureEventActivity, ...]
    active_events: tuple[EventT, ...]


def resolve_active_adventure_events(events: Sequence[EventT]) -> AdventureActiveEventProjection:
    """Resolve explicit supersession chains while preserving every input event.

    A later event may supersede exactly one earlier event.  The superseding
    event is itself active unless another later record supersedes it, so a
    correction chain has one active tip.  Unknown, duplicate, forward, and
    self references fail closed rather than guessing a projection.
    """
    if not isinstance(events, (list, tuple)):
        raise TypeError("adventure event activity requires a sequence of events")

    seen: dict[str, EventT] = {}
    superseded_by: dict[str, str] = {}
    for event in events:
        if not isinstance(event.sequence, int) or event.sequence < 1:
            raise AdventureCorrectionError("event sequence is invalid")
        if not isinstance(event.event_id, str) or not event.event_id:
            raise AdventureCorrectionError("event identifier is invalid")
        if event.event_id in seen:
            raise AdventureCorrectionError("adventure event identifiers must be unique")

        target_id = event.supersedes_event_id
        if target_id is not None:
            if not isinstance(target_id, str) or not target_id:
                raise AdventureCorrectionError("superseded event identifier is invalid")
            if target_id == event.event_id:
                raise AdventureCorrectionError("an event cannot supersede itself")
            target = seen.get(target_id)
            if target is None:
                raise AdventureCorrectionError("superseded event must already exist in the event history")
            if target.sequence >= event.sequence:
                raise AdventureCorrectionError("superseded event must precede its correction")
            if target_id in superseded_by:
                raise AdventureCorrectionError("an event may be superseded by only one correction")
            superseded_by[target_id] = event.event_id
        seen[event.event_id] = event

    activities = tuple(
        AdventureEventActivity(
            event_id=event.event_id,
            active=event.event_id not in superseded_by,
            superseded_by_event_id=superseded_by.get(event.event_id),
        )
        for event in events
    )
    return AdventureActiveEventProjection(
        activities=activities,
        active_events=tuple(event for event in events if event.event_id not in superseded_by),
    )


__all__ = [
    "AdventureActiveEventProjection", "AdventureCorrectionError", "AdventureEventActivity",
    "resolve_active_adventure_events",
]
