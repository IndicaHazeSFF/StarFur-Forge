"""Deterministic, explainable relationship-state derivation.

Relationship state is a bounded presentation/runtime signal, not a canonical
claim about a person. This first slice accepts only explicit authorized
signals. It does not inspect ordinary chat, write user memory, persist data,
or affect assistant prompts. Adventure relationships must remain in their
future ``adventure:<id>`` namespace and never use this real-world layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from pipeline.persona_state import PERSONA_ID_RE


MAX_RELATIONSHIP_SIGNALS = 16
RELATIONSHIP_SIGNAL_KINDS = (
    "positive_interaction",
    "familiar_interaction",
    "boundary_respected",
    "trust_breach",
    "repair_attempt",
)
RELATIONSHIP_SIGNAL_SOURCES = (
    "explicit_user_statement",
    "explicit_user_correction",
    "approved_relationship_context",
    "approved_memory_context",
)
_SIGNAL_ID_RE = re.compile(r"^RS-[a-z0-9][a-z0-9_-]{0,63}$")
_MAX_STATE_VALUE = 0.9999


def _identifier(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    value = value.strip().casefold()
    if not PERSONA_ID_RE.fullmatch(value):
        raise ValueError(f"{name} must be a valid namespaced identifier.")
    return value


def _subunit_value(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number from 0.0 up to but not including 1.0.")
    value = float(value)
    if not 0.0 <= value < 1.0:
        raise ValueError(f"{name} must be from 0.0 up to but not including 1.0.")
    return value


def _text_choice(name: str, value: str, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    value = value.strip().casefold()
    if value not in choices:
        raise ValueError(f"{name} must be one of {choices}.")
    return value


@dataclass(frozen=True)
class RelationshipState:
    """One persona's bounded, non-canonical state toward a stable subject."""

    persona_id: str
    subject_id: str
    familiarity: float = 0.0
    trust: float = 0.5
    confidence: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "persona_id", _identifier("persona_id", self.persona_id))
        object.__setattr__(self, "subject_id", _identifier("subject_id", self.subject_id))
        for name in ("familiarity", "trust", "confidence"):
            object.__setattr__(self, name, _subunit_value(name, getattr(self, name)))

    def public_dict(self) -> dict[str, str | float]:
        return {
            "persona_id": self.persona_id,
            "subject_id": self.subject_id,
            "familiarity": self.familiarity,
            "trust": self.trust,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class RelationshipSignal:
    """A caller-authorized relationship observation for a single derivation."""

    signal_id: str
    kind: str
    intensity: float
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, str) or not _SIGNAL_ID_RE.fullmatch(self.signal_id):
            raise ValueError("signal_id must use the form RS-<stable-id>.")
        object.__setattr__(self, "kind", _text_choice("kind", self.kind, RELATIONSHIP_SIGNAL_KINDS))
        object.__setattr__(self, "source", _text_choice("source", self.source, RELATIONSHIP_SIGNAL_SOURCES))
        object.__setattr__(self, "intensity", _subunit_value("intensity", self.intensity))


@dataclass(frozen=True)
class RelationshipContribution:
    """One inspectable change produced from an explicit signal."""

    signal_id: str
    kind: str
    source: str
    familiarity_delta: float
    trust_delta: float
    confidence_delta: float

    def public_dict(self) -> dict[str, str | float]:
        return {
            "signal_id": self.signal_id,
            "kind": self.kind,
            "source": self.source,
            "familiarity_delta": self.familiarity_delta,
            "trust_delta": self.trust_delta,
            "confidence_delta": self.confidence_delta,
        }


@dataclass(frozen=True)
class DerivedRelationshipState:
    """Ephemeral derived state plus the bounded signals that explain it."""

    state: RelationshipState
    contributions: tuple[RelationshipContribution, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "state": self.state.public_dict(),
            "contributions": [item.public_dict() for item in self.contributions],
        }


# Positive deltas asymptotically approach 1.0; negative deltas scale with the
# amount of current state, so a single weak signal cannot invent a total bond
# or erase it outright.
_DELTAS: dict[str, tuple[float, float, float]] = {
    "positive_interaction": (0.10, 0.12, 0.08),
    "familiar_interaction": (0.18, 0.04, 0.06),
    "boundary_respected": (0.03, 0.16, 0.10),
    "trust_breach": (-0.03, -0.38, 0.04),
    "repair_attempt": (0.04, 0.10, 0.12),
}


def _apply_delta(value: float, delta: float, intensity: float) -> tuple[float, float]:
    if delta >= 0.0:
        actual = delta * intensity * (1.0 - value)
    else:
        actual = delta * intensity * value
    return min(_MAX_STATE_VALUE, max(0.0, value + actual)), round(actual, 4)


def derive_relationship_state(
    signals: Iterable[RelationshipSignal],
    *,
    baseline: RelationshipState,
) -> DerivedRelationshipState:
    """Return a fresh state from explicit signals without mutating ``baseline``."""
    if not isinstance(baseline, RelationshipState):
        raise TypeError("baseline must be a RelationshipState instance.")
    values = tuple(signals)
    if len(values) > MAX_RELATIONSHIP_SIGNALS:
        raise ValueError(f"signals must contain at most {MAX_RELATIONSHIP_SIGNALS} entries.")
    if not all(isinstance(signal, RelationshipSignal) for signal in values):
        raise TypeError("signals must contain RelationshipSignal values.")
    if len({signal.signal_id for signal in values}) != len(values):
        raise ValueError("signals must not contain duplicate signal IDs.")

    familiarity = baseline.familiarity
    trust = baseline.trust
    confidence = baseline.confidence
    contributions: list[RelationshipContribution] = []
    for signal in sorted(values, key=lambda item: item.signal_id):
        familiarity_weight, trust_weight, confidence_weight = _DELTAS[signal.kind]
        familiarity, familiarity_delta = _apply_delta(familiarity, familiarity_weight, signal.intensity)
        trust, trust_delta = _apply_delta(trust, trust_weight, signal.intensity)
        confidence, confidence_delta = _apply_delta(confidence, confidence_weight, signal.intensity)
        contributions.append(RelationshipContribution(
            signal.signal_id,
            signal.kind,
            signal.source,
            familiarity_delta,
            trust_delta,
            confidence_delta,
        ))

    return DerivedRelationshipState(
        RelationshipState(
            baseline.persona_id,
            baseline.subject_id,
            familiarity=round(familiarity, 4),
            trust=round(trust, 4),
            confidence=round(confidence, 4),
        ),
        tuple(contributions),
    )


__all__ = [
    "MAX_RELATIONSHIP_SIGNALS",
    "RELATIONSHIP_SIGNAL_KINDS",
    "RELATIONSHIP_SIGNAL_SOURCES",
    "DerivedRelationshipState",
    "RelationshipContribution",
    "RelationshipSignal",
    "RelationshipState",
    "derive_relationship_state",
]
