"""Typed, sanitized Core context for future generated adventure turns.

This is deliberately a *projection*, not a new adventure state source.  The
mounted session retains complete event-backed projections; this module copies
only a small, presentation-safe subset for an untrusted provider request.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from pipeline.adventure_registry import AdventureRecord
from pipeline.adventure_session import AdventureSessionState


MAX_TURN_CONTEXT_EVENTS = 6
MAX_TURN_CONTEXT_STATE_FACTS = 8
MAX_TURN_CONTEXT_RELATIONSHIPS = 8
MAX_TURN_CONTEXT_KNOWLEDGE_FACTS = 8
MAX_TURN_CONTEXT_RESOURCES = 8
MAX_TURN_CONTEXT_CHARACTERS = 14_000

_NUMERIC_RELATIONSHIP_VALUE = re.compile(r"\d")


def _bounded(value: str, maximum: int) -> str:
    """Keep a context projection bounded without modifying authoritative data."""
    normalized = " ".join(value.split())
    return normalized[:maximum].rstrip()


def _safe_relationship_value(value: str) -> str:
    """Never disclose a numeric story meter to an extraction provider."""
    return "qualitative internal state" if _NUMERIC_RELATIONSHIP_VALUE.search(value) else value


@dataclass(frozen=True)
class AdventureTurnContextEntry:
    """One already-sanitized, typed line suitable for a provider projection."""

    kind: str
    label: str
    value: str

    def __post_init__(self) -> None:
        if self.kind not in {"event", "state", "relationship", "knowledge", "resource"}:
            raise ValueError("adventure turn context entry kind is unsupported")
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("adventure turn context entry label is invalid")
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("adventure turn context entry value is invalid")


@dataclass(frozen=True)
class AdventureTurnContextView:
    """A bounded non-authoritative provider view of one mounted workspace."""

    record: AdventureRecord
    event_count: int
    entries: tuple[AdventureTurnContextEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.record, AdventureRecord):
            raise TypeError("adventure turn context record is invalid")
        if isinstance(self.event_count, bool) or not isinstance(self.event_count, int) or self.event_count < 0:
            raise ValueError("adventure turn context event count is invalid")
        if not isinstance(self.entries, tuple) or not all(isinstance(item, AdventureTurnContextEntry) for item in self.entries):
            raise TypeError("adventure turn context entries are invalid")

    @classmethod
    def from_session(cls, session: AdventureSessionState) -> "AdventureTurnContextView":
        """Copy only safe bounded facts from an already-mounted adventure session."""
        if not isinstance(session, AdventureSessionState):
            raise TypeError("adventure turn context requires an AdventureSessionState")
        if session.record is None:
            raise ValueError("adventure turn context requires a mounted workspace")

        entries: list[AdventureTurnContextEntry] = []
        for event in session.context_events[:MAX_TURN_CONTEXT_EVENTS]:
            entries.append(AdventureTurnContextEntry("event", event.event_type, _bounded(event.summary, 500)))
        for fact in session.context_state_facts[:MAX_TURN_CONTEXT_STATE_FACTS]:
            entries.append(AdventureTurnContextEntry("state", fact.key, _bounded(fact.value, 500)))
        for fact in session.context_relationship_facts[:MAX_TURN_CONTEXT_RELATIONSHIPS]:
            entries.append(AdventureTurnContextEntry(
                "relationship", f"{fact.subject} / {fact.dimension}",
                _bounded(_safe_relationship_value(fact.value), 160),
            ))
        for fact in session.context_knowledge_facts[:MAX_TURN_CONTEXT_KNOWLEDGE_FACTS]:
            entries.append(AdventureTurnContextEntry(
                "knowledge", f"{fact.subject} {fact.status}", _bounded(fact.fact, 500),
            ))
        # AdventureSessionState has already selected public facts only.  Never
        # consult its complete resource projection here.
        for fact in session.context_resource_facts[:MAX_TURN_CONTEXT_RESOURCES]:
            entries.append(AdventureTurnContextEntry(
                "resource", f"{fact.resource_id} ({fact.label})", _bounded(str(fact.value), 500),
            ))

        view = cls(session.record, session.event_count, tuple(entries))
        if len(view.render()) > MAX_TURN_CONTEXT_CHARACTERS:
            raise ValueError("adventure turn context projection exceeds its bounded limit")
        return view

    def render(self) -> str:
        """Render a provider-safe reference section with no write authority."""
        lines = [
            "ADVENTURE TURN CORE CONTEXT (bounded, read-only projection):",
            f"Workspace: {self.record.title} ({self.record.adventure_id})",
            f"Authoritative event count: {self.event_count}",
            "Do not infer omitted facts, hidden resources, or numeric relationship meters.",
        ]
        if self.entries:
            lines.extend(f"- [{entry.kind}] {entry.label}: {entry.value}" for entry in self.entries)
        else:
            lines.append("- No bounded adventure facts are currently selected.")
        lines.append("END ADVENTURE TURN CORE CONTEXT")
        return "\n".join(lines)

    @property
    def adventure_id(self) -> str:
        return self.record.adventure_id

    @property
    def title(self) -> str:
        return self.record.title


__all__ = [
    "AdventureTurnContextEntry", "AdventureTurnContextView",
    "MAX_TURN_CONTEXT_CHARACTERS", "MAX_TURN_CONTEXT_EVENTS",
]
