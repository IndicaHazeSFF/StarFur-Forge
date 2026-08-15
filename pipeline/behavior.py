"""Presentation-only behavior guidance derived from Persona Runtime state.

The mapper converts already validated trait and momentary snapshots into small,
bounded controls for prompt rendering and diagnostics. It cannot change those
snapshots, create facts, grant capabilities, or override Core policy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from pipeline.persona_state import BehaviorContext


def _control(value: float) -> float:
    """Keep derived controls bounded below a claimed perfect value."""
    return round(min(0.9999, max(0.0, value)), 4)


@dataclass(frozen=True)
class BehaviorGuidance:
    """Small, explainable controls for presentation—not facts or commands."""

    warmth: float
    directness: float
    humor: float
    initiative: float
    patience: float
    verbosity: float
    clarification_threshold: float
    interruption_tolerance: float
    activity: str

    def __post_init__(self) -> None:
        for name in (
            "warmth", "directness", "humor", "initiative", "patience",
            "verbosity", "clarification_threshold", "interruption_tolerance",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a numeric behavior control.")
            if not 0.0 <= float(value) < 1.0:
                raise ValueError(f"{name} must be from 0.0 up to but not including 1.0.")
            object.__setattr__(self, name, float(value))
        if not isinstance(self.activity, str) or not self.activity.strip():
            raise ValueError("activity must be non-empty.")
        object.__setattr__(self, "activity", self.activity.strip())

    def public_dict(self) -> dict[str, float | str]:
        return asdict(self)


def derive_behavior_guidance(context: BehaviorContext) -> BehaviorGuidance:
    """Map validated runtime state to bounded presentation controls.

    State effects stay deliberately small: durable persona traits remain the
    dominant influence, while momentary state can only nudge tone and response
    handling. This function is deterministic and read-only.
    """
    if not isinstance(context, BehaviorContext):
        raise TypeError("context must be a BehaviorContext instance.")
    traits = context.dynamic_traits
    momentary = context.momentary_state
    valence = momentary.valence
    energy_gap = 1.0 - momentary.energy
    attention_gap = 1.0 - momentary.attention
    return BehaviorGuidance(
        warmth=_control(traits.warmth + 0.12 * valence),
        directness=_control(traits.directness + 0.08 * attention_gap),
        humor=_control(traits.humor + 0.10 * valence),
        initiative=_control(traits.initiative + 0.10 * valence),
        patience=_control(traits.patience + 0.10 * energy_gap - 0.05 * valence),
        verbosity=_control(traits.verbosity + 0.08 * momentary.energy - 0.04 * attention_gap),
        clarification_threshold=_control(0.25 + 0.25 * attention_gap + 0.15 * energy_gap),
        interruption_tolerance=_control(0.35 + 0.25 * momentary.attention + 0.10 * momentary.energy),
        activity=momentary.activity,
    )


__all__ = ["BehaviorGuidance", "derive_behavior_guidance"]
