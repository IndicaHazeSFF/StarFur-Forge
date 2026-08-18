"""Session-local staging for explicit, all-or-nothing adventure event batches."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_events import AdventureEventDraft
from pipeline.adventure_registry import AdventureRecord


MAX_STAGED_ADVENTURE_EVENTS = 16


@dataclass(frozen=True)
class AdventureTurnTransaction:
    record: AdventureRecord | None = None
    drafts: tuple[AdventureEventDraft, ...] = ()

    def __post_init__(self) -> None:
        if self.record is not None and not isinstance(self.record, AdventureRecord):
            raise TypeError("staged adventure record must be an AdventureRecord or None")
        if not isinstance(self.drafts, tuple) or not all(isinstance(draft, AdventureEventDraft) for draft in self.drafts):
            raise TypeError("staged adventure drafts must be AdventureEventDrafts")
        if self.record is None and self.drafts:
            raise ValueError("an inactive adventure turn cannot contain drafts")
        if len(self.drafts) > MAX_STAGED_ADVENTURE_EVENTS:
            raise ValueError("staged adventure event limit exceeded")

    @classmethod
    def inactive(cls) -> "AdventureTurnTransaction":
        return cls()

    @property
    def active(self) -> bool:
        return self.record is not None

    def begin(self, record: AdventureRecord) -> "AdventureTurnTransaction":
        if self.active:
            raise ValueError("an adventure turn is already active")
        return type(self)(record=record)

    def stage(self, draft: AdventureEventDraft) -> "AdventureTurnTransaction":
        if not self.active:
            raise ValueError("no adventure turn is active")
        if not isinstance(draft, AdventureEventDraft):
            raise TypeError("staged value must be an AdventureEventDraft")
        return type(self)(record=self.record, drafts=(*self.drafts, draft))

    def abort(self) -> "AdventureTurnTransaction":
        return type(self).inactive()


__all__ = ["AdventureTurnTransaction", "MAX_STAGED_ADVENTURE_EVENTS"]
