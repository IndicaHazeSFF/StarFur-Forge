"""Deterministic, explainable momentary-state derivation.

This module is deliberately a narrow foundation.  It accepts only explicit,
validated runtime signals and derives a short-lived :class:`MomentaryState`.
It does not infer emotion from ordinary chat, write canonical memories,
persist a mood, or alter a persona's durable traits.  Callers may later decide
which permitted interaction, relationship, or system events produce signals.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from pipeline.persona_state import MomentaryState


MAX_EMOTION_SIGNALS = 16
EMOTION_SIGNAL_KINDS = (
    "positive_interaction",
    "support_needed",
    "frustration",
    "fatigue",
    "focused_work",
    "interruption",
)
EMOTION_SIGNAL_SOURCES = (
    "explicit_user_statement",
    "approved_relationship_context",
    "approved_memory_context",
    "system_activity",
)
_SIGNAL_ID_RE = re.compile(r"^ES-[a-z0-9][a-z0-9_-]{0,63}$")


def _bounded_text(name: str, value: str, *, limit: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    value = value.strip()
    if not value:
        raise ValueError(f"{name} must not be empty.")
    if len(value) > limit:
        raise ValueError(f"{name} must be at most {limit} characters.")
    return value


def _unit_value(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number between 0.0 and 1.0.")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0.")
    return value


def _clamp_unit(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 4)


def _clamp_valence(value: float) -> float:
    return round(min(1.0, max(-1.0, value)), 4)


@dataclass(frozen=True)
class EmotionSignal:
    """One caller-authorized observation used only for a current derivation."""

    signal_id: str
    kind: str
    intensity: float
    source: str
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, str) or not _SIGNAL_ID_RE.fullmatch(self.signal_id):
            raise ValueError("signal_id must use the form ES-<stable-id>.")
        kind = _bounded_text("kind", self.kind, limit=64).casefold()
        if kind not in EMOTION_SIGNAL_KINDS:
            raise ValueError(f"kind must be one of {EMOTION_SIGNAL_KINDS}.")
        source = _bounded_text("source", self.source, limit=80).casefold()
        if source not in EMOTION_SIGNAL_SOURCES:
            raise ValueError(f"source must be one of {EMOTION_SIGNAL_SOURCES}.")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "intensity", _unit_value("intensity", self.intensity))
        if not isinstance(self.detail, str):
            raise TypeError("detail must be a string.")
        object.__setattr__(self, "detail", self.detail.strip()[:240])


@dataclass(frozen=True)
class EmotionContribution:
    """One bounded, inspectable contribution to an output snapshot."""

    signal_id: str
    kind: str
    source: str
    energy_delta: float = 0.0
    attention_delta: float = 0.0
    valence_delta: float = 0.0

    def public_dict(self) -> dict[str, str | float]:
        return {
            "signal_id": self.signal_id,
            "kind": self.kind,
            "source": self.source,
            "energy_delta": self.energy_delta,
            "attention_delta": self.attention_delta,
            "valence_delta": self.valence_delta,
        }


@dataclass(frozen=True)
class DerivedEmotionState:
    """Ephemeral result with provenance; never a canonical fact or trait update."""

    momentary_state: MomentaryState
    contributions: tuple[EmotionContribution, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "momentary_state": self.momentary_state.public_dict(),
            "contributions": [item.public_dict() for item in self.contributions],
        }


_DELTAS: dict[str, tuple[float, float, float]] = {
    "positive_interaction": (0.05, 0.05, 0.35),
    "support_needed": (-0.05, 0.10, -0.15),
    "frustration": (-0.10, -0.05, -0.45),
    "fatigue": (-0.45, -0.20, -0.10),
    "focused_work": (0.00, 0.40, 0.05),
    "interruption": (0.00, -0.30, -0.05),
}


def derive_emotion_state(
    signals: Iterable[EmotionSignal],
    *,
    baseline: MomentaryState | None = None,
    activity: str | None = None,
) -> DerivedEmotionState:
    """Derive a fresh, deterministic state from explicit observations only.

    The supplied baseline is read-only.  Signal order cannot affect the result;
    duplicate signal IDs are rejected so callers cannot accidentally count the
    same observation twice.
    """
    baseline = baseline or MomentaryState()
    if not isinstance(baseline, MomentaryState):
        raise TypeError("baseline must be a MomentaryState or None.")
    values = tuple(signals)
    if len(values) > MAX_EMOTION_SIGNALS:
        raise ValueError(f"signals must contain at most {MAX_EMOTION_SIGNALS} entries.")
    if not all(isinstance(signal, EmotionSignal) for signal in values):
        raise TypeError("signals must contain EmotionSignal values.")
    if len({signal.signal_id for signal in values}) != len(values):
        raise ValueError("signals must not contain duplicate signal IDs.")

    energy = baseline.energy
    attention = baseline.attention
    valence = baseline.valence
    contributions: list[EmotionContribution] = []
    for signal in sorted(values, key=lambda item: item.signal_id):
        base_energy, base_attention, base_valence = _DELTAS[signal.kind]
        energy_delta = round(base_energy * signal.intensity, 4)
        attention_delta = round(base_attention * signal.intensity, 4)
        valence_delta = round(base_valence * signal.intensity, 4)
        energy += energy_delta
        attention += attention_delta
        valence += valence_delta
        contributions.append(EmotionContribution(
            signal.signal_id,
            signal.kind,
            signal.source,
            energy_delta,
            attention_delta,
            valence_delta,
        ))

    state = MomentaryState(
        energy=_clamp_unit(energy),
        attention=_clamp_unit(attention),
        valence=_clamp_valence(valence),
        activity=activity if activity is not None else baseline.activity,
    )
    return DerivedEmotionState(state, tuple(contributions))


__all__ = [
    "EMOTION_SIGNAL_KINDS",
    "EMOTION_SIGNAL_SOURCES",
    "MAX_EMOTION_SIGNALS",
    "DerivedEmotionState",
    "EmotionContribution",
    "EmotionSignal",
    "derive_emotion_state",
]
