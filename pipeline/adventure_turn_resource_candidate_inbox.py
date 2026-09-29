"""Session-local inbox for a distinct portable resource-candidate channel."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_registry import AdventureRecord
from pipeline.adventure_turn_candidates import normalize_turn_generation_id
from pipeline.adventure_turn_provenance import AdventureTurnGenerationProvenance
from pipeline.adventure_turn_resource_candidates import (
    AdventureTurnResourceCandidate,
    AdventureTurnResourceCandidateBatch,
)


class AdventureTurnResourceCandidateInboxError(ValueError):
    """Raised when a resource-candidate inbox operation is invalid."""


@dataclass(frozen=True)
class AdventureTurnResourceCandidateSelection:
    generation_id: str
    candidate: AdventureTurnResourceCandidate
    provenance: AdventureTurnGenerationProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "generation_id", normalize_turn_generation_id(self.generation_id))
        if not isinstance(self.candidate, AdventureTurnResourceCandidate):
            raise TypeError("selected resource candidate is invalid")
        if not isinstance(self.provenance, AdventureTurnGenerationProvenance):
            raise TypeError("selected resource candidate provenance is invalid")
        if self.provenance.generation_id != self.generation_id or self.provenance.candidate_id != self.candidate.candidate_id:
            raise ValueError("selected resource candidate provenance does not match")


@dataclass(frozen=True)
class AdventureTurnResourceCandidateInbox:
    record: AdventureRecord | None = None
    batch: AdventureTurnResourceCandidateBatch | None = None
    event_count: int = 0
    generation_id: str | None = None
    provenance: AdventureTurnGenerationProvenance | None = None

    def __post_init__(self) -> None:
        if self.record is not None and not isinstance(self.record, AdventureRecord):
            raise TypeError("resource candidate inbox record is invalid")
        if self.batch is not None and not isinstance(self.batch, AdventureTurnResourceCandidateBatch):
            raise TypeError("resource candidate inbox batch is invalid")
        if isinstance(self.event_count, bool) or not isinstance(self.event_count, int) or self.event_count < 0:
            raise ValueError("resource candidate inbox event count is invalid")
        if self.generation_id is not None:
            object.__setattr__(self, "generation_id", normalize_turn_generation_id(self.generation_id))
        if self.provenance is not None and not isinstance(self.provenance, AdventureTurnGenerationProvenance):
            raise TypeError("resource candidate inbox provenance is invalid")
        if (self.record is None) != (self.batch is None):
            raise ValueError("resource candidate inbox record and batch must be present together")
        if self.record is None and (self.event_count or self.generation_id is not None or self.provenance is not None):
            raise ValueError("empty resource candidate inbox cannot retain generation state")
        if self.record is not None and (self.generation_id is None or self.provenance is None):
            raise ValueError("active resource candidate inbox requires generation state")
        if self.provenance is not None and (
            self.provenance.generation_id != self.generation_id
            or self.provenance.origin_event_count != self.event_count
        ):
            raise ValueError("resource candidate inbox provenance does not match its origin")

    @classmethod
    def empty(cls) -> "AdventureTurnResourceCandidateInbox":
        return cls()

    @property
    def active(self) -> bool:
        return self.record is not None

    def present(self, *, record: AdventureRecord, batch: AdventureTurnResourceCandidateBatch,
                event_count: int, provenance: AdventureTurnGenerationProvenance) -> "AdventureTurnResourceCandidateInbox":
        if not isinstance(record, AdventureRecord) or not isinstance(batch, AdventureTurnResourceCandidateBatch):
            raise TypeError("resource candidate inbox input is invalid")
        if not isinstance(provenance, AdventureTurnGenerationProvenance) or provenance.candidate_id is not None:
            raise AdventureTurnResourceCandidateInboxError("resource candidate inbox provenance is invalid")
        return type(self)(record, batch, event_count, provenance.generation_id, provenance)

    def select(self, record: AdventureRecord, candidate_id: object, *, event_count: int) -> AdventureTurnResourceCandidateSelection:
        if not self.active:
            raise AdventureTurnResourceCandidateInboxError("no resource-turn candidates are available")
        if not isinstance(record, AdventureRecord) or record != self.record:
            raise AdventureTurnResourceCandidateInboxError("resource-turn candidates belong to another workspace")
        if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count != self.event_count:
            raise AdventureTurnResourceCandidateInboxError("resource-turn candidates are stale after authoritative story changes")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise AdventureTurnResourceCandidateInboxError("resource-turn candidate identifier is invalid")
        wanted = candidate_id.strip().upper()
        for candidate in self.batch.candidates:
            if candidate.candidate_id == wanted:
                return AdventureTurnResourceCandidateSelection(
                    self.generation_id, candidate, self.provenance.for_candidate(candidate.candidate_id),
                )
        raise AdventureTurnResourceCandidateInboxError("resource-turn candidate was not found")

    def clear(self) -> "AdventureTurnResourceCandidateInbox":
        return type(self).empty()


__all__ = [
    "AdventureTurnResourceCandidateInbox", "AdventureTurnResourceCandidateInboxError",
    "AdventureTurnResourceCandidateSelection",
]
