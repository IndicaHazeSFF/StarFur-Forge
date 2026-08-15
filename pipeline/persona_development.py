"""Bounded, namespaced foundations for persona interests and verified skills.

This module intentionally does not load or persist data, alter prompts, or
derive learning from chat.  It provides the small deterministic state model
that later RSS, sandbox, and verified-learning work can use without sharing
persona-local development with user-controlled assistant memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import math
import re
from threading import RLock
from typing import Iterable

from pipeline.persona_state import PERSONA_ID_RE


MAX_DEVELOPMENT_RECORDS = 64
MAX_LEARNING_RECORDS = 128
MAX_REFERENCE_RECORDS = 128
MAX_CONCEPT_LENGTH = 120
MAX_EVIDENCE_COUNT = 100_000
DEFAULT_INTEREST_HALF_LIFE_DAYS = 90.0
DEFAULT_SKILL_HALF_LIFE_DAYS = 180.0
LEARNING_OUTCOMES = ("verified_success", "verified_failure", "inconclusive")
LEARNING_SOURCES = ("manual", "reference", "sandbox", "imported")
REFERENCE_SOURCES = ("rss", "manual_reference", "imported")
_LEARNING_ID_RE = re.compile(r"^LR-[a-z0-9][a-z0-9_-]{0,63}$")
_REFERENCE_ID_RE = re.compile(r"^RI-[a-z0-9][a-z0-9_-]{0,63}$")


def _persona_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("persona_id must be a string.")
    normalized = value.strip().casefold()
    if not PERSONA_ID_RE.fullmatch(normalized):
        raise ValueError("persona_id must be a valid PersonaState identifier.")
    return normalized


def _concept(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("concept must be a string.")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("concept must not be empty.")
    if len(normalized) > MAX_CONCEPT_LENGTH:
        raise ValueError(f"concept must be at most {MAX_CONCEPT_LENGTH} characters.")
    return normalized


def _concept_key(value: str) -> str:
    return _concept(value).casefold()


def _bounded_text(name: str, value: str, *, limit: int) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError(f"{name} must not be empty.")
    if len(normalized) > limit:
        raise ValueError(f"{name} must be at most {limit} characters.")
    return normalized


def _confidence(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("confidence must be a number from 0.0 up to, but not including, 1.0.")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized < 1.0:
        raise ValueError("confidence must be a finite number from 0.0 up to, but not including, 1.0.")
    return normalized


def _strength(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("evidence strength must be a number above 0.0 and below 1.0.")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 < normalized < 1.0:
        raise ValueError("evidence strength must be a finite number above 0.0 and below 1.0.")
    return normalized


def _evidence_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("evidence_count must be an integer.")
    if not 0 <= value <= MAX_EVIDENCE_COUNT:
        raise ValueError(f"evidence_count must be between 0 and {MAX_EVIDENCE_COUNT}.")
    return value


def _timestamp(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _half_life(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("half_life_days must be a number.")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.01 <= normalized <= 3650.0:
        raise ValueError("half_life_days must be a finite number between 0.01 and 3650.0.")
    return normalized


def _decayed(confidence: float, observed_at: datetime, half_life_days: float, as_of: datetime) -> float:
    point = _timestamp(as_of, name="as_of")
    if point < observed_at:
        raise ValueError("as_of must not precede the latest evidence timestamp.")
    elapsed_days = (point - observed_at).total_seconds() / 86_400
    return confidence * (0.5 ** (elapsed_days / half_life_days))


def _reinforced(confidence: float, strength: float) -> float:
    """Combine independent support without allowing certainty to reach 1.0."""
    return 1.0 - (1.0 - confidence) * (1.0 - strength)


@dataclass(frozen=True)
class InterestRecord:
    """A bounded curiosity/interest signal, not an asserted skill or user fact."""

    concept: str
    confidence: float
    evidence_count: int
    last_evidence_at: datetime
    half_life_days: float = DEFAULT_INTEREST_HALF_LIFE_DAYS

    def __post_init__(self) -> None:
        object.__setattr__(self, "concept", _concept(self.concept))
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        object.__setattr__(self, "evidence_count", _evidence_count(self.evidence_count))
        object.__setattr__(self, "last_evidence_at", _timestamp(self.last_evidence_at, name="last_evidence_at"))
        object.__setattr__(self, "half_life_days", _half_life(self.half_life_days))

    @property
    def key(self) -> str:
        return _concept_key(self.concept)

    def confidence_at(self, as_of: datetime) -> float:
        return _decayed(self.confidence, self.last_evidence_at, self.half_life_days, as_of)

    def public_dict(self, *, as_of: datetime | None = None) -> dict[str, object]:
        point = as_of or self.last_evidence_at
        return {
            "concept": self.concept,
            "confidence": self.confidence,
            "effective_confidence": self.confidence_at(point),
            "evidence_count": self.evidence_count,
            "last_evidence_at": self.last_evidence_at.isoformat(),
            "half_life_days": self.half_life_days,
        }


@dataclass(frozen=True)
class SkillRecord:
    """A conservatively verified skill signal; interest alone never creates one."""

    concept: str
    confidence: float
    evidence_count: int
    last_verified_at: datetime
    half_life_days: float = DEFAULT_SKILL_HALF_LIFE_DAYS

    def __post_init__(self) -> None:
        object.__setattr__(self, "concept", _concept(self.concept))
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        object.__setattr__(self, "evidence_count", _evidence_count(self.evidence_count))
        object.__setattr__(self, "last_verified_at", _timestamp(self.last_verified_at, name="last_verified_at"))
        object.__setattr__(self, "half_life_days", _half_life(self.half_life_days))

    @property
    def key(self) -> str:
        return _concept_key(self.concept)

    def confidence_at(self, as_of: datetime) -> float:
        return _decayed(self.confidence, self.last_verified_at, self.half_life_days, as_of)

    def public_dict(self, *, as_of: datetime | None = None) -> dict[str, object]:
        point = as_of or self.last_verified_at
        return {
            "concept": self.concept,
            "confidence": self.confidence,
            "effective_confidence": self.confidence_at(point),
            "evidence_count": self.evidence_count,
            "last_verified_at": self.last_verified_at.isoformat(),
            "half_life_days": self.half_life_days,
        }


@dataclass(frozen=True)
class LearningRecord:
    """One explicit, bounded learning attempt separate from canonical memory.

    A record is evidence of an attempt, not proof of expertise.  Only
    ``apply_verified_learning`` may use a verified-success record to reinforce
    a ``SkillRecord``.
    """

    learning_id: str
    persona_id: str
    source: str
    hypothesis: str
    attempt: str
    outcome: str
    result: str
    verification_evidence: tuple[str, ...]
    completed_at: datetime
    skill_concept: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.learning_id, str) or not _LEARNING_ID_RE.fullmatch(self.learning_id):
            raise ValueError("learning_id must use the form LR-<stable-id>.")
        object.__setattr__(self, "persona_id", _persona_id(self.persona_id))
        source = _bounded_text("source", self.source, limit=40).casefold()
        if source not in LEARNING_SOURCES:
            raise ValueError(f"source must be one of {LEARNING_SOURCES}.")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "hypothesis", _bounded_text("hypothesis", self.hypothesis, limit=800))
        object.__setattr__(self, "attempt", _bounded_text("attempt", self.attempt, limit=1200))
        outcome = _bounded_text("outcome", self.outcome, limit=40).casefold()
        if outcome not in LEARNING_OUTCOMES:
            raise ValueError(f"outcome must be one of {LEARNING_OUTCOMES}.")
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "result", _bounded_text("result", self.result, limit=1200))
        evidence = tuple(_bounded_text("verification evidence", item, limit=800) for item in self.verification_evidence)
        if len(evidence) > 16:
            raise ValueError("verification_evidence is limited to 16 entries.")
        if outcome == "verified_success" and not evidence:
            raise ValueError("verified_success requires verification evidence.")
        object.__setattr__(self, "verification_evidence", evidence)
        object.__setattr__(self, "completed_at", _timestamp(self.completed_at, name="completed_at"))
        if self.skill_concept is not None:
            object.__setattr__(self, "skill_concept", _concept(self.skill_concept))
        if outcome == "verified_success" and self.skill_concept is None:
            raise ValueError("verified_success requires a skill_concept.")

    def public_dict(self) -> dict[str, object]:
        return {
            "learning_id": self.learning_id,
            "persona_id": self.persona_id,
            "source": self.source,
            "hypothesis": self.hypothesis,
            "attempt": self.attempt,
            "outcome": self.outcome,
            "result": self.result,
            "verification_evidence": list(self.verification_evidence),
            "completed_at": self.completed_at.isoformat(),
            "skill_concept": self.skill_concept,
        }


@dataclass(frozen=True)
class ReferenceIntakeRecord:
    """A bounded reference event that may explicitly raise curiosity.

    This record does not fetch content, infer topics, execute a task, or prove
    a skill.  Its supplied topics are merely approved candidates for an
    interest signal via ``record_reference_interest``.
    """

    reference_id: str
    persona_id: str
    source: str
    title: str
    locator: str
    summary: str
    topics: tuple[str, ...]
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.reference_id, str) or not _REFERENCE_ID_RE.fullmatch(self.reference_id):
            raise ValueError("reference_id must use the form RI-<stable-id>.")
        object.__setattr__(self, "persona_id", _persona_id(self.persona_id))
        source = _bounded_text("source", self.source, limit=40).casefold()
        if source not in REFERENCE_SOURCES:
            raise ValueError(f"source must be one of {REFERENCE_SOURCES}.")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "title", _bounded_text("title", self.title, limit=300))
        object.__setattr__(self, "locator", _bounded_text("locator", self.locator, limit=2048))
        object.__setattr__(self, "summary", _bounded_text("summary", self.summary, limit=1600))
        topics = tuple(_concept(topic) for topic in self.topics)
        if not 1 <= len(topics) <= 8:
            raise ValueError("topics must contain between 1 and 8 concepts.")
        if len({_concept_key(topic) for topic in topics}) != len(topics):
            raise ValueError("topics must not contain duplicate concepts.")
        object.__setattr__(self, "topics", topics)
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at, name="observed_at"))

    def public_dict(self) -> dict[str, object]:
        return {
            "reference_id": self.reference_id,
            "persona_id": self.persona_id,
            "source": self.source,
            "title": self.title,
            "locator": self.locator,
            "summary": self.summary,
            "topics": list(self.topics),
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True)
class PersonaDevelopmentState:
    """Immutable persona-local interest and verified-skill state."""

    persona_id: str
    interests: tuple[InterestRecord, ...] = ()
    skills: tuple[SkillRecord, ...] = ()
    learning_records: tuple[LearningRecord, ...] = ()
    reference_records: tuple[ReferenceIntakeRecord, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "persona_id", _persona_id(self.persona_id))
        interests = tuple(self.interests)
        skills = tuple(self.skills)
        learning_records = tuple(self.learning_records)
        reference_records = tuple(self.reference_records)
        if len(interests) > MAX_DEVELOPMENT_RECORDS or len(skills) > MAX_DEVELOPMENT_RECORDS:
            raise ValueError(f"interests and skills are each limited to {MAX_DEVELOPMENT_RECORDS} records.")
        if len(learning_records) > MAX_LEARNING_RECORDS:
            raise ValueError(f"learning_records are limited to {MAX_LEARNING_RECORDS} records.")
        if len(reference_records) > MAX_REFERENCE_RECORDS:
            raise ValueError(f"reference_records are limited to {MAX_REFERENCE_RECORDS} records.")
        if not all(isinstance(record, InterestRecord) for record in interests):
            raise TypeError("interests must contain InterestRecord values.")
        if not all(isinstance(record, SkillRecord) for record in skills):
            raise TypeError("skills must contain SkillRecord values.")
        if not all(isinstance(record, LearningRecord) for record in learning_records):
            raise TypeError("learning_records must contain LearningRecord values.")
        if not all(isinstance(record, ReferenceIntakeRecord) for record in reference_records):
            raise TypeError("reference_records must contain ReferenceIntakeRecord values.")
        if len({record.key for record in interests}) != len(interests):
            raise ValueError("interests must not contain duplicate concepts.")
        if len({record.key for record in skills}) != len(skills):
            raise ValueError("skills must not contain duplicate concepts.")
        if any(record.persona_id != self.persona_id for record in learning_records):
            raise ValueError("learning_records must use the state persona_id.")
        if len({record.learning_id for record in learning_records}) != len(learning_records):
            raise ValueError("learning_records must not contain duplicate learning_id values.")
        if any(record.persona_id != self.persona_id for record in reference_records):
            raise ValueError("reference_records must use the state persona_id.")
        if len({record.reference_id for record in reference_records}) != len(reference_records):
            raise ValueError("reference_records must not contain duplicate reference_id values.")
        object.__setattr__(self, "interests", tuple(sorted(interests, key=lambda record: record.key)))
        object.__setattr__(self, "skills", tuple(sorted(skills, key=lambda record: record.key)))
        object.__setattr__(self, "learning_records", tuple(sorted(
            learning_records, key=lambda record: (record.completed_at, record.learning_id),
        )))
        object.__setattr__(self, "reference_records", tuple(sorted(
            reference_records, key=lambda record: (record.observed_at, record.reference_id),
        )))

    @classmethod
    def empty(cls, persona_id: str) -> "PersonaDevelopmentState":
        return cls(persona_id)

    def record_interest(self, concept: str, *, observed_at: datetime, strength: float = 0.1, half_life_days: float | None = None) -> "PersonaDevelopmentState":
        """Return a new state after bounded interest evidence; no I/O occurs."""
        key = _concept_key(concept)
        observed = _timestamp(observed_at, name="observed_at")
        support = _strength(strength)
        existing = next((record for record in self.interests if record.key == key), None)
        if existing is None:
            record = InterestRecord(
                concept, support, 1, observed,
                DEFAULT_INTEREST_HALF_LIFE_DAYS if half_life_days is None else half_life_days,
            )
            if len(self.interests) >= MAX_DEVELOPMENT_RECORDS:
                raise ValueError("interest capacity reached; explicit retention policy is required.")
            return replace(self, interests=(*self.interests, record))
        base = existing.confidence_at(observed)
        record = InterestRecord(
            existing.concept,
            _reinforced(base, support),
            min(existing.evidence_count + 1, MAX_EVIDENCE_COUNT),
            observed,
            existing.half_life_days if half_life_days is None else half_life_days,
        )
        return replace(self, interests=tuple(record if item.key == key else item for item in self.interests))

    def record_verified_skill(self, concept: str, *, verified_at: datetime, strength: float = 0.1, half_life_days: float | None = None) -> "PersonaDevelopmentState":
        """Return a new state after explicit verification, never from interest alone."""
        key = _concept_key(concept)
        verified = _timestamp(verified_at, name="verified_at")
        support = _strength(strength)
        existing = next((record for record in self.skills if record.key == key), None)
        if existing is None:
            record = SkillRecord(
                concept, support, 1, verified,
                DEFAULT_SKILL_HALF_LIFE_DAYS if half_life_days is None else half_life_days,
            )
            if len(self.skills) >= MAX_DEVELOPMENT_RECORDS:
                raise ValueError("skill capacity reached; explicit retention policy is required.")
            return replace(self, skills=(*self.skills, record))
        base = existing.confidence_at(verified)
        record = SkillRecord(
            existing.concept,
            _reinforced(base, support),
            min(existing.evidence_count + 1, MAX_EVIDENCE_COUNT),
            verified,
            existing.half_life_days if half_life_days is None else half_life_days,
        )
        return replace(self, skills=tuple(record if item.key == key else item for item in self.skills))

    def record_learning(self, record: LearningRecord) -> "PersonaDevelopmentState":
        """Append one explicit learning attempt without changing skill confidence."""
        if not isinstance(record, LearningRecord):
            raise TypeError("record must be a LearningRecord instance.")
        if record.persona_id != self.persona_id:
            raise ValueError("learning record persona_id must match the state persona_id.")
        if any(item.learning_id == record.learning_id for item in self.learning_records):
            raise ValueError("learning record already exists.")
        if len(self.learning_records) >= MAX_LEARNING_RECORDS:
            raise ValueError("learning record capacity reached; explicit retention policy is required.")
        return replace(self, learning_records=(*self.learning_records, record))

    def apply_verified_learning(
        self,
        record: LearningRecord,
        *,
        strength: float = 0.1,
        half_life_days: float | None = None,
    ) -> "PersonaDevelopmentState":
        """Record verified evidence, then conservatively reinforce its skill.

        The caller must explicitly supply a verified-success record.  Failed or
        inconclusive attempts remain inspectable learning records but cannot
        establish or reinforce expertise.
        """
        if not isinstance(record, LearningRecord):
            raise TypeError("record must be a LearningRecord instance.")
        if record.outcome != "verified_success" or record.skill_concept is None:
            raise ValueError("only verified_success learning records can reinforce a skill.")
        updated = self.record_learning(record)
        return updated.record_verified_skill(
            record.skill_concept,
            verified_at=record.completed_at,
            strength=strength,
            half_life_days=half_life_days,
        )

    def record_reference_interest(
        self,
        record: ReferenceIntakeRecord,
        topic: str,
        *,
        strength: float = 0.1,
        half_life_days: float | None = None,
    ) -> "PersonaDevelopmentState":
        """Append a reference event and explicitly raise one declared interest.

        Reference intake can create curiosity only.  It never creates a skill,
        proposes user memory, or causes a model/provider/network call.
        """
        if not isinstance(record, ReferenceIntakeRecord):
            raise TypeError("record must be a ReferenceIntakeRecord instance.")
        if record.persona_id != self.persona_id:
            raise ValueError("reference record persona_id must match the state persona_id.")
        if any(item.reference_id == record.reference_id for item in self.reference_records):
            raise ValueError("reference record already exists.")
        if len(self.reference_records) >= MAX_REFERENCE_RECORDS:
            raise ValueError("reference record capacity reached; explicit retention policy is required.")
        topic_key = _concept_key(topic)
        if topic_key not in {_concept_key(item) for item in record.topics}:
            raise ValueError("topic must be one of the reference record topics.")
        updated = replace(self, reference_records=(*self.reference_records, record))
        return updated.record_interest(
            topic,
            observed_at=record.observed_at,
            strength=strength,
            half_life_days=half_life_days,
        )

    def public_dict(self, *, as_of: datetime | None = None) -> dict[str, object]:
        return {
            "persona_id": self.persona_id,
            "interests": [record.public_dict(as_of=as_of) for record in self.interests],
            "skills": [record.public_dict(as_of=as_of) for record in self.skills],
            "learning_records": [record.public_dict() for record in self.learning_records],
            "reference_records": [record.public_dict() for record in self.reference_records],
        }


class PersonaDevelopmentRegistry:
    """Thread-safe, in-memory namespace registry for future runtime wiring.

    The registry deliberately has no persistence path. Restarting it loses
    development state until a later reviewed storage policy is introduced.
    """

    def __init__(self, states: Iterable[PersonaDevelopmentState] = ()):
        self._lock = RLock()
        self._states: dict[str, PersonaDevelopmentState] = {}
        for state in states:
            self.replace(state)

    def snapshot(self, persona_id: str) -> PersonaDevelopmentState:
        key = _persona_id(persona_id)
        with self._lock:
            return self._states.get(key, PersonaDevelopmentState.empty(key))

    def replace(self, state: PersonaDevelopmentState) -> PersonaDevelopmentState:
        if not isinstance(state, PersonaDevelopmentState):
            raise TypeError("state must be a PersonaDevelopmentState instance.")
        with self._lock:
            self._states[state.persona_id] = state
            return state


__all__ = [
    "DEFAULT_INTEREST_HALF_LIFE_DAYS",
    "DEFAULT_SKILL_HALF_LIFE_DAYS",
    "InterestRecord",
    "LEARNING_OUTCOMES",
    "LEARNING_SOURCES",
    "LearningRecord",
    "MAX_DEVELOPMENT_RECORDS",
    "MAX_LEARNING_RECORDS",
    "MAX_REFERENCE_RECORDS",
    "PersonaDevelopmentRegistry",
    "PersonaDevelopmentState",
    "REFERENCE_SOURCES",
    "ReferenceIntakeRecord",
    "SkillRecord",
]
