"""Session-local staging for explicit, all-or-nothing adventure event batches."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from pipeline.adventure_events import AdventureEventDraft, normalize_event_request_id
from pipeline.adventure_mutation import AdventureMutation
from pipeline.adventure_resource_state import AdventureResourceOperation
from pipeline.adventure_registry import AdventureRecord
from pipeline.adventure_turn_candidates import (
    AdventureTurnCandidateSelection,
    normalize_turn_generation_id,
)
from pipeline.adventure_turn_mutation_candidate_inbox import AdventureTurnMutationCandidateSelection


MAX_STAGED_ADVENTURE_EVENTS = 16


@dataclass(frozen=True)
class AdventureTurnTransaction:
    record: AdventureRecord | None = None
    origin_event_count: int | None = None
    drafts: tuple[AdventureEventDraft, ...] = ()
    mutations: tuple[AdventureMutation, ...] = ()
    mutation_draft_indices: tuple[int, ...] = ()
    candidate_draft_ids: tuple[tuple[int, str, str], ...] = ()
    request_id: str | None = None

    def __post_init__(self) -> None:
        if self.record is not None and not isinstance(self.record, AdventureRecord):
            raise TypeError("staged adventure record must be an AdventureRecord or None")
        if self.origin_event_count is not None and (
            isinstance(self.origin_event_count, bool)
            or not isinstance(self.origin_event_count, int)
            or self.origin_event_count < 0
        ):
            raise ValueError("staged adventure origin event count is invalid")
        if not isinstance(self.drafts, tuple) or not all(isinstance(draft, AdventureEventDraft) for draft in self.drafts):
            raise TypeError("staged adventure drafts must be AdventureEventDrafts")
        if not isinstance(self.mutations, tuple) or not all(isinstance(mutation, AdventureMutation) for mutation in self.mutations):
            raise TypeError("staged adventure mutations must be AdventureMutations")
        if not isinstance(self.mutation_draft_indices, tuple) or not all(
            isinstance(index, int) and not isinstance(index, bool) for index in self.mutation_draft_indices
        ):
            raise TypeError("staged mutation draft indices must be integers")
        if len(self.mutations) != len(self.mutation_draft_indices):
            raise ValueError("staged mutations must retain draft indices")
        if tuple(sorted(self.mutation_draft_indices)) != self.mutation_draft_indices or len(set(self.mutation_draft_indices)) != len(self.mutation_draft_indices):
            raise ValueError("staged mutation draft indices are invalid")
        if any(index < 0 or index >= len(self.drafts) for index in self.mutation_draft_indices):
            raise ValueError("staged mutation draft index is out of range")
        if not isinstance(self.candidate_draft_ids, tuple):
            raise TypeError("staged candidate draft identifiers must be a tuple")
        candidate_indices = []
        candidate_identities = []
        for value in self.candidate_draft_ids:
            if not isinstance(value, tuple) or len(value) != 3:
                raise TypeError("staged candidate draft identifier is invalid")
            index, generation_id, candidate_id = value
            if isinstance(index, bool) or not isinstance(index, int) or not isinstance(generation_id, str) or not isinstance(candidate_id, str):
                raise TypeError("staged candidate draft identifier is invalid")
            try:
                generation_id = normalize_turn_generation_id(generation_id)
            except ValueError as error:
                raise ValueError("staged candidate draft identifier is invalid") from error
            if not candidate_id.strip():
                raise ValueError("staged candidate draft identifier is invalid")
            candidate_indices.append(index)
            candidate_identities.append((generation_id, candidate_id))
        if tuple(sorted(candidate_indices)) != tuple(candidate_indices) or len(set(candidate_indices)) != len(candidate_indices):
            raise ValueError("staged candidate draft indices are invalid")
        if len(set(candidate_identities)) != len(candidate_identities) or any(index < 0 or index >= len(self.drafts) for index in candidate_indices):
            raise ValueError("staged candidate draft identifier is invalid")
        if self.record is None and (
            self.origin_event_count is not None or self.drafts or self.mutations
            or self.mutation_draft_indices or self.candidate_draft_ids
        ):
            raise ValueError("an inactive adventure turn cannot contain staged changes")
        if self.record is None and self.request_id is not None:
            raise ValueError("an inactive adventure turn cannot contain a request identifier")
        if self.record is not None and self.request_id is None:
            raise ValueError("an active adventure turn requires a request identifier")
        if self.request_id is not None:
            object.__setattr__(self, "request_id", normalize_event_request_id(self.request_id))
        if len(self.drafts) > MAX_STAGED_ADVENTURE_EVENTS:
            raise ValueError("staged adventure event limit exceeded")
        if len(self.mutations) > len(self.drafts):
            raise ValueError("staged mutation count cannot exceed staged event count")

    @classmethod
    def inactive(cls) -> "AdventureTurnTransaction":
        return cls()

    @property
    def active(self) -> bool:
        return self.record is not None

    def begin(self, record: AdventureRecord, *, event_count: int = 0) -> "AdventureTurnTransaction":
        if self.active:
            raise ValueError("an adventure turn is already active")
        return type(self)(
            record=record, origin_event_count=event_count, request_id=f"turn-{uuid4().hex}",
        )

    def stage(self, draft: AdventureEventDraft) -> "AdventureTurnTransaction":
        if not self.active:
            raise ValueError("no adventure turn is active")
        if not isinstance(draft, AdventureEventDraft):
            raise TypeError("staged value must be an AdventureEventDraft")
        return type(self)(
            record=self.record,
            origin_event_count=self.origin_event_count,
            drafts=(*self.drafts, draft),
            mutations=self.mutations,
            mutation_draft_indices=self.mutation_draft_indices,
            candidate_draft_ids=self.candidate_draft_ids,
            request_id=self.request_id,
        )

    def stage_candidate(self, selection: AdventureTurnCandidateSelection) -> "AdventureTurnTransaction":
        """Stage one explicitly selected, already validated ordinary candidate.

        This method deliberately has no candidate-selection policy: a future
        Core-owned review surface must select the candidate before calling it.
        The candidate batch, provider output, and canonical event log stay
        outside this session-local bridge.
        """
        if not isinstance(selection, AdventureTurnCandidateSelection):
            raise TypeError("staged candidate must be an AdventureTurnCandidateSelection")
        if not self.active:
            raise ValueError("no adventure turn is active")
        candidate = selection.candidate
        identity = (selection.generation_id, candidate.candidate_id)
        if identity in {(generation_id, candidate_id) for _, generation_id, candidate_id in self.candidate_draft_ids}:
            return self
        return type(self)(
            record=self.record,
            origin_event_count=self.origin_event_count,
            drafts=(*self.drafts, replace(candidate.draft, generation_provenance=selection.provenance)),
            mutations=self.mutations,
            mutation_draft_indices=self.mutation_draft_indices,
            candidate_draft_ids=(*self.candidate_draft_ids, (len(self.drafts), *identity)),
            request_id=self.request_id,
        )

    def stage_mutation(
        self, mutation: AdventureMutation, *, summary: object, details: object = None,
    ) -> "AdventureTurnTransaction":
        """Stage one typed fact as an ordinary compatible event draft.

        The existing event-log writer remains schema-v1 by policy, so this
        boundary deliberately converts only validated typed data to the legacy
        structured fields.  The original mutation is retained in session
        staging for later schema-v2 transaction integration.
        """
        if not self.active:
            raise ValueError("no adventure turn is active")
        if not isinstance(mutation, AdventureMutation):
            raise TypeError("staged value must be an AdventureMutation")
        if mutation.kind == "state_set":
            draft = AdventureEventDraft(
                "state_change", summary, details=details,
                state_key=mutation.state_key, state_value=mutation.state_value,
            )
        elif mutation.kind == "relationship_set":
            draft = AdventureEventDraft(
                "relationship_change", summary, details=details,
                relationship_subject=mutation.relationship_subject,
                relationship_dimension=mutation.relationship_dimension,
                relationship_value=mutation.relationship_value,
            )
        elif mutation.kind == "knowledge_set":
            draft = AdventureEventDraft(
                "character_knowledge", summary, details=details,
                knowledge_subject=mutation.knowledge_subject,
                knowledge_status=mutation.knowledge_status,
                knowledge_fact=mutation.knowledge_fact,
            )
        else:  # Defensive even though AdventureMutation is closed today.
            raise ValueError("staged mutation kind is unsupported")
        return type(self)(
            record=self.record,
            origin_event_count=self.origin_event_count,
            drafts=(*self.drafts, draft),
            mutations=(*self.mutations, mutation),
            mutation_draft_indices=(*self.mutation_draft_indices, len(self.drafts)),
            candidate_draft_ids=self.candidate_draft_ids,
            request_id=self.request_id,
        )

    def stage_mutation_candidate(
        self,
        selection: AdventureTurnMutationCandidateSelection,
        *,
        resource_operation: AdventureResourceOperation | None = None,
    ) -> "AdventureTurnTransaction":
        """Stage one reviewed typed candidate through explicit Core policy.

        The caller must separately obtain the candidate from its workspace- and
        origin-checked inbox.  Resource candidates require a catalog-validated
        operation supplied by Core; this method deliberately cannot validate a
        resource declaration from provider output alone.
        """
        if not isinstance(selection, AdventureTurnMutationCandidateSelection):
            raise TypeError("staged mutation candidate must be an AdventureTurnMutationCandidateSelection")
        if not self.active:
            raise ValueError("no adventure turn is active")
        candidate = selection.candidate
        identity = (selection.generation_id, candidate.candidate_id)
        if identity in {(generation_id, candidate_id) for _, generation_id, candidate_id in self.candidate_draft_ids}:
            return self
        mutation = candidate.mutation
        if mutation.kind == "resource_change":
            if not isinstance(resource_operation, AdventureResourceOperation):
                raise ValueError("generated resource mutation requires a catalog-validated operation")
            if (
                resource_operation.resource_id != mutation.resource_id
                or resource_operation.operation != mutation.resource_operation
                or resource_operation.value != mutation.resource_value
            ):
                raise ValueError("catalog-validated resource operation does not match generated mutation")
            draft = AdventureEventDraft(
                "resource_change",
                f"Generated resource operation for {mutation.resource_id}.",
                resource_id=resource_operation.resource_id,
                resource_operation=resource_operation.operation,
                resource_value=resource_operation.value,
                generation_provenance=selection.provenance,
            )
            return type(self)(
                record=self.record,
                origin_event_count=self.origin_event_count,
                drafts=(*self.drafts, draft),
                mutations=self.mutations,
                mutation_draft_indices=self.mutation_draft_indices,
                candidate_draft_ids=(*self.candidate_draft_ids, (len(self.drafts), *identity)),
                request_id=self.request_id,
            )
        if resource_operation is not None:
            raise ValueError("only a generated resource mutation accepts a resource operation")
        summary = _mutation_candidate_summary(mutation)
        staged = self.stage_mutation(mutation, summary=summary)
        draft_index = len(self.drafts)
        drafts = (*staged.drafts[:-1], replace(staged.drafts[-1], generation_provenance=selection.provenance))
        return type(self)(
            record=staged.record,
            origin_event_count=staged.origin_event_count,
            drafts=drafts,
            mutations=staged.mutations,
            mutation_draft_indices=staged.mutation_draft_indices,
            candidate_draft_ids=(*staged.candidate_draft_ids, (draft_index, *identity)),
            request_id=staged.request_id,
        )

    def stage_resource(
        self, operation: AdventureResourceOperation, *, summary: object, details: object = None,
    ) -> "AdventureTurnTransaction":
        """Stage one already catalog-validated generic resource operation.

        Resource mutations deliberately stay schema-v1 event drafts in this
        initial slice.  They are not an ``AdventureMutation`` because the
        schema-v2 envelope has no resource representation yet.
        """
        if not self.active:
            raise ValueError("no adventure turn is active")
        if not isinstance(operation, AdventureResourceOperation):
            raise TypeError("staged value must be an AdventureResourceOperation")
        draft = AdventureEventDraft(
            "resource_change", summary, details=details,
            resource_id=operation.resource_id,
            resource_operation=operation.operation,
            resource_value=operation.value,
        )
        return self.stage(draft)

    def remove(self, sequence: object) -> "AdventureTurnTransaction":
        """Discard one 1-based staged draft while retaining mutation provenance."""
        if not self.active:
            raise ValueError("no adventure turn is active")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or not 1 <= sequence <= len(self.drafts):
            raise ValueError("staged adventure event number is invalid")
        index = sequence - 1
        retained_drafts = self.drafts[:index] + self.drafts[index + 1:]
        retained_mutations = []
        retained_indices = []
        for mutation, mutation_index in zip(self.mutations, self.mutation_draft_indices):
            if mutation_index == index:
                continue
            retained_mutations.append(mutation)
            retained_indices.append(mutation_index - 1 if mutation_index > index else mutation_index)
        return type(self)(
            record=self.record,
            origin_event_count=self.origin_event_count,
            drafts=retained_drafts,
            mutations=tuple(retained_mutations),
            mutation_draft_indices=tuple(retained_indices),
            candidate_draft_ids=tuple(
                (candidate_index - 1 if candidate_index > index else candidate_index, generation_id, candidate_id)
                for candidate_index, generation_id, candidate_id in self.candidate_draft_ids
                if candidate_index != index
            ),
            request_id=self.request_id,
        )

    def abort(self) -> "AdventureTurnTransaction":
        return type(self).inactive()


def _mutation_candidate_summary(mutation: AdventureMutation) -> str:
    """Create a deterministic Core label without accepting model narration."""
    if mutation.kind == "state_set":
        return f"Generated state: {mutation.state_key} = {mutation.state_value}."
    if mutation.kind == "relationship_set":
        return (
            "Generated relationship: "
            f"{mutation.relationship_subject} / {mutation.relationship_dimension} = "
            f"{mutation.relationship_value}."
        )
    if mutation.kind == "knowledge_set":
        return (
            "Generated character knowledge: "
            f"{mutation.knowledge_subject} {mutation.knowledge_status}: {mutation.knowledge_fact}."
        )
    raise ValueError("generated mutation kind is unsupported")


__all__ = ["AdventureTurnTransaction", "MAX_STAGED_ADVENTURE_EVENTS"]
