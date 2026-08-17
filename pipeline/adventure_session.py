"""Bounded read-only mounted-adventure context for one conversation."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_replay import DEFAULT_REPLAY_SPINE_LIMIT, select_replay_spine
from pipeline.adventure_state import AdventureStateFact, derive_adventure_state
from pipeline.adventure_registry import AdventureRecord


MAX_CONTEXT_EVENTS = DEFAULT_REPLAY_SPINE_LIMIT


@dataclass(frozen=True)
class AdventureSessionState:
    """One conversation's optional read-only mount and bounded replay facts."""

    record: AdventureRecord | None = None
    event_count: int = 0
    context_events: tuple[AdventureEvent, ...] = ()
    state_facts: tuple[AdventureStateFact, ...] = ()

    def __post_init__(self) -> None:
        if self.record is not None and not isinstance(self.record, AdventureRecord):
            raise TypeError("mounted adventure record must be an AdventureRecord or None")
        if not isinstance(self.event_count, int) or self.event_count < 0:
            raise ValueError("mounted adventure event count must be a non-negative integer")
        if not isinstance(self.context_events, tuple) or not all(isinstance(event, AdventureEvent) for event in self.context_events):
            raise TypeError("mounted adventure context events must be AdventureEvents")
        if not isinstance(self.state_facts, tuple) or not all(isinstance(fact, AdventureStateFact) for fact in self.state_facts):
            raise TypeError("mounted adventure state facts must be AdventureStateFacts")
        if len(self.context_events) > MAX_CONTEXT_EVENTS:
            raise ValueError("mounted adventure context event limit exceeded")
        if self.record is None and (self.event_count or self.context_events or self.state_facts):
            raise ValueError("unmounted adventure state cannot contain events")
        if self.event_count < len(self.context_events):
            raise ValueError("mounted adventure event count cannot be smaller than context events")

    @classmethod
    def unmounted(cls) -> "AdventureSessionState":
        return cls()

    @property
    def active(self) -> bool:
        return self.record is not None

    def mount(self, record: AdventureRecord, events: list[AdventureEvent] | tuple[AdventureEvent, ...] = ()) -> "AdventureSessionState":
        """Mount only a bounded selection of validated events; never write them."""
        if not isinstance(events, (list, tuple)) or not all(isinstance(event, AdventureEvent) for event in events):
            raise TypeError("mounted adventure events must be AdventureEvents")
        total = len(events)
        return type(self)(
            record=record,
            event_count=total,
            context_events=select_replay_spine(events),
            state_facts=derive_adventure_state(events),
        )

    def unmount(self) -> "AdventureSessionState":
        return type(self).unmounted()

    def public_dict(self) -> dict[str, object]:
        if self.record is None:
            return {"mounted": False, "storage": "session_ephemeral"}
        return {
            "mounted": True,
            "adventure_id": self.record.adventure_id,
            "title": self.record.title,
            "status": self.record.status,
            "event_count": self.event_count,
            "context_event_count": len(self.context_events),
            "state_fact_count": len(self.state_facts),
            "storage": "session_ephemeral",
        }

    def context_text(self) -> str:
        """Render bounded Core-read event facts, never invented story state."""
        if self.record is None:
            return ""
        header = (
            "MOUNTED ADVENTURE WORKSPACE (core-provided):\n"
            f"Title: {self.record.title}\n"
            f"ID: {self.record.adventure_id}\n"
        )
        if not self.context_events:
            return header + (
                "This workspace has no recorded authoritative adventure events. Do not invent prior story events, "
                "characters, relationships, replay history, or hidden narrative state. Keep ordinary assistant "
                "memory and real-world claims separate.\n"
                "END MOUNTED ADVENTURE WORKSPACE"
            )
        events = "\n".join(f"- [{event.event_type}] {event.summary}" for event in self.context_events)
        state = ""
        if self.state_facts:
            state_lines = "\n".join(f"- {fact.key}: {fact.value}" for fact in self.state_facts)
            state = "CURRENT AUTHORITATIVE STORY STATE (core-provided):\n" + state_lines + "\nEND CURRENT AUTHORITATIVE STORY STATE\n"
        return header + (
            f"Authoritative event log: {self.event_count} event(s); {len(self.context_events)} replay-spine facts are supplied below.\n"
            "These are established story facts, not user memories. Do not invent omitted events, details, or values.\n"
            f"{state}"
            "RECENT AUTHORITATIVE ADVENTURE EVENTS:\n"
            f"{events}\n"
            "END MOUNTED ADVENTURE WORKSPACE"
        )


__all__ = ["AdventureSessionState", "MAX_CONTEXT_EVENTS"]
