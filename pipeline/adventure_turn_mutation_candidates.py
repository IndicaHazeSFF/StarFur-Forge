"""Validation boundary for untrusted typed adventure-turn mutation proposals.

This deliberately remains separate from ordinary generated event candidates.
It decodes only a compact structured envelope into pure ``AdventureMutation``
values; it neither selects a narrative event type nor stages or persists a
mutation.  A later Core-owned policy slice must decide whether a reviewed
candidate is appropriate for the currently mounted adventure and, for
resources, validate it against that adventure's declared catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pipeline.adventure_mutation import AdventureMutation, AdventureMutationError


TURN_MUTATION_CANDIDATE_SCHEMA_VERSION = 1
MAX_ADVENTURE_TURN_MUTATION_CANDIDATES = 16


class AdventureTurnMutationCandidateError(ValueError):
    """Raised when untrusted typed mutation candidate data is invalid."""


_MUTATION_FIELDS_BY_KIND = {
    "state_set": frozenset({"kind", "key", "value"}),
    "relationship_set": frozenset({"kind", "subject", "dimension", "value"}),
    "knowledge_set": frozenset({"kind", "subject", "status", "fact"}),
    "resource_change": frozenset({"kind", "id", "operation", "value"}),
}


def _strict_mutation(value: object) -> AdventureMutation:
    """Validate a closed mutation object before the general value object sees it."""
    if not isinstance(value, Mapping) or not isinstance(value.get("kind"), str):
        raise AdventureTurnMutationCandidateError("mutation candidate payload is invalid")
    fields = _MUTATION_FIELDS_BY_KIND.get(value["kind"])
    if fields is None or set(value) != fields:
        raise AdventureTurnMutationCandidateError("mutation candidate payload fields are invalid")
    try:
        return AdventureMutation.from_dict(dict(value))
    except (TypeError, AdventureMutationError) as error:
        raise AdventureTurnMutationCandidateError("mutation candidate payload is invalid") from error


@dataclass(frozen=True)
class AdventureTurnMutationCandidate:
    """One bounded, untrusted typed mutation proposal with no write authority."""

    sequence: int
    candidate_id: str
    mutation: AdventureMutation
    confidence: float

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureTurnMutationCandidateError("mutation candidate sequence is invalid")
        if self.candidate_id != f"TM-{self.sequence:03d}":
            raise AdventureTurnMutationCandidateError("mutation candidate identifier is invalid")
        if not isinstance(self.mutation, AdventureMutation):
            raise TypeError("mutation candidate mutation must be an AdventureMutation")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise AdventureTurnMutationCandidateError("mutation candidate confidence is invalid")
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise AdventureTurnMutationCandidateError(
                "mutation candidate confidence must be between 0 and 1"
            )
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True)
class AdventureTurnMutationCandidateBatch:
    """A bounded provider-untrusted batch of typed mutation proposals."""

    candidates: tuple[AdventureTurnMutationCandidate, ...]
    schema_version: int = TURN_MUTATION_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TURN_MUTATION_CANDIDATE_SCHEMA_VERSION:
            raise AdventureTurnMutationCandidateError("mutation candidate schema is unsupported")
        if (
            not isinstance(self.candidates, tuple)
            or len(self.candidates) > MAX_ADVENTURE_TURN_MUTATION_CANDIDATES
        ):
            raise AdventureTurnMutationCandidateError("mutation candidate batch size is invalid")
        if not all(isinstance(candidate, AdventureTurnMutationCandidate) for candidate in self.candidates):
            raise TypeError("mutation candidate batch contains an invalid candidate")
        if [candidate.sequence for candidate in self.candidates] != list(range(1, len(self.candidates) + 1)):
            raise AdventureTurnMutationCandidateError("mutation candidate sequence is invalid")


def parse_untrusted_adventure_turn_mutation_candidates(
    value: object,
) -> AdventureTurnMutationCandidateBatch:
    """Validate decoded provider output without granting it Core authority.

    The canonical form wraps the closed payload in ``mutation``. A deliberately
    narrow flat compatibility form is also supported for small local models:
    it must contain exactly one closed mutation object plus ``confidence``.
    Neither form accepts ordinary narrative fields, hidden reasoning, or prose.
    """
    if not isinstance(value, Mapping) or set(value) != {"schema_version", "candidates"}:
        raise AdventureTurnMutationCandidateError("mutation candidate envelope fields are invalid")
    if (
        value["schema_version"] != TURN_MUTATION_CANDIDATE_SCHEMA_VERSION
        or not isinstance(value["candidates"], list)
    ):
        raise AdventureTurnMutationCandidateError("mutation candidate envelope is invalid")
    candidates = []
    for sequence, raw in enumerate(value["candidates"], 1):
        if not isinstance(raw, Mapping):
            raise AdventureTurnMutationCandidateError("mutation candidate fields are invalid")
        if "mutation" in raw and set(raw) != {"mutation", "confidence"}:
            raise AdventureTurnMutationCandidateError("mutation candidate fields are invalid")
        if set(raw) == {"mutation", "confidence"}:
            payload = raw["mutation"]
        elif "confidence" in raw:
            payload = {key: item for key, item in raw.items() if key != "confidence"}
        else:
            raise AdventureTurnMutationCandidateError("mutation candidate fields are invalid")
        try:
            mutation = _strict_mutation(payload)
        except AdventureTurnMutationCandidateError:
            raise
        candidates.append(AdventureTurnMutationCandidate(
            sequence=sequence,
            candidate_id=f"TM-{sequence:03d}",
            mutation=mutation,
            confidence=raw["confidence"],
        ))
    return AdventureTurnMutationCandidateBatch(tuple(candidates))


def render_adventure_turn_mutation_candidate_batch(
    batch: AdventureTurnMutationCandidateBatch, *, generation_id: str | None = None,
    hidden_resource_ids: frozenset[str] = frozenset(),
) -> str:
    """Render only validated typed proposal fields for explicit Core review."""
    if not isinstance(batch, AdventureTurnMutationCandidateBatch):
        raise TypeError("mutation candidate batch is invalid")
    if not isinstance(hidden_resource_ids, frozenset) or not all(
        isinstance(resource_id, str) for resource_id in hidden_resource_ids
    ):
        raise TypeError("hidden resource identifiers must be a frozen set of text")
    lines = ["Generated typed adventure-turn candidates (untrusted; not staged):"]
    if generation_id is not None:
        from pipeline.adventure_turn_candidates import normalize_turn_generation_id
        lines.append(f"Generation: {normalize_turn_generation_id(generation_id)}")
    if not batch.candidates:
        lines.append("(none; the provider proposed no durable typed changes)")
    for candidate in batch.candidates:
        mutation = candidate.mutation
        if mutation.kind == "resource_change" and mutation.resource_id in hidden_resource_ids:
            lines.append(f"{candidate.candidate_id} [resource_change] Hidden resource change")
        else:
            lines.append(f"{candidate.candidate_id} [{mutation.kind}] {mutation.to_dict()}")
        lines.append(f"  Model-declared confidence (advisory): {candidate.confidence:.2f}")
    lines.append(
        "Review output only; Core must explicitly validate and stage any selected "
        "candidate before it can be committed."
    )
    return "\n".join(lines)


__all__ = [
    "AdventureTurnMutationCandidate", "AdventureTurnMutationCandidateBatch",
    "AdventureTurnMutationCandidateError", "MAX_ADVENTURE_TURN_MUTATION_CANDIDATES",
    "TURN_MUTATION_CANDIDATE_SCHEMA_VERSION",
    "parse_untrusted_adventure_turn_mutation_candidates", "render_adventure_turn_mutation_candidate_batch",
]
