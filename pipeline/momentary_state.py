"""Conservative transitions for ephemeral Persona Runtime state.

The emotion layer produces a candidate state from explicit signals. This module
decays prior state toward a neutral baseline and rate-limits movement toward a
candidate. It is deterministic, read-only, and intentionally has no clock,
storage, prompt, or chat-inference dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.persona_state import MomentaryState


def _number(name: str, value: float, *, minimum: float, maximum: float, inclusive_maximum: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")
    value = float(value)
    valid = minimum <= value <= maximum if inclusive_maximum else minimum <= value < maximum
    if not valid:
        edge = "through" if inclusive_maximum else "up to but not including"
        raise ValueError(f"{name} must be from {minimum} {edge} {maximum}.")
    return value


def _unit(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 4)


def _valence(value: float) -> float:
    return round(min(1.0, max(-1.0, value)), 4)


@dataclass(frozen=True)
class MomentaryTransitionPolicy:
    """Bounded decay and hysteresis controls for one transition."""

    half_life_seconds: float = 300.0
    min_change: float = 0.02
    max_step: float = 0.25

    def __post_init__(self) -> None:
        object.__setattr__(self, "half_life_seconds", _number(
            "half_life_seconds", self.half_life_seconds, minimum=0.1, maximum=86_400.0,
        ))
        object.__setattr__(self, "min_change", _number(
            "min_change", self.min_change, minimum=0.0, maximum=1.0, inclusive_maximum=False,
        ))
        object.__setattr__(self, "max_step", _number(
            "max_step", self.max_step, minimum=0.0001, maximum=1.0,
        ))


@dataclass(frozen=True)
class MomentaryStateTransition:
    """An inspectable ephemeral snapshot; it is never a memory record."""

    state: MomentaryState
    elapsed_seconds: float
    decay_retention: float
    applied_fields: tuple[str, ...]
    held_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.state, MomentaryState):
            raise TypeError("state must be a MomentaryState instance.")
        object.__setattr__(self, "elapsed_seconds", _number(
            "elapsed_seconds", self.elapsed_seconds, minimum=0.0, maximum=86_400.0,
        ))
        object.__setattr__(self, "decay_retention", _number(
            "decay_retention", self.decay_retention, minimum=0.0, maximum=1.0,
        ))
        valid_fields = {"energy", "attention", "valence"}
        for name in ("applied_fields", "held_fields"):
            fields = tuple(getattr(self, name))
            if any(field not in valid_fields for field in fields):
                raise ValueError(f"{name} contains an unknown state field.")
            if tuple(sorted(set(fields))) != fields:
                raise ValueError(f"{name} must contain sorted unique fields.")
            object.__setattr__(self, name, fields)

    def public_dict(self) -> dict[str, object]:
        return {
            "state": self.state.public_dict(),
            "elapsed_seconds": self.elapsed_seconds,
            "decay_retention": self.decay_retention,
            "applied_fields": list(self.applied_fields),
            "held_fields": list(self.held_fields),
        }


def _decayed(previous: MomentaryState, retention: float) -> dict[str, float]:
    return {
        "energy": 0.5 + (previous.energy - 0.5) * retention,
        "attention": 0.5 + (previous.attention - 0.5) * retention,
        "valence": previous.valence * retention,
    }


def transition_momentary_state(
    previous: MomentaryState,
    candidate: MomentaryState,
    *,
    elapsed_seconds: float,
    policy: MomentaryTransitionPolicy | None = None,
) -> MomentaryStateTransition:
    """Decay prior state, then apply a bounded candidate-state adjustment."""
    if not isinstance(previous, MomentaryState) or not isinstance(candidate, MomentaryState):
        raise TypeError("previous and candidate must be MomentaryState instances.")
    policy = policy or MomentaryTransitionPolicy()
    if not isinstance(policy, MomentaryTransitionPolicy):
        raise TypeError("policy must be a MomentaryTransitionPolicy or None.")
    elapsed = _number("elapsed_seconds", elapsed_seconds, minimum=0.0, maximum=86_400.0)
    retention = 2 ** (-elapsed / policy.half_life_seconds)
    decayed = _decayed(previous, retention)

    values: dict[str, float] = {}
    applied: list[str] = []
    held: list[str] = []
    for field in ("energy", "attention", "valence"):
        difference = getattr(candidate, field) - decayed[field]
        if abs(difference) < policy.min_change:
            values[field] = decayed[field]
            held.append(field)
            continue
        step = min(policy.max_step, abs(difference)) * (1.0 if difference > 0.0 else -1.0)
        values[field] = decayed[field] + step
        applied.append(field)

    activity = candidate.activity if applied else previous.activity
    return MomentaryStateTransition(
        MomentaryState(
            energy=_unit(values["energy"]),
            attention=_unit(values["attention"]),
            valence=_valence(values["valence"]),
            activity=activity,
        ),
        elapsed_seconds=round(elapsed, 4),
        decay_retention=round(retention, 6),
        applied_fields=tuple(sorted(applied)),
        held_fields=tuple(sorted(held)),
    )


__all__ = [
    "MomentaryStateTransition",
    "MomentaryTransitionPolicy",
    "transition_momentary_state",
]
