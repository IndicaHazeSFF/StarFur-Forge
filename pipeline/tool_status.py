"""Privacy-bounded aggregate status for one session-local tool broker.

This module classifies already-validated lifecycle labels.  It does not inspect
tool proposals, grants, approvals, audit events, results, or executor details,
and it provides no control or authority surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .tool_audit import TOOL_LIFECYCLE_STATES


TOOL_STATUS_SCHEMA_VERSION = 1
MAX_PUBLIC_TOOL_REQUESTS = 128
_PENDING_REVIEW_STATES = frozenset({"proposed", "awaiting_approval"})
_TERMINAL_STATES = frozenset({
    "completed", "failed", "denied", "cancelled", "timed_out", "outcome_unknown",
})


@dataclass(frozen=True)
class ToolStatusSummary:
    """Counts only; individual request identity and contents stay private."""

    schema_version: int
    total_count: int
    pending_review_count: int
    approved_count: int
    queued_count: int
    running_count: int
    terminal_count: int

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != TOOL_STATUS_SCHEMA_VERSION:
            raise ValueError("tool status schema version is unsupported")
        values = (
            self.total_count,
            self.pending_review_count,
            self.approved_count,
            self.queued_count,
            self.running_count,
            self.terminal_count,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise TypeError("tool status counts must be integers")
        if any(not 0 <= value <= MAX_PUBLIC_TOOL_REQUESTS for value in values):
            raise ValueError("tool status count is out of bounds")
        if sum(values[1:]) != self.total_count:
            raise ValueError("tool status category counts are inconsistent")

    @classmethod
    def empty(cls) -> "ToolStatusSummary":
        return cls(TOOL_STATUS_SCHEMA_VERSION, 0, 0, 0, 0, 0, 0)

    @classmethod
    def from_states(cls, states: Iterable[str]) -> "ToolStatusSummary":
        normalized = tuple(states)
        if len(normalized) > MAX_PUBLIC_TOOL_REQUESTS:
            raise ValueError("tool status request count exceeds the public bound")
        if any(state not in TOOL_LIFECYCLE_STATES for state in normalized):
            raise ValueError("tool status contains an invalid lifecycle state")
        return cls(
            TOOL_STATUS_SCHEMA_VERSION,
            len(normalized),
            sum(state in _PENDING_REVIEW_STATES for state in normalized),
            normalized.count("approved"),
            normalized.count("queued"),
            normalized.count("running"),
            sum(state in _TERMINAL_STATES for state in normalized),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "total_count": self.total_count,
            "pending_review_count": self.pending_review_count,
            "approved_count": self.approved_count,
            "queued_count": self.queued_count,
            "running_count": self.running_count,
            "terminal_count": self.terminal_count,
            "storage": "session_ephemeral",
        }


__all__ = [
    "MAX_PUBLIC_TOOL_REQUESTS",
    "TOOL_STATUS_SCHEMA_VERSION",
    "ToolStatusSummary",
]
