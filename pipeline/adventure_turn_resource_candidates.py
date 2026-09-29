"""Strict, separate candidate channel for portable enum resource proposals."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_mutation import AdventureMutation, MUTATION_RESOURCE_CHANGE
from pipeline.adventure_turn_mutation_candidates import (
    AdventureTurnMutationCandidateError,
    parse_untrusted_portable_enum_resource_candidates,
)
from pipeline.adventure_turn_resource_policy import AdventureTurnResourcePolicyView


RESOURCE_TURN_CANDIDATE_SCHEMA_VERSION = 1
MAX_ADVENTURE_TURN_RESOURCE_CANDIDATES = 8


class AdventureTurnResourceCandidateError(ValueError):
    """Raised when a portable resource candidate is not closed and bounded."""


@dataclass(frozen=True)
class AdventureTurnResourceCandidate:
    sequence: int
    candidate_id: str
    mutation: AdventureMutation
    confidence: float

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureTurnResourceCandidateError("resource candidate sequence is invalid")
        if self.candidate_id != f"TR-{self.sequence:03d}":
            raise AdventureTurnResourceCandidateError("resource candidate identifier is invalid")
        if not isinstance(self.mutation, AdventureMutation) or self.mutation.kind != MUTATION_RESOURCE_CHANGE:
            raise AdventureTurnResourceCandidateError("resource candidate mutation is invalid")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise AdventureTurnResourceCandidateError("resource candidate confidence is invalid")
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise AdventureTurnResourceCandidateError("resource candidate confidence must be between 0 and 1")
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True)
class AdventureTurnResourceCandidateBatch:
    candidates: tuple[AdventureTurnResourceCandidate, ...]
    schema_version: int = RESOURCE_TURN_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RESOURCE_TURN_CANDIDATE_SCHEMA_VERSION:
            raise AdventureTurnResourceCandidateError("resource candidate schema is unsupported")
        if not isinstance(self.candidates, tuple) or len(self.candidates) > MAX_ADVENTURE_TURN_RESOURCE_CANDIDATES:
            raise AdventureTurnResourceCandidateError("resource candidate batch size is invalid")
        if not all(isinstance(item, AdventureTurnResourceCandidate) for item in self.candidates):
            raise TypeError("resource candidate batch contains an invalid candidate")
        if [item.sequence for item in self.candidates] != list(range(1, len(self.candidates) + 1)):
            raise AdventureTurnResourceCandidateError("resource candidate sequence is invalid")


def parse_untrusted_adventure_turn_resource_candidates(
    value: object, policy: AdventureTurnResourcePolicyView,
) -> AdventureTurnResourceCandidateBatch:
    """Convert the generic closed envelope into the distinct ``TR`` channel."""
    try:
        generic = parse_untrusted_portable_enum_resource_candidates(value, policy)
    except (AdventureTurnMutationCandidateError, TypeError, ValueError) as error:
        raise AdventureTurnResourceCandidateError("resource candidate payload is invalid") from error
    return AdventureTurnResourceCandidateBatch(tuple(
        AdventureTurnResourceCandidate(
            sequence=item.sequence,
            candidate_id=f"TR-{item.sequence:03d}",
            mutation=item.mutation,
            confidence=item.confidence,
        )
        for item in generic.candidates
    ))


def render_adventure_turn_resource_candidate_batch(
    batch: AdventureTurnResourceCandidateBatch, *, generation_id: str | None = None,
) -> str:
    if not isinstance(batch, AdventureTurnResourceCandidateBatch):
        raise TypeError("resource candidate batch is invalid")
    lines = ["Generated resource-turn candidates (untrusted; not staged):"]
    if generation_id is not None:
        from pipeline.adventure_turn_candidates import normalize_turn_generation_id
        lines.append(f"Generation: {normalize_turn_generation_id(generation_id)}")
    if not batch.candidates:
        lines.append("(none; the provider proposed no eligible public enum resource changes)")
    for candidate in batch.candidates:
        lines.append(f"{candidate.candidate_id} [resource_change] {candidate.mutation.to_dict()}")
        lines.append(f"  Model-declared confidence (advisory): {candidate.confidence:.2f}")
    lines.append("Review output only; Core must explicitly validate and stage any selected candidate before it can be committed.")
    return "\n".join(lines)


__all__ = [
    "AdventureTurnResourceCandidate", "AdventureTurnResourceCandidateBatch", "AdventureTurnResourceCandidateError",
    "MAX_ADVENTURE_TURN_RESOURCE_CANDIDATES", "RESOURCE_TURN_CANDIDATE_SCHEMA_VERSION",
    "parse_untrusted_adventure_turn_resource_candidates", "render_adventure_turn_resource_candidate_batch",
]
