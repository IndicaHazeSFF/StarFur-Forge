"""Bounded, adventure-local read model for one governed participant.

This module deliberately does not register a roster, invoke a provider, or
write an event. It turns already-mounted Core projections into a small view
that a future persona/NPC proposal path may receive without access to shared
assistant memory, real-world persona state, hidden resources, or full history.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re

from pipeline.adventure_initiative import AdventureInitiativeError, AdventureParticipant
from pipeline.adventure_initiative import AdventureParticipantRoster
from pipeline.adventure_knowledge import AdventureKnowledgeFact
from pipeline.adventure_relationship import AdventureRelationshipFact
from pipeline.adventure_resource_state import AdventureResourceFact
from pipeline.adventure_session import AdventureSessionState


MAX_PARTICIPANT_EVENTS = 16
MAX_PARTICIPANT_RELATIONSHIPS = 16
MAX_PARTICIPANT_RESOURCES = 16
MAX_PARTICIPANT_VIEW_CHARACTERS = 12_000
MAX_DECLARED_PARTICIPANT_CONTEXT_CHARACTERS = 4_000

# Ordinary replay facts are not automatically public to every governed
# participant.  Until an event schema gains explicit audience declarations,
# retain only event kinds that establish shared world continuity.  Perspective
# facts use their typed projections below, where subject ownership is known.
_SHARED_PARTICIPANT_EVENT_TYPES = frozenset({
    "premise", "choice", "discovery", "location_change", "state_change", "unresolved_hook",
})
_NUMERIC_RELATIONSHIP_VALUE = re.compile(r"\d")


def _participant_subject_matches(participant: AdventureParticipant, subject: str) -> bool:
    """Use only exact normalized participant identity/display-name matches."""
    if not isinstance(subject, str):
        return False
    normalized = " ".join(subject.split()).casefold()
    return normalized in {participant.participant_id, participant.display_name.casefold()}


def _participant_event_is_visible(participant: AdventureParticipant, event: object) -> bool:
    """Conservatively admit only shared continuity events to a participant view.

    Relationship and character-knowledge events are represented by typed
    projections after an exact subject check.  Their narrative summaries must
    not bypass that perspective boundary merely because they appeared in the
    global replay spine.
    """
    event_type = getattr(event, "event_type", None)
    if event_type in _SHARED_PARTICIPANT_EVENT_TYPES:
        return True
    return False


def _safe_relationship_value(value: str) -> str:
    """Keep internal numeric meters out of a future participant prompt."""
    return "qualitative internal state" if _NUMERIC_RELATIONSHIP_VALUE.search(value) else value


def render_declared_participant_prompt_context(roster: AdventureParticipantRoster) -> str:
    """Render only explicit package-declared participant labels for a model.

    This is intentionally not a participant perspective view: it excludes
    namespaces, memory policy, event/state projections, relationships,
    resources, initiative decisions, and any permission-shaped material. The
    roster labels merely help an ordinary-event extractor recognize who is in
    the declared adventure cast; they never authorize an action or establish a
    fact beyond the package declaration.
    """
    if not isinstance(roster, AdventureParticipantRoster):
        raise TypeError("participant prompt context requires an AdventureParticipantRoster")
    lines = [
        "DECLARED ADVENTURE PARTICIPANTS (Core-supplied labels only):",
        "Do not infer omitted history, perspective, authority, or an autonomous action from these labels.",
    ]
    lines.extend(
        f"- {participant.participant_id} ({participant.kind}): {participant.display_name}"
        for participant in roster.participants
    )
    rendered = "\n".join(lines)
    if len(rendered) > MAX_DECLARED_PARTICIPANT_CONTEXT_CHARACTERS:
        raise AdventureInitiativeError("declared participant context exceeds its bounded character limit")
    return rendered


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
    character_budget_omissions: int = 0

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
        maximum_omissions = MAX_PARTICIPANT_EVENTS + MAX_PARTICIPANT_RELATIONSHIPS + MAX_PARTICIPANT_RESOURCES + self.participant.memory_policy.max_knowledge_facts
        if (type(self.character_budget_omissions) is not int
                or not 0 <= self.character_budget_omissions <= maximum_omissions):
            raise AdventureInitiativeError("participant view omission count is invalid")

    @classmethod
    def from_session(cls, session: AdventureSessionState, participant: AdventureParticipant) -> "AdventureParticipantView":
        """Build from bounded mounted context without reading full history/state."""
        if not isinstance(session, AdventureSessionState):
            raise TypeError("participant view requires an AdventureSessionState")
        if session.record is None:
            raise AdventureInitiativeError("participant view requires a mounted adventure")
        if not isinstance(participant, AdventureParticipant):
            raise TypeError("participant view requires an AdventureParticipant")
        event_limit = min(MAX_PARTICIPANT_EVENTS, participant.memory_policy.max_context_facts)
        events = () if not participant.memory_policy.retain_salient_events else tuple(
            event.summary for event in session.context_events
            if _participant_event_is_visible(participant, event)
        )[:event_limit]
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
        )._fit_character_budget()

    def _fit_character_budget(self) -> "AdventureParticipantView":
        """Keep whole already-filtered facts in existing category/order priority.

        This is bounded presentation selection, never rewriting story truth or
        summarizing a fact. An oversized item does not prevent a later smaller
        item from fitting. Views already below the ceiling are unchanged.
        """
        try:
            self.render()
            return self
        except AdventureInitiativeError:
            pass
        selected = replace(self, events=(), relationships=(), knowledge=(), public_resources=(),
            character_budget_omissions=0)
        omitted = 0
        for category in ("events", "relationships", "knowledge", "public_resources"):
            for item in getattr(self, category):
                candidate = replace(selected, **{category: getattr(selected, category) + (item,)})
                try:
                    candidate.render()
                except AdventureInitiativeError:
                    omitted += 1
                else:
                    selected = candidate
        result = replace(selected, character_budget_omissions=omitted)
        result.render()  # Keep the renderer's hard guard as the final boundary.
        return result

    def context_usage(self) -> dict[str, int]:
        """Describe this existing view only; never read storage or alter selection.

        Counts are per-category ceilings, not one combined model-token budget.
        Rendering here validates the existing character ceiling; its prose is
        discarded and never retained in the returned diagnostic data.
        """
        rendered_characters = len(self.render())
        policy = self.participant.memory_policy
        return {
            "selected_events": len(self.events),
            "event_limit": min(MAX_PARTICIPANT_EVENTS, policy.max_context_facts) if policy.retain_salient_events else 0,
            "selected_relationships": len(self.relationships),
            "relationship_limit": MAX_PARTICIPANT_RELATIONSHIPS,
            "selected_knowledge": len(self.knowledge),
            "knowledge_limit": policy.max_knowledge_facts,
            "selected_public_resources": len(self.public_resources),
            "public_resource_limit": MAX_PARTICIPANT_RESOURCES,
            "selected_fact_count": len(self.events) + len(self.relationships) + len(self.knowledge) + len(self.public_resources),
            "rendered_characters": rendered_characters,
            "character_limit": MAX_PARTICIPANT_VIEW_CHARACTERS,
            "character_budget_omissions": self.character_budget_omissions,
        }

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
            lines.extend(
                f"- [relationship] {fact.dimension}: {_safe_relationship_value(fact.value)}"
                for fact in self.relationships
            )
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
    "MAX_DECLARED_PARTICIPANT_CONTEXT_CHARACTERS", "render_declared_participant_prompt_context",
]
