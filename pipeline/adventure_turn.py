"""Session-local staging for explicit, all-or-nothing adventure event batches."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from pipeline.adventure_events import AdventureEventDraft, normalize_event_request_id
from pipeline.adventure_mutation import AdventureMutation
from pipeline.adventure_registry import AdventureRecord


MAX_STAGED_ADVENTURE_EVENTS = 16


@dataclass(frozen=True)
class AdventureTurnTransaction:
    record: AdventureRecord | None = None
    drafts: tuple[AdventureEventDraft, ...] = ()
    mutations: tuple[AdventureMutation, ...] = ()
    request_id: str | None = None

    def __post_init__(self) -> None:
        if self.record is not None and not isinstance(self.record, AdventureRecord):
            raise TypeError("staged adventure record must be an AdventureRecord or None")
        if not isinstance(self.drafts, tuple) or not all(isinstance(draft, AdventureEventDraft) for draft in self.drafts):
            raise TypeError("staged adventure drafts must be AdventureEventDrafts")
        if not isinstance(self.mutations, tuple) or not all(isinstance(mutation, AdventureMutation) for mutation in self.mutations):
            raise TypeError("staged adventure mutations must be AdventureMutations")
        if self.record is None and (self.drafts or self.mutations):
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

    def begin(self, record: AdventureRecord) -> "AdventureTurnTransaction":
        if self.active:
            raise ValueError("an adventure turn is already active")
        return type(self)(record=record, request_id=f"turn-{uuid4().hex}")

    def stage(self, draft: AdventureEventDraft) -> "AdventureTurnTransaction":
        if not self.active:
            raise ValueError("no adventure turn is active")
        if not isinstance(draft, AdventureEventDraft):
            raise TypeError("staged value must be an AdventureEventDraft")
        return type(self)(
            record=self.record,
            drafts=(*self.drafts, draft),
            mutations=self.mutations,
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
            drafts=(*self.drafts, draft),
            mutations=(*self.mutations, mutation),
            request_id=self.request_id,
        )

    def abort(self) -> "AdventureTurnTransaction":
        return type(self).inactive()


__all__ = ["AdventureTurnTransaction", "MAX_STAGED_ADVENTURE_EVENTS"]
