"""Validation boundary for untrusted future generated adventure-turn proposals.

This module is deliberately not a model parser, command handler, or event
writer.  A provider adapter may later hand it a decoded object, after which
Core can decide whether to display, stage, reject, or request confirmation for
the resulting bounded ordinary-event candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from pipeline.adventure_events import AdventureEventDraft
from pipeline.adventure_turn_policy import ORDINARY_ADVENTURE_EVENT_TYPES
from pipeline.adventure_turn_provenance import AdventureTurnGenerationProvenance


TURN_CANDIDATE_SCHEMA_VERSION = 1
MAX_ADVENTURE_TURN_CANDIDATES = 16
# Compatibility name retained for callers and fixtures. The policy itself lives
# in one shared module so prompt/parser changes cannot silently diverge.
ORDINARY_GENERATED_EVENT_TYPES = ORDINARY_ADVENTURE_EVENT_TYPES
TURN_GENERATION_ID_PATTERN = re.compile(r"^TG-[0-9a-f]{32}$")


def normalize_turn_generation_id(value: object) -> str:
    """Validate a Core-generated opaque candidate-batch identity."""
    if not isinstance(value, str) or not TURN_GENERATION_ID_PATTERN.fullmatch(value):
        raise ValueError("turn generation identifier is invalid")
    return value


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
        if self.draft.event_type not in ORDINARY_GENERATED_EVENT_TYPES:
            raise AdventureTurnCandidateError(
                "turn candidate event type is not permitted for generated candidates"
            )
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
class AdventureTurnCandidateSelection:
    """One exact candidate selected from a trusted, session-local generation."""

    generation_id: str
    candidate: AdventureTurnCandidate
    provenance: AdventureTurnGenerationProvenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "generation_id", normalize_turn_generation_id(self.generation_id))
        if not isinstance(self.candidate, AdventureTurnCandidate):
            raise TypeError("selected turn candidate must be an AdventureTurnCandidate")
        if self.provenance is not None:
            if not isinstance(self.provenance, AdventureTurnGenerationProvenance):
                raise TypeError("selected turn candidate provenance is invalid")
            if self.provenance.generation_id != self.generation_id:
                raise ValueError("selected turn candidate provenance does not match its generation")


@dataclass(frozen=True)
class AdventureTurnCandidateBatch:
    """A bounded, provider-untrusted set of ordinary event proposals."""

    candidates: tuple[AdventureTurnCandidate, ...]
    schema_version: int = TURN_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TURN_CANDIDATE_SCHEMA_VERSION:
            raise AdventureTurnCandidateError("turn candidate schema is unsupported")
        if not isinstance(self.candidates, tuple) or len(self.candidates) > MAX_ADVENTURE_TURN_CANDIDATES:
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


def render_adventure_turn_candidate_batch(
    batch: AdventureTurnCandidateBatch, *, generation_id: str | None = None,
) -> str:
    """Render bounded candidate data for a future Core-owned review surface.

    This intentionally displays only Core-validated ordinary draft fields.  It
    does not turn a candidate into a staged draft, canonical event, or model
    instruction.
    """
    if not isinstance(batch, AdventureTurnCandidateBatch):
        raise TypeError("turn candidate batch is invalid")
    lines = [
        "Generated adventure-turn candidates (untrusted; not staged):",
    ]
    if generation_id is not None:
        lines.append(f"Generation: {normalize_turn_generation_id(generation_id)}")
    if not batch.candidates:
        lines.append("(none; the provider proposed no durable ordinary event)")
    else:
        for candidate in batch.candidates:
            lines.append(
                f"{candidate.candidate_id} [{candidate.draft.event_type}] "
                f"{candidate.draft.summary}"
            )
            if candidate.draft.details:
                lines.append(f"  Details: {candidate.draft.details}")
            lines.append(f"  Candidate confidence: {candidate.confidence:.2f}")
    lines.append(
        "Review output only; Core must explicitly validate and stage any "
        "selected candidate before it can be committed."
    )
    return "\n".join(lines)


__all__ = [
    "AdventureTurnCandidate", "AdventureTurnCandidateBatch", "AdventureTurnCandidateError",
    "AdventureTurnCandidateSelection",
    "MAX_ADVENTURE_TURN_CANDIDATES", "ORDINARY_GENERATED_EVENT_TYPES",
    "TURN_CANDIDATE_SCHEMA_VERSION", "normalize_turn_generation_id",
    "parse_untrusted_adventure_turn_candidates", "render_adventure_turn_candidate_batch",
]
