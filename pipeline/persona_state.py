"""Validated, immutable foundations for the Persona Runtime.

These structures describe persona state only. They do not load files, render
prompts, derive emotions, persist state, or alter assistant behavior yet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any, Mapping


PERSONA_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
TRAIT_NAMES = (
    "warmth",
    "directness",
    "humor",
    "curiosity",
    "initiative",
    "patience",
    "verbosity",
)


def _unit_value(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number between 0.0 and 1.0.")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0.")
    return normalized


def _nonempty_text(name: str, value: str, *, limit: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty.")
    if len(normalized) > limit:
        raise ValueError(f"{name} must be at most {limit} characters.")
    return normalized


@dataclass(frozen=True)
class DynamicTraits:
    """Slow-changing, bounded presentation preferences for one persona."""

    warmth: float = 0.5
    directness: float = 0.5
    humor: float = 0.5
    curiosity: float = 0.5
    initiative: float = 0.5
    patience: float = 0.5
    verbosity: float = 0.5

    def __post_init__(self) -> None:
        for name in TRAIT_NAMES:
            object.__setattr__(self, name, _unit_value(name, getattr(self, name)))

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "DynamicTraits":
        if not isinstance(values, Mapping):
            raise TypeError("Dynamic traits must be a mapping.")
        unknown = set(values) - set(TRAIT_NAMES)
        if unknown:
            raise ValueError(f"Unknown dynamic trait(s): {sorted(unknown)}")
        return cls(**dict(values))

    def public_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class MomentaryState:
    """Bounded, derived runtime state; not canonical memory or personality."""

    energy: float = 0.5
    attention: float = 0.5
    valence: float = 0.0
    activity: str = "idle"

    def __post_init__(self) -> None:
        object.__setattr__(self, "energy", _unit_value("energy", self.energy))
        object.__setattr__(self, "attention", _unit_value("attention", self.attention))
        if isinstance(self.valence, bool) or not isinstance(self.valence, (int, float)):
            raise TypeError("valence must be a number between -1.0 and 1.0.")
        valence = float(self.valence)
        if not -1.0 <= valence <= 1.0:
            raise ValueError("valence must be between -1.0 and 1.0.")
        object.__setattr__(self, "valence", valence)
        object.__setattr__(self, "activity", _nonempty_text("activity", self.activity, limit=80))

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "MomentaryState":
        if not isinstance(values, Mapping):
            raise TypeError("Momentary state must be a mapping.")
        known = {"energy", "attention", "valence", "activity"}
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"Unknown momentary state field(s): {sorted(unknown)}")
        return cls(**dict(values))

    def public_dict(self) -> dict[str, float | str]:
        return asdict(self)


@dataclass(frozen=True)
class PersonaState:
    """One persona's static identity plus bounded dynamic and momentary state."""

    persona_id: str
    display_name: str
    static_identity: str
    dynamic_traits: DynamicTraits = field(default_factory=DynamicTraits)
    momentary_state: MomentaryState = field(default_factory=MomentaryState)

    def __post_init__(self) -> None:
        persona_id = _nonempty_text("persona_id", self.persona_id, limit=64).casefold()
        if not PERSONA_ID_RE.fullmatch(persona_id):
            raise ValueError("persona_id must start with a lowercase letter and contain only lowercase letters, digits, _ or -.")
        object.__setattr__(self, "persona_id", persona_id)
        object.__setattr__(self, "display_name", _nonempty_text("display_name", self.display_name, limit=120))
        object.__setattr__(self, "static_identity", _nonempty_text("static_identity", self.static_identity, limit=20_000))
        if not isinstance(self.dynamic_traits, DynamicTraits):
            raise TypeError("dynamic_traits must be a DynamicTraits instance.")
        if not isinstance(self.momentary_state, MomentaryState):
            raise TypeError("momentary_state must be a MomentaryState instance.")

    def public_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "display_name": self.display_name,
            "dynamic_traits": self.dynamic_traits.public_dict(),
            "momentary_state": self.momentary_state.public_dict(),
        }


@dataclass(frozen=True)
class BehaviorContext:
    """A validated snapshot intended for future, read-only context rendering."""

    persona_id: str
    dynamic_traits: DynamicTraits
    momentary_state: MomentaryState

    def __post_init__(self) -> None:
        persona_id = _nonempty_text("persona_id", self.persona_id, limit=64).casefold()
        if not PERSONA_ID_RE.fullmatch(persona_id):
            raise ValueError("persona_id must be a valid PersonaState identifier.")
        object.__setattr__(self, "persona_id", persona_id)
        if not isinstance(self.dynamic_traits, DynamicTraits):
            raise TypeError("dynamic_traits must be a DynamicTraits instance.")
        if not isinstance(self.momentary_state, MomentaryState):
            raise TypeError("momentary_state must be a MomentaryState instance.")

    @classmethod
    def from_persona_state(cls, state: PersonaState) -> "BehaviorContext":
        if not isinstance(state, PersonaState):
            raise TypeError("state must be a PersonaState instance.")
        return cls(state.persona_id, state.dynamic_traits, state.momentary_state)

    def public_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "dynamic_traits": self.dynamic_traits.public_dict(),
            "momentary_state": self.momentary_state.public_dict(),
        }


__all__ = [
    "PERSONA_ID_RE",
    "TRAIT_NAMES",
    "BehaviorContext",
    "DynamicTraits",
    "MomentaryState",
    "PersonaState",
]