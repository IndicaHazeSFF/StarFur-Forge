"""Provider-free lifecycle contracts for a future isolated tool supervisor.

These values bind one already-authorized Core invocation to one worker
generation and provide a cooperative cancellation seam.  They do not start a
process, select a backend, grant authority, or prove OS isolation.  Real
platform adapters remain disabled until the later backend conformance gates.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
import re
import secrets
from threading import Event
from typing import Protocol

from .tool_contracts import ToolProposal, ToolResult
from .tool_grants import (
    IDENTITY_RE, INVOCATION_ID_RE, ToolInvocation, tool_invocation_fingerprint,
)
from .tool_registry import TOOL_ID_RE


SUPERVISOR_SCHEMA_VERSION = 1
WORKER_GENERATION_RE = re.compile(r"^TW-[A-Za-z0-9_-]{1,64}$")
SUPERVISOR_COMPLETION_OUTCOMES = frozenset({
    "completed", "failed", "cancelled", "timed_out", "outcome_unknown",
})
SUPERVISOR_STOP_STATES = frozenset({"verified_stopped", "not_verified"})
SUPERVISOR_CANCEL_STATES = frozenset({"requested", "verified_stopped", "unknown"})
SUPERVISOR_RUN_STATES = frozenset({
    "starting", "running", "cancel_requested", "verified_stopped", "unknown",
})


def _strict_version(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 999:
        raise ValueError(f"{label} is invalid")
    return value


def _timestamp(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 <= float(value) < 10**12
    ):
        raise ValueError(f"{label} is invalid")
    return float(value)


def new_worker_generation() -> str:
    """Return an opaque Core-created generation; it conveys no authority."""
    return f"TW-{secrets.token_hex(16)}"


@dataclass(frozen=True)
class SupervisorLaunchRequest:
    """Exact, payload-free binding for one authorized launch attempt."""

    schema_version: int
    invocation_id: str
    tool_id: str
    tool_version: int
    binding_fingerprint: str
    policy_revision: str
    worker_generation: str
    issued_at: float
    authorization_deadline: float

    def __post_init__(self) -> None:
        _strict_version(self.schema_version, "supervisor schema version")
        if self.schema_version != SUPERVISOR_SCHEMA_VERSION:
            raise ValueError("supervisor schema version is unsupported")
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ValueError("supervisor invocation identifier is invalid")
        if not isinstance(self.tool_id, str) or not TOOL_ID_RE.fullmatch(self.tool_id):
            raise ValueError("supervisor tool identifier is invalid")
        _strict_version(self.tool_version, "supervisor tool version")
        if (
            not isinstance(self.binding_fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.binding_fingerprint)
        ):
            raise ValueError("supervisor binding fingerprint is invalid")
        if not isinstance(self.policy_revision, str) or not IDENTITY_RE.fullmatch(self.policy_revision):
            raise ValueError("supervisor policy revision is invalid")
        if not isinstance(self.worker_generation, str) or not WORKER_GENERATION_RE.fullmatch(
            self.worker_generation
        ):
            raise ValueError("supervisor worker generation is invalid")
        issued = _timestamp(self.issued_at, "supervisor issue time")
        deadline = _timestamp(self.authorization_deadline, "supervisor authorization deadline")
        if issued >= deadline:
            raise ValueError("supervisor authorization deadline is invalid")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "authorization_deadline", deadline)

    @classmethod
    def from_invocation(
        cls, invocation: ToolInvocation, *, worker_generation: str,
        issued_at: float, authorization_deadline: float,
    ) -> "SupervisorLaunchRequest":
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("supervisor invocation is invalid")
        if authorization_deadline > invocation.expires_at:
            raise ValueError("supervisor authorization deadline exceeds invocation expiry")
        return cls(
            SUPERVISOR_SCHEMA_VERSION,
            invocation.invocation_id,
            invocation.tool_id,
            invocation.tool_version,
            tool_invocation_fingerprint(invocation),
            invocation.policy_revision,
            worker_generation,
            issued_at,
            authorization_deadline,
        )

    def matches_invocation(self, invocation: ToolInvocation) -> bool:
        return isinstance(invocation, ToolInvocation) and (
            self.invocation_id == invocation.invocation_id
            and self.tool_id == invocation.tool_id
            and self.tool_version == invocation.tool_version
            and self.binding_fingerprint == tool_invocation_fingerprint(invocation)
            and self.policy_revision == invocation.policy_revision
        )


class SupervisorCancellation:
    """Process-local cooperative signal; it is not a verified stop result."""

    __slots__ = ("_event", "_process_id")

    def __init__(self) -> None:
        self._event = Event()
        self._process_id = os.getpid()

    @property
    def requested(self) -> bool:
        return self._process_id == os.getpid() and self._event.is_set()

    def request(self) -> None:
        if self._process_id != os.getpid():
            raise RuntimeError("supervisor cancellation belongs to another process")
        self._event.set()


@dataclass(frozen=True)
class SupervisorCancelReceipt:
    """Bounded acknowledgement; only verified_stopped proves termination."""

    schema_version: int
    invocation_id: str
    worker_generation: str
    state: str

    def __post_init__(self) -> None:
        _strict_version(self.schema_version, "supervisor cancel schema version")
        if self.schema_version != SUPERVISOR_SCHEMA_VERSION:
            raise ValueError("supervisor cancel schema version is unsupported")
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ValueError("supervisor cancel invocation identifier is invalid")
        if not isinstance(self.worker_generation, str) or not WORKER_GENERATION_RE.fullmatch(
            self.worker_generation
        ):
            raise ValueError("supervisor cancel worker generation is invalid")
        if self.state not in SUPERVISOR_CANCEL_STATES:
            raise ValueError("supervisor cancel state is invalid")

    def matches(self, request: SupervisorLaunchRequest) -> bool:
        return isinstance(request, SupervisorLaunchRequest) and (
            self.invocation_id == request.invocation_id
            and self.worker_generation == request.worker_generation
        )


@dataclass(frozen=True)
class SupervisorRunStatus:
    """Payload-free query result for one exact worker generation."""

    schema_version: int
    invocation_id: str
    binding_fingerprint: str
    worker_generation: str
    state: str

    def __post_init__(self) -> None:
        _strict_version(self.schema_version, "supervisor status schema version")
        if self.schema_version != SUPERVISOR_SCHEMA_VERSION:
            raise ValueError("supervisor status schema version is unsupported")
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ValueError("supervisor status invocation identifier is invalid")
        if (
            not isinstance(self.binding_fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.binding_fingerprint)
        ):
            raise ValueError("supervisor status binding fingerprint is invalid")
        if not isinstance(self.worker_generation, str) or not WORKER_GENERATION_RE.fullmatch(
            self.worker_generation
        ):
            raise ValueError("supervisor status worker generation is invalid")
        if self.state not in SUPERVISOR_RUN_STATES:
            raise ValueError("supervisor run state is invalid")

    @classmethod
    def from_request(
        cls, request: SupervisorLaunchRequest, *, state: str,
    ) -> "SupervisorRunStatus":
        if not isinstance(request, SupervisorLaunchRequest):
            raise TypeError("supervisor launch request is invalid")
        return cls(
            SUPERVISOR_SCHEMA_VERSION, request.invocation_id,
            request.binding_fingerprint, request.worker_generation, state,
        )

    def matches(self, request: SupervisorLaunchRequest) -> bool:
        return isinstance(request, SupervisorLaunchRequest) and (
            self.invocation_id == request.invocation_id
            and self.binding_fingerprint == request.binding_fingerprint
            and self.worker_generation == request.worker_generation
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "invocation_id": self.invocation_id,
            "worker_generation": self.worker_generation,
            "state": self.state,
        }


@dataclass(frozen=True)
class SupervisorCompletion:
    """Strict final lifecycle envelope returned by a trusted supervisor adapter."""

    schema_version: int
    invocation_id: str
    tool_id: str
    tool_version: int
    binding_fingerprint: str
    policy_revision: str
    worker_generation: str
    outcome: str
    stop_state: str
    result: ToolResult | None = None

    def __post_init__(self) -> None:
        _strict_version(self.schema_version, "supervisor completion schema version")
        if self.schema_version != SUPERVISOR_SCHEMA_VERSION:
            raise ValueError("supervisor completion schema version is unsupported")
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ValueError("supervisor completion invocation identifier is invalid")
        if not isinstance(self.tool_id, str) or not TOOL_ID_RE.fullmatch(self.tool_id):
            raise ValueError("supervisor completion tool identifier is invalid")
        _strict_version(self.tool_version, "supervisor completion tool version")
        if (
            not isinstance(self.binding_fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.binding_fingerprint)
        ):
            raise ValueError("supervisor completion binding fingerprint is invalid")
        if not isinstance(self.policy_revision, str) or not IDENTITY_RE.fullmatch(self.policy_revision):
            raise ValueError("supervisor completion policy revision is invalid")
        if not isinstance(self.worker_generation, str) or not WORKER_GENERATION_RE.fullmatch(
            self.worker_generation
        ):
            raise ValueError("supervisor completion worker generation is invalid")
        if self.outcome not in SUPERVISOR_COMPLETION_OUTCOMES:
            raise ValueError("supervisor completion outcome is invalid")
        if self.stop_state not in SUPERVISOR_STOP_STATES:
            raise ValueError("supervisor completion stop state is invalid")
        if self.outcome in {"completed", "failed", "cancelled", "timed_out"} and (
            self.stop_state != "verified_stopped"
        ):
            raise ValueError("supervisor terminal outcome requires verified stop")
        if self.result is not None and not isinstance(self.result, ToolResult):
            raise TypeError("supervisor completion result is invalid")
        if self.result is not None and (
            self.result.invocation_id != self.invocation_id
            or self.result.tool_id != self.tool_id
            or self.result.tool_version != self.tool_version
        ):
            raise ValueError("supervisor result binding does not match completion")
        if self.outcome == "outcome_unknown" and self.result is not None:
            raise ValueError("unknown supervisor outcome cannot include a result")
        if self.outcome == "completed" and (
            self.result is None or self.result.outcome != "completed"
        ):
            raise ValueError("completed supervisor outcome requires completed result")
        if self.result is not None and self.result.outcome != self.outcome:
            raise ValueError("supervisor result outcome does not match completion")

    @classmethod
    def from_request(
        cls, request: SupervisorLaunchRequest, *, outcome: str,
        stop_state: str, result: ToolResult | None = None,
    ) -> "SupervisorCompletion":
        if not isinstance(request, SupervisorLaunchRequest):
            raise TypeError("supervisor launch request is invalid")
        return cls(
            SUPERVISOR_SCHEMA_VERSION,
            request.invocation_id,
            request.tool_id,
            request.tool_version,
            request.binding_fingerprint,
            request.policy_revision,
            request.worker_generation,
            outcome,
            stop_state,
            result,
        )

    def matches(self, request: SupervisorLaunchRequest) -> bool:
        return isinstance(request, SupervisorLaunchRequest) and (
            self.invocation_id == request.invocation_id
            and self.tool_id == request.tool_id
            and self.tool_version == request.tool_version
            and self.binding_fingerprint == request.binding_fingerprint
            and self.policy_revision == request.policy_revision
            and self.worker_generation == request.worker_generation
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "invocation_id": self.invocation_id,
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "worker_generation": self.worker_generation,
            "outcome": self.outcome,
            "stop_state": self.stop_state,
            "result": None if self.result is None else {
                "outcome": self.result.outcome,
                "error_category": self.result.error_category,
                "artifact_count": len(self.result.artifact_refs),
            },
        }


class ToolExecutionSupervisor(Protocol):
    """Trusted adapter seam; implementations must independently enforce policy."""

    @property
    def available(self) -> bool: ...

    def run(
        self, request: SupervisorLaunchRequest, invocation: ToolInvocation,
        proposal: ToolProposal, cancellation: SupervisorCancellation,
    ) -> SupervisorCompletion: ...

    def request_cancel(
        self, request: SupervisorLaunchRequest,
        cancellation: SupervisorCancellation,
    ) -> SupervisorCancelReceipt: ...

    def query(self, request: SupervisorLaunchRequest) -> SupervisorRunStatus: ...


class DisabledToolSupervisor:
    """Default supervisor exposes no execution capability."""

    available = False

    def run(self, request, invocation, proposal, cancellation):
        raise RuntimeError("tool execution supervisor is disabled")

    def request_cancel(self, request, cancellation):
        raise RuntimeError("tool execution supervisor is disabled")

    def query(self, request):
        raise RuntimeError("tool execution supervisor is disabled")


__all__ = [
    "DisabledToolSupervisor", "SUPERVISOR_SCHEMA_VERSION", "SupervisorCancellation",
    "SupervisorCancelReceipt", "SupervisorCompletion", "SupervisorLaunchRequest",
    "SupervisorRunStatus", "ToolExecutionSupervisor", "new_worker_generation",
]
