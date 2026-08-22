"""Bounded read-only mounted-adventure context for one conversation."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_knowledge import (
    AdventureKnowledgeFact,
    MAX_CONTEXT_KNOWLEDGE_FACTS,
    derive_adventure_knowledge,
    select_adventure_knowledge_context,
)
from pipeline.adventure_relationship import (
    AdventureRelationshipFact,
    MAX_CONTEXT_RELATIONSHIP_FACTS,
    derive_adventure_relationships,
    select_adventure_relationship_context,
)
from pipeline.adventure_replay import DEFAULT_REPLAY_SPINE_LIMIT, select_replay_spine
from pipeline.adventure_state import (
    AdventureStateFact,
    MAX_CONTEXT_STATE_FACTS,
    derive_adventure_state,
    select_adventure_state_context,
)
from pipeline.adventure_registry import AdventureRecord
from pipeline.adventure_resources import AdventureResourceCatalog
from pipeline.adventure_resource_state import (
    AdventureResourceFact,
    MAX_CONTEXT_RESOURCE_FACTS,
    derive_adventure_resource_facts,
    select_adventure_resource_context,
)


MAX_CONTEXT_EVENTS = DEFAULT_REPLAY_SPINE_LIMIT


@dataclass(frozen=True)
class AdventureSessionState:
    """One conversation's optional read-only mount and bounded replay facts."""

    record: AdventureRecord | None = None
    event_count: int = 0
    context_events: tuple[AdventureEvent, ...] = ()
    state_facts: tuple[AdventureStateFact, ...] = ()
    context_state_facts: tuple[AdventureStateFact, ...] = ()
    relationship_facts: tuple[AdventureRelationshipFact, ...] = ()
    context_relationship_facts: tuple[AdventureRelationshipFact, ...] = ()
    knowledge_facts: tuple[AdventureKnowledgeFact, ...] = ()
    context_knowledge_facts: tuple[AdventureKnowledgeFact, ...] = ()
    resource_catalog: AdventureResourceCatalog = AdventureResourceCatalog(())
    resource_facts: tuple[AdventureResourceFact, ...] = ()
    context_resource_facts: tuple[AdventureResourceFact, ...] = ()

    def __post_init__(self) -> None:
        if self.record is not None and not isinstance(self.record, AdventureRecord):
            raise TypeError("mounted adventure record must be an AdventureRecord or None")
        if not isinstance(self.event_count, int) or self.event_count < 0:
            raise ValueError("mounted adventure event count must be a non-negative integer")
        if not isinstance(self.context_events, tuple) or not all(isinstance(event, AdventureEvent) for event in self.context_events):
            raise TypeError("mounted adventure context events must be AdventureEvents")
        if not isinstance(self.state_facts, tuple) or not all(isinstance(fact, AdventureStateFact) for fact in self.state_facts):
            raise TypeError("mounted adventure state facts must be AdventureStateFacts")
        if not isinstance(self.context_state_facts, tuple) or not all(isinstance(fact, AdventureStateFact) for fact in self.context_state_facts):
            raise TypeError("mounted adventure context state facts must be AdventureStateFacts")
        if not isinstance(self.relationship_facts, tuple) or not all(isinstance(fact, AdventureRelationshipFact) for fact in self.relationship_facts):
            raise TypeError("mounted adventure relationship facts must be AdventureRelationshipFacts")
        if not isinstance(self.context_relationship_facts, tuple) or not all(isinstance(fact, AdventureRelationshipFact) for fact in self.context_relationship_facts):
            raise TypeError("mounted adventure context relationship facts must be AdventureRelationshipFacts")
        if not isinstance(self.knowledge_facts, tuple) or not all(isinstance(fact, AdventureKnowledgeFact) for fact in self.knowledge_facts):
            raise TypeError("mounted adventure knowledge facts must be AdventureKnowledgeFacts")
        if not isinstance(self.context_knowledge_facts, tuple) or not all(isinstance(fact, AdventureKnowledgeFact) for fact in self.context_knowledge_facts):
            raise TypeError("mounted adventure context knowledge facts must be AdventureKnowledgeFacts")
        if not isinstance(self.resource_catalog, AdventureResourceCatalog):
            raise TypeError("mounted adventure resource catalog must be an AdventureResourceCatalog")
        if not isinstance(self.resource_facts, tuple) or not all(isinstance(fact, AdventureResourceFact) for fact in self.resource_facts):
            raise TypeError("mounted adventure resource facts must be AdventureResourceFacts")
        if not isinstance(self.context_resource_facts, tuple) or not all(isinstance(fact, AdventureResourceFact) for fact in self.context_resource_facts):
            raise TypeError("mounted adventure context resource facts must be AdventureResourceFacts")
        if len(self.context_events) > MAX_CONTEXT_EVENTS:
            raise ValueError("mounted adventure context event limit exceeded")
        if len(self.context_state_facts) > MAX_CONTEXT_STATE_FACTS:
            raise ValueError("mounted adventure context state fact limit exceeded")
        if len(self.context_relationship_facts) > MAX_CONTEXT_RELATIONSHIP_FACTS:
            raise ValueError("mounted adventure context relationship fact limit exceeded")
        if len(self.context_knowledge_facts) > MAX_CONTEXT_KNOWLEDGE_FACTS:
            raise ValueError("mounted adventure context knowledge fact limit exceeded")
        if len(self.context_resource_facts) > MAX_CONTEXT_RESOURCE_FACTS:
            raise ValueError("mounted adventure context resource fact limit exceeded")
        if self.record is None and (
            self.event_count or self.context_events or self.state_facts or self.context_state_facts
            or self.relationship_facts or self.context_relationship_facts or self.knowledge_facts
            or self.context_knowledge_facts or self.resource_catalog.definitions
            or self.resource_facts or self.context_resource_facts
        ):
            raise ValueError("unmounted adventure state cannot contain events")
        if self.event_count < len(self.context_events):
            raise ValueError("mounted adventure event count cannot be smaller than context events")

    @classmethod
    def unmounted(cls) -> "AdventureSessionState":
        return cls()

    @property
    def active(self) -> bool:
        return self.record is not None

    def mount(
        self, record: AdventureRecord, events: list[AdventureEvent] | tuple[AdventureEvent, ...] = (),
        *, resource_catalog: AdventureResourceCatalog | None = None,
    ) -> "AdventureSessionState":
        """Mount only a bounded selection of validated events; never write them."""
        if not isinstance(events, (list, tuple)) or not all(isinstance(event, AdventureEvent) for event in events):
            raise TypeError("mounted adventure events must be AdventureEvents")
        total = len(events)
        if resource_catalog is None:
            resource_catalog = self.resource_catalog if self.record == record else AdventureResourceCatalog(())
        if not isinstance(resource_catalog, AdventureResourceCatalog):
            raise TypeError("mounted adventure resource catalog must be an AdventureResourceCatalog")
        state_facts = derive_adventure_state(events)
        relationship_facts = derive_adventure_relationships(events)
        knowledge_facts = derive_adventure_knowledge(events)
        resource_facts = derive_adventure_resource_facts(resource_catalog, events)
        return type(self)(
            record=record,
            event_count=total,
            # Resource values have their own public/hidden projection below.
            # Never let a free-form resource event summary leak a hidden value
            # through the generic replay-spine channel.
            context_events=select_replay_spine(
                tuple(event for event in events if event.event_type != "resource_change"),
            ),
            state_facts=state_facts,
            context_state_facts=select_adventure_state_context(state_facts),
            relationship_facts=relationship_facts,
            context_relationship_facts=select_adventure_relationship_context(relationship_facts),
            knowledge_facts=knowledge_facts,
            context_knowledge_facts=select_adventure_knowledge_context(knowledge_facts),
            resource_catalog=resource_catalog,
            resource_facts=resource_facts,
            context_resource_facts=select_adventure_resource_context(resource_facts),
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
            "context_state_fact_count": len(self.context_state_facts),
            "relationship_fact_count": len(self.relationship_facts),
            "context_relationship_fact_count": len(self.context_relationship_facts),
            "knowledge_fact_count": len(self.knowledge_facts),
            "context_knowledge_fact_count": len(self.context_knowledge_facts),
            "resource_fact_count": len(self.resource_facts),
            "context_resource_fact_count": len(self.context_resource_facts),
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
        events = "\n".join(f"- [{event.event_type}] {event.summary}" for event in self.context_events)
        state = ""
        if self.context_state_facts:
            state_lines = "\n".join(f"- {fact.key}: {fact.value}" for fact in self.context_state_facts)
            state = (
                "CURRENT AUTHORITATIVE STORY STATE (core-provided):\n"
                f"{len(self.state_facts)} total fact(s); {len(self.context_state_facts)} selected for bounded context.\n"
                f"{state_lines}\nEND CURRENT AUTHORITATIVE STORY STATE\n"
            )
        relationships = ""
        if self.context_relationship_facts:
            relationship_lines = "\n".join(
                f"- {fact.subject} / {fact.dimension}: {fact.value}"
                for fact in self.context_relationship_facts
            )
            relationships = (
                "CURRENT AUTHORITATIVE ADVENTURE RELATIONSHIPS (core-provided):\n"
                f"{len(self.relationship_facts)} total fact(s); {len(self.context_relationship_facts)} selected for bounded context.\n"
                f"{relationship_lines}\n"
                "END CURRENT AUTHORITATIVE ADVENTURE RELATIONSHIPS\n"
            )
        knowledge = ""
        if self.context_knowledge_facts:
            knowledge_lines = "\n".join(
                f"- {fact.subject} {fact.status}: {fact.fact}"
                for fact in self.context_knowledge_facts
            )
            knowledge = (
                "CHARACTER KNOWLEDGE AND BELIEFS (core-provided):\n"
                "These are character-specific perspectives, not automatically objective world truth.\n"
                f"{len(self.knowledge_facts)} total fact(s); {len(self.context_knowledge_facts)} selected for bounded context.\n"
                f"{knowledge_lines}\n"
                "END CHARACTER KNOWLEDGE AND BELIEFS\n"
            )
        resources = ""
        if self.context_resource_facts:
            resource_lines = "\n".join(
                f"- {fact.resource_id} ({fact.label}): {fact.value}"
                for fact in self.context_resource_facts
            )
            resources = (
                "CURRENT PUBLIC ADVENTURE RESOURCES (core-provided):\n"
                f"{len(self.resource_facts)} declared resource(s); {len(self.context_resource_facts)} public fact(s) selected for bounded context.\n"
                f"{resource_lines}\nEND CURRENT PUBLIC ADVENTURE RESOURCES\n"
            )
        if not self.context_events:
            return header + (
                "This workspace has no recorded authoritative adventure events. Do not invent prior story events, "
                "characters, relationships, replay history, or hidden narrative state. Keep ordinary assistant "
                "memory and real-world claims separate.\n"
                f"{resources}"
                "END MOUNTED ADVENTURE WORKSPACE"
            )
        return header + (
            f"Authoritative event log: {self.event_count} event(s); {len(self.context_events)} replay-spine facts are supplied below.\n"
            "These are established story facts, not user memories. Do not invent omitted events, details, or values.\n"
            f"{state}"
            f"{relationships}"
            f"{knowledge}"
            f"{resources}"
            "RECENT AUTHORITATIVE ADVENTURE EVENTS:\n"
            f"{events}\n"
            "END MOUNTED ADVENTURE WORKSPACE"
        )


__all__ = ["AdventureSessionState", "MAX_CONTEXT_EVENTS"]
