"""Explicit, bounded source selection for one completed adventure turn.

Transcript text is presentation history rather than authoritative world state.
This module lets Core deliberately select one completed ``user -> narrator``
pair as *untrusted* provider input without treating ordinary chat, uploaded
text, or provider reasoning as story truth.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_transcript import AdventureTranscriptRecord


class AdventureTurnSourceError(ValueError):
    """Raised when an explicit transcript cannot form one completed turn."""


@dataclass(frozen=True)
class CompletedAdventureTurnSource:
    """One explicit presentation pair, retained only as untrusted input."""

    user_record_id: str
    narrator_record_id: str
    user_text: str
    narrator_text: str

    def __post_init__(self) -> None:
        values = (
            self.user_record_id, self.narrator_record_id,
            self.user_text, self.narrator_text,
        )
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise AdventureTurnSourceError("completed adventure-turn source is invalid")

    @property
    def record_ids(self) -> tuple[str, str]:
        return self.user_record_id, self.narrator_record_id


def select_latest_completed_transcript_turn(
    records: object,
) -> CompletedAdventureTurnSource:
    """Select only a final adjacent explicit ``user -> narrator`` pair.

    Requiring adjacency keeps an earlier player action from being silently
    paired with unrelated later narration. The caller decides whether to use
    this source; selection itself reads no files and changes no state.
    """
    if not isinstance(records, (tuple, list)) or len(records) < 2:
        raise AdventureTurnSourceError("no completed user/narrator transcript turn is available")
    user, narrator = records[-2:]
    if not isinstance(user, AdventureTranscriptRecord) or not isinstance(narrator, AdventureTranscriptRecord):
        raise AdventureTurnSourceError("completed adventure-turn transcript records are invalid")
    if user.role != "user" or narrator.role != "narrator":
        raise AdventureTurnSourceError(
            "latest transcript entries must be an adjacent user entry followed by a narrator entry"
        )
    return CompletedAdventureTurnSource(
        user_record_id=user.record_id,
        narrator_record_id=narrator.record_id,
        user_text=user.text,
        narrator_text=narrator.text,
    )


__all__ = [
    "AdventureTurnSourceError", "CompletedAdventureTurnSource",
    "select_latest_completed_transcript_turn",
]
