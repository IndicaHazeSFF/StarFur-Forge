"""Session-local inbox for reviewed typed adventure-turn mutation candidates.

This is intentionally parallel to, rather than combined with, the ordinary
event candidate inbox.  Selecting a ``TM-###`` candidate returns a validated
pure mutation plus bounded provenance; it does not validate a resource catalog,
stage a draft, mutate derived state, or append an event.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_registry import AdventureRecord
from pipeline.adventure_turn_candidates import normalize_turn_generation_id
from pipeline.adventure_turn_mutation_candidates import (
    AdventureTurnMutationCandidate,
    AdventureTurnMutationCandidateBatch,
)
from pipeline.adventure_turn_provenance import AdventureTurnGenerationProvenance


class AdventureTurnMutationCandidateInboxError(ValueError):
    """Raised when a typed candidate inbox operation is invalid."""


@dataclass(frozen=True)
class AdventureTurnMutationCandidateSelection:
    """One explicitly selected typed proposal, still without write authority."""

    generation_id: str
    candidate: AdventureTurnMutationCandidate
    provenance: AdventureTurnGenerationProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "generation_id", normalize_turn_generation_id(self.generation_id))
        if not isinstance(self.candidate, AdventureTurnMutationCandidate):
            raise TypeError("selected mutation candidate must be an AdventureTurnMutationCandidate")
        if not isinstance(self.provenance, AdventureTurnGenerationProvenance):
            raise TypeError("selected mutation candidate provenance is invalid")
        if self.provenance.generation_id != self.generation_id:
            raise ValueError("selected mutation candidate provenance does not match its generation")
        if self.provenance.candidate_id != self.candidate.candidate_id:
            raise ValueError("selected mutation candidate provenance does not match its candidate")


@dataclass(frozen=True)
class AdventureTurnMutationCandidateInbox:
    """One workspace-bound, session-local batch of typed mutation proposals."""

    record: AdventureRecord | None = None
    batch: AdventureTurnMutationCandidateBatch | None = None
    event_count: int = 0
    generation_id: str | None = None
    provenance: AdventureTurnGenerationProvenance | None = None

    def __post_init__(self) -> None:
        if self.record is not None and not isinstance(self.record, AdventureRecord):
            raise TypeError("mutation candidate inbox record must be an AdventureRecord or None")
        if self.batch is not None and not isinstance(self.batch, AdventureTurnMutationCandidateBatch):
            raise TypeError("mutation candidate inbox batch must be an AdventureTurnMutationCandidateBatch or None")
        if isinstance(self.event_count, bool) or not isinstance(self.event_count, int) or self.event_count < 0:
            raise ValueError("mutation candidate inbox event count is invalid")
        if self.generation_id is not None:
            object.__setattr__(self, "generation_id", normalize_turn_generation_id(self.generation_id))
        if self.provenance is not None and not isinstance(self.provenance, AdventureTurnGenerationProvenance):
            raise TypeError("mutation candidate inbox provenance is invalid")
        if (self.record is None) != (self.batch is None):
            raise ValueError("mutation candidate inbox record and batch must be present together")
        if self.record is None and (self.event_count or self.generation_id is not None or self.provenance is not None):
            raise ValueError("an empty mutation candidate inbox cannot retain generation state")
        if self.record is not None and (self.generation_id is None or self.provenance is None):
            raise ValueError("an active mutation candidate inbox requires a generation identifier")
        if self.provenance is not None and self.provenance.generation_id != self.generation_id:
            raise ValueError("mutation candidate inbox provenance does not match its generation")
        if self.provenance is not None and self.provenance.origin_event_count != self.event_count:
            raise ValueError("mutation candidate inbox provenance does not match its origin")

    @classmethod
    def empty(cls) -> "AdventureTurnMutationCandidateInbox":
        return cls()

    @property
    def active(self) -> bool:
        return self.record is not None

    def present(
        self,
        *,
        record: AdventureRecord,
        batch: AdventureTurnMutationCandidateBatch,
        event_count: int,
        provenance: AdventureTurnGenerationProvenance,
    ) -> "AdventureTurnMutationCandidateInbox":
        """Replace this session's noncanonical typed candidates for one workspace."""
        if not isinstance(record, AdventureRecord):
            raise TypeError("mutation candidate inbox record is invalid")
        if not isinstance(batch, AdventureTurnMutationCandidateBatch):
            raise TypeError("mutation candidate inbox batch is invalid")
        if not isinstance(provenance, AdventureTurnGenerationProvenance):
            raise TypeError("mutation candidate inbox provenance is invalid")
        if provenance.candidate_id is not None:
            raise AdventureTurnMutationCandidateInboxError(
                "mutation candidate inbox provenance must name no candidate before selection"
            )
        return type(self)(record, batch, event_count, provenance.generation_id, provenance)

    def select(
        self, record: AdventureRecord, candidate_id: object, *, event_count: int,
    ) -> AdventureTurnMutationCandidateSelection:
        """Return one requested typed candidate without changing inbox state."""
        if not self.active:
            raise AdventureTurnMutationCandidateInboxError("no typed adventure-turn candidates are available")
        if not isinstance(record, AdventureRecord) or record != self.record:
            raise AdventureTurnMutationCandidateInboxError("typed adventure-turn candidates belong to another workspace")
        if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count < 0:
            raise AdventureTurnMutationCandidateInboxError("typed adventure-turn candidate event count is invalid")
        if event_count != self.event_count:
            raise AdventureTurnMutationCandidateInboxError(
                "typed adventure-turn candidates are stale after authoritative story changes"
            )
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise AdventureTurnMutationCandidateInboxError("typed adventure-turn candidate identifier is invalid")
        normalized = candidate_id.strip().upper()
        for candidate in self.batch.candidates:
            if candidate.candidate_id == normalized:
                return AdventureTurnMutationCandidateSelection(
                    self.generation_id, candidate, self.provenance.for_candidate(candidate.candidate_id),
                )
        raise AdventureTurnMutationCandidateInboxError("typed adventure-turn candidate was not found")

    def clear(self) -> "AdventureTurnMutationCandidateInbox":
        return type(self).empty()


__all__ = [
    "AdventureTurnMutationCandidateInbox", "AdventureTurnMutationCandidateInboxError",
    "AdventureTurnMutationCandidateSelection",
]
