"""Pure resident-to-presentation mapping for read-only apartment clients.

The apartment must not parse chat prose or invent state.  It can, however,
render a stable generic visual slot selected from the already-public resident
snapshot.  Asset packages resolve these slots later; this module never opens a
file, loads art, calls a provider, or mutates a session.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


_VISUAL_BY_ACTIVITY = {
    "idle": "idle",
    "generating": "thinking",
    "streaming": "thinking",
    "reviewing_candidates": "reviewing",
    "staging_adventure_turn": "planning",
    "roleplaying": "roleplaying",
    "adventure_ready": "adventuring",
    "provider_error": "provider_error",
    "provider_unavailable": "offline",
}
_VISUAL_BY_RESIDENT_ACTION = {
    "idle": "idle", "resting": "resting", "reading": "reading",
    "working": "working", "waiting": "waiting", "chatting": "chatting",
    "adventuring": "adventuring",
}


@dataclass(frozen=True)
class ResidentPresentationPlan:
    """Small data-only plan for one apartment/dashboard render pass."""

    persona_id: str | None
    visual_state: str
    activity: str

    def __post_init__(self) -> None:
        if self.persona_id is not None and (not isinstance(self.persona_id, str) or not self.persona_id):
            raise ValueError("presentation persona identifier is invalid")
        if self.visual_state not in set(_VISUAL_BY_ACTIVITY.values()) | set(_VISUAL_BY_RESIDENT_ACTION.values()):
            raise ValueError("presentation visual state is invalid")
        if self.activity not in _VISUAL_BY_ACTIVITY:
            raise ValueError("presentation activity is invalid")

    @classmethod
    def from_resident_snapshot(cls, snapshot: Mapping[str, object]) -> "ResidentPresentationPlan":
        """Build a generic asset-slot plan from a public snapshot payload."""
        if not isinstance(snapshot, Mapping):
            raise TypeError("resident snapshot must be a mapping")
        activity = snapshot.get("activity")
        if not isinstance(activity, str) or activity not in _VISUAL_BY_ACTIVITY:
            raise ValueError("resident snapshot activity is invalid")
        persona = snapshot.get("persona")
        persona_id = persona.get("persona_id") if isinstance(persona, Mapping) else None
        if persona_id is not None and not isinstance(persona_id, str):
            raise ValueError("resident snapshot persona identifier is invalid")
        # A real provider/session activity always wins. A resident action can
        # affect visual idle behavior only while Core reports no busier state.
        resident_action = persona.get("resident_action") if isinstance(persona, Mapping) else None
        action_kind = resident_action.get("kind") if isinstance(resident_action, Mapping) else None
        visual_state = (
            _VISUAL_BY_RESIDENT_ACTION[action_kind]
            if activity == "idle" and action_kind in _VISUAL_BY_RESIDENT_ACTION
            else _VISUAL_BY_ACTIVITY[activity]
        )
        return cls(persona_id=persona_id, activity=activity, visual_state=visual_state)

    def public_dict(self) -> dict[str, object]:
        """Return asset *slots*, never paths or package-installed assets."""
        actor_slot = "resident.default" if self.persona_id is None else f"resident.{self.persona_id}"
        return {
            "visual_state": self.visual_state,
            "actor_slot": actor_slot,
            "animation_slot": f"{actor_slot}.{self.visual_state}",
            "scene_slot": "apartment.default",
            "storage": "presentation_ephemeral",
        }


__all__ = ["ResidentPresentationPlan"]
