"""Ephemeral, persona-namespaced runtime state.

This module is the single in-memory owner for mutable *persona-local* runtime
snapshots.  It deliberately does not persist state, inspect ordinary chat,
access shared assistant memories, or perform any relationship/apartment
inference.  Those systems can later store their validated snapshots here under
the same persona identifier without being confused with another persona.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
from typing import Iterable

from pipeline.persona_development import PersonaDevelopmentState
from pipeline.persona_state import PersonaState
from pipeline.relationship import RelationshipState
from pipeline.resident_action import ResidentAction


@dataclass(frozen=True)
class PersonaRuntimeState:
    """One bounded runtime snapshot, isolated by persona identifier.

    ``persona_state`` owns dynamic traits and momentary state. Development owns
    interests/skills/learning evidence. Relationship snapshots and one typed
    visible resident action stay local to this persona and restart-ephemeral.
    """

    persona_state: PersonaState
    development_state: PersonaDevelopmentState
    relationship_states: tuple[RelationshipState, ...] = ()
    resident_action: ResidentAction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.persona_state, PersonaState):
            raise TypeError("persona_state must be a PersonaState instance.")
        if not isinstance(self.development_state, PersonaDevelopmentState):
            raise TypeError("development_state must be a PersonaDevelopmentState instance.")
        if self.persona_state.persona_id != self.development_state.persona_id:
            raise ValueError("persona_state and development_state must use the same persona_id.")
        if not isinstance(self.relationship_states, tuple) or not all(
            isinstance(item, RelationshipState) for item in self.relationship_states
        ):
            raise TypeError("relationship_states must be a tuple of RelationshipState instances.")
        if any(item.persona_id != self.persona_state.persona_id for item in self.relationship_states):
            raise ValueError("relationship_states must use the runtime persona_id.")
        subjects = tuple(item.subject_id for item in self.relationship_states)
        if len(set(subjects)) != len(subjects):
            raise ValueError("relationship_states must not repeat a subject_id.")
        object.__setattr__(self, "relationship_states", tuple(sorted(self.relationship_states, key=lambda item: item.subject_id)))
        action = self.resident_action or ResidentAction.idle(self.persona_state.persona_id)
        if not isinstance(action, ResidentAction):
            raise TypeError("resident_action must be a ResidentAction or None")
        if action.persona_id != self.persona_state.persona_id:
            raise ValueError("resident_action persona_id must match the runtime persona_id.")
        object.__setattr__(self, "resident_action", action)

    @property
    def persona_id(self) -> str:
        return self.persona_state.persona_id

    @classmethod
    def from_persona_state(
        cls,
        persona_state: PersonaState,
        development_state: PersonaDevelopmentState | None = None,
        relationship_states: Iterable[RelationshipState] = (),
    ) -> "PersonaRuntimeState":
        return cls(
            persona_state=persona_state,
            development_state=development_state or PersonaDevelopmentState.empty(persona_state.persona_id),
            relationship_states=tuple(relationship_states),
        )

    def with_relationship_state(self, relationship_state: RelationshipState) -> "PersonaRuntimeState":
        """Return a new snapshot with one validated real-world relationship state.

        This does not derive a state from chat or inject it into prompts. Callers
        must use the existing explicit-signal relationship derivation first.
        """
        if not isinstance(relationship_state, RelationshipState):
            raise TypeError("relationship_state must be a RelationshipState instance.")
        if relationship_state.persona_id != self.persona_id:
            raise ValueError("relationship_state persona_id must match the runtime persona_id.")
        updated = tuple(
            relationship_state if item.subject_id == relationship_state.subject_id else item
            for item in self.relationship_states
        )
        if not any(item.subject_id == relationship_state.subject_id for item in self.relationship_states):
            updated = (*updated, relationship_state)
        return replace(self, relationship_states=updated)

    def with_resident_action(self, resident_action: ResidentAction) -> "PersonaRuntimeState":
        """Return this persona's runtime with one already Core-authorized action.

        The registry does not decide when to call this.  In particular, normal
        chat and provider output may not manufacture an action by invoking this
        value object directly.
        """
        if not isinstance(resident_action, ResidentAction):
            raise TypeError("resident_action must be a ResidentAction instance.")
        if resident_action.persona_id != self.persona_id:
            raise ValueError("resident_action persona_id must match the runtime persona_id.")
        return replace(self, resident_action=resident_action)

    def public_dict(self) -> dict[str, object]:
        """Return a bounded UI-safe snapshot without prompts, evidence, or subjects."""
        return {
            "persona_id": self.persona_id,
            "display_name": self.persona_state.display_name,
            "dynamic_traits": self.persona_state.dynamic_traits.public_dict(),
            "momentary_state": self.persona_state.momentary_state.public_dict(),
            "development": {
                "interest_count": len(self.development_state.interests),
                "verified_skill_count": len(self.development_state.skills),
                "learning_record_count": len(self.development_state.learning_records),
                "reference_record_count": len(self.development_state.reference_records),
            },
            "real_world_relationship_count": len(self.relationship_states),
            "resident_action": self.resident_action.public_dict(),
            "storage": "restart_ephemeral",
        }


class PersonaRuntimeRegistry:
    """Thread-safe, restart-ephemeral runtime state keyed only by persona ID."""

    def __init__(self, states: tuple[PersonaRuntimeState, ...] = ()) -> None:
        self._lock = RLock()
        self._states: dict[str, PersonaRuntimeState] = {}
        for state in states:
            self.replace(state)

    def ensure(
        self,
        persona_state: PersonaState,
        development_state: PersonaDevelopmentState | None = None,
    ) -> PersonaRuntimeState:
        """Return an existing persona-local snapshot or seed one deterministically."""
        if not isinstance(persona_state, PersonaState):
            raise TypeError("persona_state must be a PersonaState instance.")
        seeded = PersonaRuntimeState.from_persona_state(persona_state, development_state)
        with self._lock:
            return self._states.setdefault(seeded.persona_id, seeded)

    def snapshot(self, persona_id: str) -> PersonaRuntimeState | None:
        if not isinstance(persona_id, str):
            raise TypeError("persona_id must be a string.")
        with self._lock:
            return self._states.get(persona_id.strip().casefold())

    def replace(self, state: PersonaRuntimeState) -> PersonaRuntimeState:
        if not isinstance(state, PersonaRuntimeState):
            raise TypeError("state must be a PersonaRuntimeState instance.")
        with self._lock:
            self._states[state.persona_id] = state
            return state

    def public_snapshot(self, persona_id: str) -> dict[str, object] | None:
        """Return one UI-safe runtime snapshot without creating or mutating state."""
        state = self.snapshot(persona_id)
        return None if state is None else state.public_dict()


__all__ = ["PersonaRuntimeRegistry", "PersonaRuntimeState"]
