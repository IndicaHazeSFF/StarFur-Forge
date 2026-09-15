"""Passive public status for the optional sandbox execution subsystem.

The default status is deterministically disabled.  This module does not probe,
install, connect, select, authorize, or execute.  A future status source may
translate already-supplied supervisor readiness evidence, but apartment polling
must never be used to obtain that evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .sandbox_supervisor_readiness import SupervisorTransportReadiness


SANDBOX_EXECUTION_STATUS_SCHEMA_VERSION = 1
SANDBOX_HOST_STATUSES = frozenset({
    "unprobed", "unsupported", "unavailable", "prerequisites_met",
})
SANDBOX_SUPERVISOR_STATUSES = frozenset({
    "unprobed", "unavailable", "ready",
})
SANDBOX_EXECUTION_STATUSES = frozenset({"disabled", "unavailable"})
SANDBOX_EXECUTION_REASONS = frozenset({
    "not_configured",
    "host_unprobed",
    "host_unsupported",
    "host_unavailable",
    "supervisor_unprobed",
    "supervisor_unsupported",
    "supervisor_unavailable",
    "observation_missing",
    "observation_stale",
    "binding_mismatch",
    "enforcement_missing",
    "execution_not_enabled",
    "observation_failed",
})


@dataclass(frozen=True)
class SandboxExecutionStatus:
    """Sanitized status only; never a readiness or authorization token."""

    schema_version: int
    configured: bool
    host_status: str
    supervisor_status: str
    execution_status: str
    reason: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SANDBOX_EXECUTION_STATUS_SCHEMA_VERSION:
            raise ValueError("sandbox execution status schema version is unsupported")
        if not isinstance(self.configured, bool):
            raise TypeError("sandbox execution configured state is invalid")
        if self.host_status not in SANDBOX_HOST_STATUSES:
            raise ValueError("sandbox host status is invalid")
        if self.supervisor_status not in SANDBOX_SUPERVISOR_STATUSES:
            raise ValueError("sandbox supervisor status is invalid")
        if self.execution_status not in SANDBOX_EXECUTION_STATUSES:
            raise ValueError("sandbox execution state is invalid")
        if self.reason not in SANDBOX_EXECUTION_REASONS:
            raise ValueError("sandbox execution reason is invalid")
        if not self.configured and (
            self.host_status != "unprobed"
            or self.supervisor_status != "unprobed"
            or self.execution_status != "disabled"
            or self.reason != "not_configured"
        ):
            raise ValueError("unconfigured sandbox execution status is inconsistent")
        if self.supervisor_status == "ready" and self.reason != "execution_not_enabled":
            raise ValueError("ready supervisor must remain explicitly execution-disabled")

    @classmethod
    def disabled(cls) -> "SandboxExecutionStatus":
        return cls(
            SANDBOX_EXECUTION_STATUS_SCHEMA_VERSION,
            False,
            "unprobed",
            "unprobed",
            "disabled",
            "not_configured",
        )

    @classmethod
    def observation_failed(cls) -> "SandboxExecutionStatus":
        return cls(
            SANDBOX_EXECUTION_STATUS_SCHEMA_VERSION,
            True,
            "unprobed",
            "unavailable",
            "unavailable",
            "observation_failed",
        )

    @classmethod
    def from_transport_readiness(
        cls,
        readiness: SupervisorTransportReadiness,
        *,
        host_status: str,
    ) -> "SandboxExecutionStatus":
        if not isinstance(readiness, SupervisorTransportReadiness):
            raise TypeError("sandbox supervisor readiness is invalid")
        if host_status not in SANDBOX_HOST_STATUSES:
            raise ValueError("sandbox host status is invalid")
        if readiness.ready:
            return cls(
                SANDBOX_EXECUTION_STATUS_SCHEMA_VERSION,
                True,
                host_status,
                "ready",
                "disabled",
                "execution_not_enabled",
            )
        reason = readiness.reason
        if reason not in SANDBOX_EXECUTION_REASONS:
            reason = "supervisor_unavailable"
        supervisor_status = "unprobed" if reason in {
            "host_unprobed", "supervisor_unprobed", "observation_missing",
        } else "unavailable"
        return cls(
            SANDBOX_EXECUTION_STATUS_SCHEMA_VERSION,
            True,
            host_status,
            supervisor_status,
            "unavailable",
            reason,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "configured": self.configured,
            "host_status": self.host_status,
            "supervisor_status": self.supervisor_status,
            "execution_status": self.execution_status,
            "reason": self.reason,
            "storage": "presentation_ephemeral",
        }


class SandboxExecutionStatusProvider(Protocol):
    """Passive source protocol; implementations must never probe from snapshot()."""

    def snapshot(self) -> SandboxExecutionStatus: ...


class DisabledSandboxExecutionStatusProvider:
    """Core default: fixed unavailable data and no side effects."""

    def snapshot(self) -> SandboxExecutionStatus:
        return SandboxExecutionStatus.disabled()


__all__ = [
    "DisabledSandboxExecutionStatusProvider",
    "SANDBOX_EXECUTION_REASONS",
    "SANDBOX_EXECUTION_STATUS_SCHEMA_VERSION",
    "SANDBOX_EXECUTION_STATUSES",
    "SANDBOX_HOST_STATUSES",
    "SANDBOX_SUPERVISOR_STATUSES",
    "SandboxExecutionStatus",
    "SandboxExecutionStatusProvider",
]
