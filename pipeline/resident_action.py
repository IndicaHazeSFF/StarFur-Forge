"""Typed, provider-free visible resident activity for apartment presentation.

An action is a Core-selected presentation fact, not a claim about inner life,
an inference from chat, or a task scheduler.  It remains restart-ephemeral
until a reviewed resident-continuity policy exists.
"""

from __future__ import annotations

from dataclasses import dataclass


RESIDENT_ACTION_KINDS = frozenset({
    "idle", "resting", "reading", "working", "waiting", "chatting", "adventuring",
})
RESIDENT_ACTION_SOURCES = frozenset({"core_default", "explicit_core"})


@dataclass(frozen=True)
class ResidentAction:
    """One bounded visual activity for one persona-local runtime."""

    persona_id: str
    kind: str = "idle"
    source: str = "core_default"

    def __post_init__(self) -> None:
        if not isinstance(self.persona_id, str) or not self.persona_id.strip():
            raise ValueError("resident action persona identifier is invalid")
        if self.kind not in RESIDENT_ACTION_KINDS:
            raise ValueError("resident action kind is invalid")
        if self.source not in RESIDENT_ACTION_SOURCES:
            raise ValueError("resident action source is invalid")
        object.__setattr__(self, "persona_id", self.persona_id.strip().casefold())

    @classmethod
    def idle(cls, persona_id: str) -> "ResidentAction":
        return cls(persona_id=persona_id)

    def public_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "source": self.source, "storage": "restart_ephemeral"}


__all__ = ["RESIDENT_ACTION_KINDS", "ResidentAction"]
