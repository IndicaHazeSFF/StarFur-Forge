"""Bounded, adventure-local read model for one governed participant.

This module deliberately does not register a roster, invoke a provider, or
write an event. It turns already-mounted Core projections into a small view
that a future persona/NPC proposal path may receive without access to shared
assistant memory, real-world persona state, hidden resources, or full history.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_initiative import AdventureInitiativeError, AdventureParticipant
from pipeline.adventure_knowledge import AdventureKnowledgeFact
from pipeline.adventure_relationship import AdventureRelationshipFact
from pipeline.adventure_resource_state import AdventureResourceFact
from pipeline.adventure_session import AdventureSessionState


MAX_PARTICIPANT_EVENTS = 16
MAX_PARTICIPANT_RELATIONSHIPS = 16
MAX_PARTICIPANT_RESOURCES = 16
MAX_PARTICIPANT_VIEW_CHARACTERS = 12_000


def _participant_subject_matches(participant: AdventureParticipant, subject: str) -> bool:
    """Use only exact normalized participant identity/display-name matches."""
    normalized = " ".join(subject.split()).casefold()
    return normalized in {participant.participant_id, participant.display_name.casefold()}


@dataclass(frozen=True)
class AdventureParticipantView:
    """A bounded, perspective-appropriate, non-authoritative participant view."""

    adventure_id: str
    participant: AdventureParticipant
    event_count: int
    events: tuple[str, ...]
    relationships: tuple[AdventureRelationshipFact, ...]
    knowledge: tuple[AdventureKnowledgeFact, ...]
    public_resources: tuple[AdventureResourceFact, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.adventure_id, str) or not self.adventure_id:
            raise AdventureInitiativeError("participant view adventure identifier is invalid")
        if not isinstance(self.participant, AdventureParticipant):
            raise TypeError("participant view requires an AdventureParticipant")
        expected = f"adventure:{self.adventure_id}:participant:{self.participant.participant_id}"
        if self.participant.memory_namespace != expected:
            raise AdventureInitiativeError("participant memory namespace does not match this adventure")
        if isinstance(self.event_count, bool) or not isinstance(self.event_count, int) or self.event_count < 0:
            raise AdventureInitiativeError("participant view event count is invalid")
        if not isinstance(self.events, tuple) or len(self.events) > MAX_PARTICIPANT_EVENTS:
            raise AdventureInitiativeError("participant view events are invalid")
        if not all(isinstance(item, str) and item for item in self.events):
            raise AdventureInitiativeError("participant view event summaries are invalid")
        if not isinstance(self.relationships, tuple) or len(self.relationships) > MAX_PARTICIPANT_RELATIONSHIPS:
            raise AdventureInitiativeError("participant view relationships are invalid")
        if not all(isinstance(item, AdventureRelationshipFact) for item in self.relationships):
            raise TypeError("participant view relationships must be AdventureRelationshipFacts")
        if not isinstance(self.knowledge, tuple) or len(self.knowledge) > self.participant.memory_policy.max_knowledge_facts:
            raise AdventureInitiativeError("participant view knowledge is invalid")
        if not all(isinstance(item, AdventureKnowledgeFact) for item in self.knowledge):
            raise TypeError("participant view knowledge must be AdventureKnowledgeFacts")
        if not isinstance(self.public_resources, tuple) or len(self.public_resources) > MAX_PARTICIPANT_RESOURCES:
            raise AdventureInitiativeError("participant view resources are invalid")
        if not all(isinstance(item, AdventureResourceFact) and item.visibility == "public" for item in self.public_resources):
            raise AdventureInitiativeError("participant view may contain public resource facts only")

    @classmethod
    def from_session(cls, session: AdventureSessionState, participant: AdventureParticipant) -> "AdventureParticipantView":
        """Build from bounded mounted context without reading full history/state."""
        if not isinstance(session, AdventureSessionState):
            raise TypeError("participant view requires an AdventureSessionState")
        if session.record is None:
            raise AdventureInitiativeError("participant view requires a mounted adventure")
        if not isinstance(participant, AdventureParticipant):
            raise TypeError("participant view requires an AdventureParticipant")
        events = tuple(event.summary for event in session.context_events[:min(
            MAX_PARTICIPANT_EVENTS, participant.memory_policy.max_context_facts,
        )])
        relationships = tuple(
            fact for fact in session.context_relationship_facts
            if _participant_subject_matches(participant, fact.subject)
        )[:MAX_PARTICIPANT_RELATIONSHIPS]
        knowledge = tuple(
            fact for fact in session.context_knowledge_facts
            if _participant_subject_matches(participant, fact.subject)
        )[:participant.memory_policy.max_knowledge_facts]
        public_resources = tuple(
            fact for fact in session.context_resource_facts if fact.visibility == "public"
        )[:MAX_PARTICIPANT_RESOURCES]
        return cls(
            session.record.adventure_id, participant, session.event_count, events,
            relationships, knowledge, public_resources,
        )

    def render(self) -> str:
        """Render a bounded reference section; never grants action authority."""
        lines = [
            "ADVENTURE PARTICIPANT VIEW (bounded, read-only projection):",
            f"Participant: {self.participant.display_name} ({self.participant.kind})",
            f"Authoritative event count: {self.event_count}",
            "Do not infer omitted facts, hidden resources, or real-world persona/user state.",
        ]
        if self.events:
            lines.extend(f"- [event] {event}" for event in self.events)
        if self.relationships:
            lines.extend(f"- [relationship] {fact.dimension}: {fact.value}" for fact in self.relationships)
        if self.knowledge:
            lines.extend(f"- [knowledge] {fact.status}: {fact.fact}" for fact in self.knowledge)
        if self.public_resources:
            lines.extend(f"- [resource] {fact.resource_id} ({fact.label}): {fact.value}" for fact in self.public_resources)
        if len(lines) == 4:
            lines.append("- No participant-relevant bounded facts are selected.")
        lines.append("END ADVENTURE PARTICIPANT VIEW")
        result = "\n".join(lines)
        if len(result) > MAX_PARTICIPANT_VIEW_CHARACTERS:
            raise AdventureInitiativeError("participant view exceeds its bounded character limit")
        return result


__all__ = [
    "AdventureParticipantView", "MAX_PARTICIPANT_EVENTS", "MAX_PARTICIPANT_RELATIONSHIPS",
    "MAX_PARTICIPANT_RESOURCES", "MAX_PARTICIPANT_VIEW_CHARACTERS",
]
