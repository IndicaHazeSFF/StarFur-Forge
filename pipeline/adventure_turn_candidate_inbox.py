"""Session-local holder for one validated future generated-turn candidate batch.

The inbox deliberately separates provider output from adventure staging.  A
caller may present a batch for the currently mounted workspace and later look
up one candidate by its deterministic identifier, but selecting it does not
stage or persist anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_registry import AdventureRecord
from pipeline.adventure_turn_candidates import (
    AdventureTurnCandidateBatch,
    AdventureTurnCandidateSelection,
    normalize_turn_generation_id,
)
from pipeline.adventure_turn_generation import AdventureTurnGenerationResult
from pipeline.adventure_turn_provenance import AdventureTurnGenerationProvenance


class AdventureTurnCandidateInboxError(ValueError):
    """Raised when a session-local candidate inbox operation is invalid."""


@dataclass(frozen=True)
class AdventureTurnCandidateInbox:
    """One workspace-bound, session-local validated candidate batch."""

    record: AdventureRecord | None = None
    batch: AdventureTurnCandidateBatch | None = None
    event_count: int = 0
    generation_id: str | None = None
    provenance: AdventureTurnGenerationProvenance | None = None

    def __post_init__(self) -> None:
        if self.record is not None and not isinstance(self.record, AdventureRecord):
            raise TypeError("candidate inbox record must be an AdventureRecord or None")
        if self.batch is not None and not isinstance(self.batch, AdventureTurnCandidateBatch):
            raise TypeError("candidate inbox batch must be an AdventureTurnCandidateBatch or None")
        if isinstance(self.event_count, bool) or not isinstance(self.event_count, int) or self.event_count < 0:
            raise ValueError("candidate inbox event count is invalid")
        if self.generation_id is not None:
            object.__setattr__(self, "generation_id", normalize_turn_generation_id(self.generation_id))
        if self.provenance is not None and not isinstance(self.provenance, AdventureTurnGenerationProvenance):
            raise TypeError("candidate inbox provenance is invalid")
        if (self.record is None) != (self.batch is None):
            raise ValueError("candidate inbox record and batch must be present together")
        if self.record is None and (self.event_count or self.generation_id is not None or self.provenance is not None):
            raise ValueError("an empty candidate inbox cannot retain generation state")
        if self.record is not None and (self.generation_id is None or self.provenance is None):
            raise ValueError("an active candidate inbox requires a generation identifier")
        if self.provenance is not None and self.provenance.generation_id != self.generation_id:
            raise ValueError("candidate inbox provenance does not match its generation")
        if self.provenance is not None and self.provenance.origin_event_count != self.event_count:
            raise ValueError("candidate inbox provenance does not match its origin")

    @classmethod
    def empty(cls) -> "AdventureTurnCandidateInbox":
        return cls()

    @property
    def active(self) -> bool:
        return self.record is not None

    def present(self, result: AdventureTurnGenerationResult) -> "AdventureTurnCandidateInbox":
        """Replace this session's noncanonical candidates for one workspace."""
        if not isinstance(result, AdventureTurnGenerationResult):
            raise TypeError("candidate inbox result must be an AdventureTurnGenerationResult")
        # A valid no-change result is informative in diagnostics, but it is not
        # a selectable review batch.  Clearing here also guarantees a retry
        # cannot leave an earlier candidate available for accidental staging.
        if not result.batch.candidates:
            return type(self).empty()
        return type(self)(
            record=result.request.record,
            batch=result.batch,
            event_count=result.request.event_count,
            generation_id=result.generation_id,
            provenance=result.request.provenance,
        )

    def select(
        self, record: AdventureRecord, candidate_id: object, *, event_count: int,
    ) -> AdventureTurnCandidateSelection:
        """Return one explicitly requested candidate without changing inbox state."""
        if not self.active:
            raise AdventureTurnCandidateInboxError("no adventure-turn candidates are available")
        if not isinstance(record, AdventureRecord) or record != self.record:
            raise AdventureTurnCandidateInboxError("adventure-turn candidates belong to another workspace")
        if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count < 0:
            raise AdventureTurnCandidateInboxError("adventure-turn candidate event count is invalid")
        if event_count != self.event_count:
            raise AdventureTurnCandidateInboxError(
                "adventure-turn candidates are stale after authoritative story changes"
            )
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise AdventureTurnCandidateInboxError("adventure-turn candidate identifier is invalid")
        normalized = candidate_id.strip().upper()
        for candidate in self.batch.candidates:
            if candidate.candidate_id == normalized:
                return AdventureTurnCandidateSelection(
                    self.generation_id, candidate, self.provenance.for_candidate(candidate.candidate_id),
                )
        raise AdventureTurnCandidateInboxError("adventure-turn candidate was not found")

    def clear(self) -> "AdventureTurnCandidateInbox":
        return type(self).empty()


__all__ = [
    "AdventureTurnCandidateInbox", "AdventureTurnCandidateInboxError",
]
