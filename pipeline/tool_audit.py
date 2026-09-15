"""Bounded, session-ephemeral security events for the inert tool broker."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
import time
from typing import Callable


TOOL_LIFECYCLE_STATES = frozenset({
    "proposed", "awaiting_approval", "approved", "queued", "running",
    "completed", "failed", "denied", "cancelled", "timed_out", "outcome_unknown",
})
TOOL_AUDIT_REASONS = frozenset({
    "proposal_validated", "approval_required", "grant_issued", "approval_recorded",
    "dispatch_queued", "dispatch_started", "completed", "permission_denied",
    "authorization_missing", "binding_stale", "executor_unavailable", "executor_failed",
    "result_invalid", "cancelled", "denied_by_controller", "duplicate_request",
    "journal_reconciled_unknown", "journal_write_failed", "authorization_expired",
    "cancel_requested", "supervisor_outcome_unknown", "timed_out",
    "supervisor_unavailable", "supervisor_failed",
    "supervisor_binding_invalid",
    "prerequisite_recorded", "resource_prerequisite_missing",
})
MAX_TOOL_AUDIT_EVENTS = 256


@dataclass(frozen=True)
class ToolAuditEvent:
    sequence: int
    timestamp: float
    invocation_id: str
    tool_id: str
    state: str
    reason: str

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("tool audit sequence is invalid")
        if isinstance(self.timestamp, bool) or not isinstance(self.timestamp, (int, float)):
            raise ValueError("tool audit timestamp is invalid")
        if not isinstance(self.invocation_id, str) or not self.invocation_id.startswith("TI-"):
            raise ValueError("tool audit invocation identifier is invalid")
        if not isinstance(self.tool_id, str) or not self.tool_id:
            raise ValueError("tool audit tool identifier is invalid")
        if self.state not in TOOL_LIFECYCLE_STATES:
            raise ValueError("tool audit lifecycle state is invalid")
        if self.reason not in TOOL_AUDIT_REASONS:
            raise ValueError("tool audit reason is invalid")

    def public_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "timestamp": float(self.timestamp),
            "invocation_id": self.invocation_id,
            "tool_id": self.tool_id,
            "state": self.state,
            "reason": self.reason,
        }


class ToolAuditLog:
    """In-memory bounded journal; it is not durable or tamper-resistant."""

    def __init__(
        self, *, maximum_events: int = MAX_TOOL_AUDIT_EVENTS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if (
            isinstance(maximum_events, bool)
            or not isinstance(maximum_events, int)
            or not 1 <= maximum_events <= 4096
        ):
            raise ValueError("tool audit event limit is invalid")
        if not callable(clock):
            raise TypeError("tool audit clock is invalid")
        self._maximum_events = maximum_events
        self._clock = clock
        self._events: list[ToolAuditEvent] = []
        self._next_sequence = 1
        self._lock = RLock()

    def append(self, invocation_id: str, tool_id: str, state: str, reason: str) -> ToolAuditEvent:
        with self._lock:
            event = ToolAuditEvent(
                self._next_sequence, self._clock(), invocation_id, tool_id, state, reason,
            )
            self._next_sequence += 1
            self._events.append(event)
            if len(self._events) > self._maximum_events:
                self._events = self._events[-self._maximum_events:]
            return event

    def events(self, *, invocation_id: str | None = None) -> tuple[ToolAuditEvent, ...]:
        with self._lock:
            if invocation_id is None:
                return tuple(self._events)
            if not isinstance(invocation_id, str):
                raise TypeError("tool audit invocation identifier is invalid")
            return tuple(item for item in self._events if item.invocation_id == invocation_id)

    def public_dict(self, *, maximum_events: int = 64) -> dict[str, object]:
        if (
            isinstance(maximum_events, bool)
            or not isinstance(maximum_events, int)
            or not 0 <= maximum_events <= 64
        ):
            raise ValueError("public tool audit limit is invalid")
        selected = self.events()[-maximum_events:] if maximum_events else ()
        return {
            "schema_version": 1,
            "storage": "session_ephemeral",
            "events": [item.public_dict() for item in selected],
        }


__all__ = [
    "TOOL_AUDIT_REASONS", "TOOL_LIFECYCLE_STATES", "ToolAuditEvent", "ToolAuditLog",
]
