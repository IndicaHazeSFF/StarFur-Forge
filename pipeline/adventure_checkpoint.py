"""Validated immutable references to authoritative adventure-log prefixes.

Checkpoints are not snapshots and do not own a branch, transcript, or derived
state.  They simply name one verified prefix of the append-only event log so a
later restore/fork subsystem has an explicit stable source boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


CHECKPOINT_SCHEMA_VERSION = 1
CHECKPOINT_FILENAME = "checkpoints.json"
_ID_PATTERN = re.compile(r"^CP-[0-9]{6}$")
_MAX_LABEL_LENGTH = 96
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AdventureCheckpointError(ValueError):
    """Raised when a checkpoint is malformed or cannot name one safe prefix."""


def normalize_checkpoint_label(value: object) -> str:
    if not isinstance(value, str):
        raise AdventureCheckpointError("checkpoint label must be text")
    label = " ".join(value.split())
    if not label:
        raise AdventureCheckpointError("checkpoint label cannot be empty")
    if len(label) > _MAX_LABEL_LENGTH:
        raise AdventureCheckpointError(f"checkpoint label must be at most {_MAX_LABEL_LENGTH} characters")
    return label


@dataclass(frozen=True)
class AdventureCheckpoint:
    """One named immutable reference to a verified event-log prefix."""

    checkpoint_id: str
    label: str
    event_count: int
    last_event_id: str | None
    event_fingerprint: str
    created_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.checkpoint_id, str) or not _ID_PATTERN.fullmatch(self.checkpoint_id):
            raise AdventureCheckpointError("checkpoint identifier is invalid")
        object.__setattr__(self, "label", normalize_checkpoint_label(self.label))
        if not isinstance(self.event_count, int) or self.event_count < 0:
            raise AdventureCheckpointError("checkpoint event count is invalid")
        expected_last = None if self.event_count == 0 else f"AE-{self.event_count:06d}"
        if self.last_event_id != expected_last:
            raise AdventureCheckpointError("checkpoint last event identifier is invalid")
        if not isinstance(self.event_fingerprint, str) or not _FINGERPRINT_PATTERN.fullmatch(self.event_fingerprint):
            raise AdventureCheckpointError("checkpoint event fingerprint is invalid")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise AdventureCheckpointError("checkpoint creation time is required")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.checkpoint_id,
            "label": self.label,
            "event_count": self.event_count,
            "last_event_id": self.last_event_id,
            "event_fingerprint": self.event_fingerprint,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureCheckpoint":
        if not isinstance(value, dict):
            raise AdventureCheckpointError("checkpoint must be an object")
        try:
            return cls(
                checkpoint_id=value["id"], label=value["label"], event_count=value["event_count"],
                last_event_id=value.get("last_event_id"), event_fingerprint=value["event_fingerprint"],
                created_at=value["created_at"],
            )
        except KeyError as error:
            raise AdventureCheckpointError("checkpoint is incomplete") from error


__all__ = [
    "AdventureCheckpoint", "AdventureCheckpointError", "CHECKPOINT_FILENAME", "CHECKPOINT_SCHEMA_VERSION",
    "normalize_checkpoint_label",
]
