"""Validation boundary for untrusted future generated adventure-turn proposals.

This module is deliberately not a model parser, command handler, or event
writer.  A provider adapter may later hand it a decoded object, after which
Core can decide whether to display, stage, reject, or request confirmation for
the resulting bounded ordinary-event candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pipeline.adventure_events import AdventureEventDraft, DRAFT_EVENT_TYPES


TURN_CANDIDATE_SCHEMA_VERSION = 1
MAX_ADVENTURE_TURN_CANDIDATES = 16
_ORDINARY_CANDIDATE_EVENT_TYPES = DRAFT_EVENT_TYPES - {
    "state_change", "relationship_change", "character_knowledge", "resource_change",
}


class AdventureTurnCandidateError(ValueError):
    """Raised when an untrusted generated-turn candidate envelope is invalid."""


@dataclass(frozen=True)
class AdventureTurnCandidate:
    """One bounded ordinary story-event proposal with no write authority."""

    sequence: int
    candidate_id: str
    draft: AdventureEventDraft
    confidence: float

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureTurnCandidateError("turn candidate sequence is invalid")
        if self.candidate_id != f"TC-{self.sequence:03d}":
            raise AdventureTurnCandidateError("turn candidate identifier is invalid")
        if not isinstance(self.draft, AdventureEventDraft):
            raise TypeError("turn candidate draft must be an AdventureEventDraft")
        if self.draft.event_type not in _ORDINARY_CANDIDATE_EVENT_TYPES:
            raise AdventureTurnCandidateError("turn candidate event type requires a dedicated typed policy")
        if any((
            self.draft.state_key is not None,
            self.draft.relationship_subject is not None,
            self.draft.knowledge_subject is not None,
            self.draft.resource_id is not None,
        )):
            raise AdventureTurnCandidateError("turn candidate cannot carry a structured mutation")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise AdventureTurnCandidateError("turn candidate confidence is invalid")
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise AdventureTurnCandidateError("turn candidate confidence must be between 0 and 1")
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True)
class AdventureTurnCandidateBatch:
    """A bounded, provider-untrusted set of ordinary event proposals."""

    candidates: tuple[AdventureTurnCandidate, ...]
    schema_version: int = TURN_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TURN_CANDIDATE_SCHEMA_VERSION:
            raise AdventureTurnCandidateError("turn candidate schema is unsupported")
        if not isinstance(self.candidates, tuple) or not self.candidates or len(self.candidates) > MAX_ADVENTURE_TURN_CANDIDATES:
            raise AdventureTurnCandidateError("turn candidate batch size is invalid")
        if not all(isinstance(candidate, AdventureTurnCandidate) for candidate in self.candidates):
            raise TypeError("turn candidate batch contains an invalid candidate")
        if [candidate.sequence for candidate in self.candidates] != list(range(1, len(self.candidates) + 1)):
            raise AdventureTurnCandidateError("turn candidate sequence is invalid")


def parse_untrusted_adventure_turn_candidates(value: object) -> AdventureTurnCandidateBatch:
    """Validate decoded provider output without granting it Core authority.

    The restricted ordinary-event-only form is intentional.  State,
    relationship, knowledge, and resource proposals need their own typed
    policy/validation path before any future staging integration.
    """
    if not isinstance(value, Mapping) or set(value) != {"schema_version", "candidates"}:
        raise AdventureTurnCandidateError("turn candidate envelope fields are invalid")
    if value["schema_version"] != TURN_CANDIDATE_SCHEMA_VERSION or not isinstance(value["candidates"], list):
        raise AdventureTurnCandidateError("turn candidate envelope is invalid")
    candidates = []
    for sequence, raw in enumerate(value["candidates"], 1):
        if not isinstance(raw, Mapping) or set(raw) - {"event_type", "summary", "details", "confidence"}:
            raise AdventureTurnCandidateError("turn candidate fields are invalid")
        required = {"event_type", "summary", "confidence"}
        if not required.issubset(raw):
            raise AdventureTurnCandidateError("turn candidate fields are incomplete")
        try:
            draft = AdventureEventDraft(
                event_type=raw["event_type"], summary=raw["summary"], details=raw.get("details"),
            )
        except (TypeError, ValueError) as error:
            raise AdventureTurnCandidateError("turn candidate draft is invalid") from error
        candidates.append(AdventureTurnCandidate(
            sequence=sequence, candidate_id=f"TC-{sequence:03d}", draft=draft,
            confidence=raw["confidence"],
        ))
    return AdventureTurnCandidateBatch(tuple(candidates))


__all__ = [
    "AdventureTurnCandidate", "AdventureTurnCandidateBatch", "AdventureTurnCandidateError",
    "MAX_ADVENTURE_TURN_CANDIDATES", "TURN_CANDIDATE_SCHEMA_VERSION",
    "parse_untrusted_adventure_turn_candidates",
]
