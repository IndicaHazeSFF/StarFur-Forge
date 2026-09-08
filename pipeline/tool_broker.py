"""Provider-free tool broker with a disabled-by-default executor boundary.

This S3 broker joins validation, exact grants, and one-use approvals without
exposing commands or providers.  The Core factory uses ``DisabledToolExecutor``
and therefore cannot execute ``sandbox.run``.  Injected executors are test-only
until a later reviewed isolation backend is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
from typing import Protocol

from .tool_approval import ToolApprovalController, ToolApprovalError
from .tool_audit import TOOL_AUDIT_REASONS, TOOL_LIFECYCLE_STATES, ToolAuditLog
from .tool_contracts import ToolContractRegistry, ToolProposal, ToolResult
from .tool_grants import (
    SessionToolGrantController, ToolGrantError, ToolInvocation, ToolInvocationIssuer,
)
from .tool_permissions import evaluate_tool_permission


MAX_TOOL_BROKER_REQUESTS = 128
TERMINAL_TOOL_STATES = frozenset({
    "completed", "failed", "denied", "cancelled", "timed_out", "outcome_unknown",
})


class ToolBrokerError(ValueError):
    """Raised for an invalid or conflicting Core broker operation."""


@dataclass(frozen=True)
class ToolDispatchContext:
    """Trusted current context used only to detect stale authority bindings."""

    principal_id: str
    session_instance_id: str
    persona_id: str
    adventure_id: str | None
    policy_revision: str

    def matches(self, invocation: ToolInvocation) -> bool:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("tool dispatch invocation is invalid")
        return (
            self.principal_id,
            self.session_instance_id,
            self.persona_id,
            self.adventure_id,
            self.policy_revision,
        ) == (
            invocation.principal_id,
            invocation.session_instance_id,
            invocation.persona_id,
            invocation.adventure_id,
            invocation.policy_revision,
        )


class ToolExecutor(Protocol):
    @property
    def available(self) -> bool: ...

    def execute(self, invocation: ToolInvocation, proposal: ToolProposal) -> ToolResult: ...


class DisabledToolExecutor:
    """Default executor advertises no capability and must never be called."""

    available = False

    def execute(self, invocation: ToolInvocation, proposal: ToolProposal) -> ToolResult:
        raise RuntimeError("tool execution is disabled")


@dataclass(frozen=True)
class ToolBrokerRecord:
    invocation: ToolInvocation
    proposal: ToolProposal
    state: str
    reason: str
    grant_id: str | None = None
    approval_id: str | None = None
    result: ToolResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.invocation, ToolInvocation) or not isinstance(self.proposal, ToolProposal):
            raise TypeError("tool broker record binding is invalid")
        if self.state not in TOOL_LIFECYCLE_STATES:
            raise ValueError("tool broker record state is invalid")
        if self.reason not in TOOL_AUDIT_REASONS:
            raise ValueError("tool broker record reason is invalid")

    def public_dict(self) -> dict[str, object]:
        result = None
        if self.result is not None:
            result = {
                "outcome": self.result.outcome,
                "error_category": self.result.error_category,
                "artifact_count": len(self.result.artifact_refs),
            }
        return {
            "invocation_id": self.invocation.invocation_id,
            "tool_id": self.invocation.tool_id,
            "tool_version": self.invocation.tool_version,
            "state": self.state,
            "reason": self.reason,
            "has_grant": self.grant_id is not None,
            "has_approval": self.approval_id is not None,
            "result": result,
            "storage": "session_ephemeral",
        }


class ToolBroker:
    def __init__(
        self, contracts: ToolContractRegistry, issuer: ToolInvocationIssuer,
        grants: SessionToolGrantController, approvals: ToolApprovalController,
        *, executor: ToolExecutor | None = None, audit: ToolAuditLog | None = None,
        maximum_requests: int = MAX_TOOL_BROKER_REQUESTS,
    ) -> None:
        if not isinstance(contracts, ToolContractRegistry):
            raise TypeError("tool broker contract registry is invalid")
        if not isinstance(issuer, ToolInvocationIssuer):
            raise TypeError("tool broker invocation issuer is invalid")
        if not isinstance(grants, SessionToolGrantController):
            raise TypeError("tool broker grant controller is invalid")
        if not isinstance(approvals, ToolApprovalController):
            raise TypeError("tool broker approval controller is invalid")
        if isinstance(maximum_requests, bool) or not isinstance(maximum_requests, int) or not 1 <= maximum_requests <= 1024:
            raise ValueError("tool broker request limit is invalid")
        selected_executor = executor or DisabledToolExecutor()
        if not hasattr(selected_executor, "available") or not callable(getattr(selected_executor, "execute", None)):
            raise TypeError("tool broker executor is invalid")
        self._contracts = contracts
        self._issuer = issuer
        self._grants = grants
        self._approvals = approvals
        self._executor = selected_executor
        self._audit = audit or ToolAuditLog()
        self._maximum_requests = maximum_requests
        self._records: dict[str, ToolBrokerRecord] = {}
        self._lock = RLock()

    @property
    def audit(self) -> ToolAuditLog:
        return self._audit

    def submit(
        self, proposal: ToolProposal, *, request_id: str, trusted_principal_id: str,
        session_instance_id: str, persona_id: str, adventure_id: str | None,
        policy_revision: str, resource_refs: tuple[str, ...] = (), lifetime_seconds: float = 300,
    ) -> ToolBrokerRecord:
        validated = self._contracts.validate_proposal(proposal)
        invocation = self._issuer.issue(
            validated,
            trusted_principal_id=trusted_principal_id,
            session_instance_id=session_instance_id,
            persona_id=persona_id,
            adventure_id=adventure_id,
            policy_revision=policy_revision,
            resource_refs=resource_refs,
            lifetime_seconds=lifetime_seconds,
            invocation_id=request_id,
        )
        with self._lock:
            existing = self._records.get(request_id)
            if existing is not None:
                if existing.invocation.binding_tuple() != invocation.binding_tuple():
                    raise ToolBrokerError("tool request identifier was reused with conflicting content")
                self._audit.append(request_id, invocation.tool_id, existing.state, "duplicate_request")
                return existing
            if len(self._records) >= self._maximum_requests:
                raise ToolBrokerError("tool broker request limit exceeded")
            record = ToolBrokerRecord(invocation, validated, "awaiting_approval", "approval_required")
            self._records[request_id] = record
            self._audit.append(request_id, invocation.tool_id, "proposed", "proposal_validated")
            self._audit.append(request_id, invocation.tool_id, "awaiting_approval", "approval_required")
            return record

    def get(self, request_id: object) -> ToolBrokerRecord | None:
        if not isinstance(request_id, str):
            return None
        with self._lock:
            return self._records.get(request_id)

    def records(self) -> tuple[ToolBrokerRecord, ...]:
        """Return immutable records in insertion order for trusted local control."""
        with self._lock:
            return tuple(self._records.values())

    def invalidate_context(self, context: ToolDispatchContext) -> int:
        """Fail closed any nonterminal request whose trusted context changed."""
        if not isinstance(context, ToolDispatchContext):
            raise TypeError("tool dispatch context is invalid")
        changed = 0
        with self._lock:
            for request_id, record in tuple(self._records.items()):
                if record.state not in TERMINAL_TOOL_STATES and not context.matches(record.invocation):
                    self._replace_terminal(record, "denied", "binding_stale")
                    changed += 1
        return changed

    def grant(self, request_id: str, *, lifetime_seconds: float = 300) -> ToolBrokerRecord:
        with self._lock:
            record = self._require_active(request_id)
            if record.grant_id is not None:
                raise ToolBrokerError("tool request already has a grant")
            grant = self._grants.issue(record.invocation, lifetime_seconds=lifetime_seconds, maximum_uses=1)
            updated = replace(record, grant_id=grant.grant_id, reason="grant_issued")
            self._records[request_id] = updated
            self._audit.append(request_id, record.invocation.tool_id, updated.state, "grant_issued")
            return updated

    def approve(self, request_id: str, *, lifetime_seconds: float = 120) -> ToolBrokerRecord:
        with self._lock:
            record = self._require_active(request_id)
            if record.approval_id is not None:
                raise ToolBrokerError("tool request is already approved")
            grant = self._grants.get(record.grant_id)
            if grant is None:
                raise ToolBrokerError("tool request has no grant")
            approval = self._approvals.approve(
                record.invocation, grant, lifetime_seconds=lifetime_seconds,
            )
            updated = replace(
                record, state="approved", reason="approval_recorded", approval_id=approval.approval_id,
            )
            self._records[request_id] = updated
            self._audit.append(request_id, record.invocation.tool_id, "approved", "approval_recorded")
            return updated

    def deny(self, request_id: str) -> ToolBrokerRecord:
        return self._terminate(request_id, state="denied", reason="denied_by_controller")

    def cancel(self, request_id: str) -> ToolBrokerRecord:
        return self._terminate(request_id, state="cancelled", reason="cancelled")

    def dispatch(self, request_id: str, *, context: ToolDispatchContext) -> ToolBrokerRecord:
        """Authorize, queue, and attempt one execution through the injected adapter."""
        with self._lock:
            queued = self.queue(request_id, context=context)
            if queued.state != "queued":
                return queued
            return self.run_queued(request_id, context=context)

    def queue(self, request_id: str, *, context: ToolDispatchContext) -> ToolBrokerRecord:
        """Atomically consume exact authority and leave a cancellable queued request."""
        if not isinstance(context, ToolDispatchContext):
            raise TypeError("tool dispatch context is invalid")
        with self._lock:
            record = self._require_record(request_id)
            if record.state in TERMINAL_TOOL_STATES:
                return record
            if not context.matches(record.invocation):
                return self._replace_terminal(record, "denied", "binding_stale")
            if record.state != "approved" or record.grant_id is None or record.approval_id is None:
                return self._replace_terminal(record, "denied", "authorization_missing")
            grant = self._grants.get(record.grant_id)
            if grant is None:
                return self._replace_terminal(record, "denied", "authorization_missing")
            try:
                evidence = self._approvals.claim(record.approval_id, record.invocation, grant)
                permission = self._grants.claim(record.grant_id, record.invocation)
            except (ToolApprovalError, ToolGrantError):
                return self._replace_terminal(record, "denied", "permission_denied")
            descriptor = self._contracts.get(
                record.invocation.tool_id, record.invocation.tool_version,
            ).descriptor
            decision = evaluate_tool_permission(
                descriptor, (permission,), confirmed=evidence.invocation_id == record.invocation.invocation_id,
            )
            if not decision.allowed:
                return self._replace_terminal(record, "denied", "permission_denied")
            queued = replace(record, state="queued", reason="dispatch_queued")
            self._records[request_id] = queued
            self._audit.append(request_id, record.invocation.tool_id, "queued", "dispatch_queued")
            return queued

    def run_queued(self, request_id: str, *, context: ToolDispatchContext) -> ToolBrokerRecord:
        """Attempt one queued request; Core's default executor remains unavailable."""
        if not isinstance(context, ToolDispatchContext):
            raise TypeError("tool dispatch context is invalid")
        with self._lock:
            queued = self._require_record(request_id)
            if queued.state in TERMINAL_TOOL_STATES:
                return queued
            if queued.state != "queued":
                raise ToolBrokerError("tool request is not queued")
            if not context.matches(queued.invocation):
                return self._replace_terminal(queued, "denied", "binding_stale")
            if not self._executor.available:
                return self._replace_terminal(queued, "failed", "executor_unavailable")
            running = replace(queued, state="running", reason="dispatch_started")
            self._records[request_id] = running
            self._audit.append(request_id, queued.invocation.tool_id, "running", "dispatch_started")
            try:
                result = self._executor.execute(queued.invocation, queued.proposal)
            except Exception:
                return self._replace_terminal(running, "failed", "executor_failed")
            try:
                if not isinstance(result, ToolResult) or result.invocation_id != queued.invocation.invocation_id:
                    raise ValueError("invalid result")
                result = self._contracts.validate_result(result)
            except (TypeError, ValueError):
                return self._replace_terminal(running, "failed", "result_invalid")
            final_state = result.outcome
            if final_state not in TERMINAL_TOOL_STATES:
                return self._replace_terminal(running, "failed", "result_invalid")
            completed = replace(running, state=final_state, reason=(
                "completed" if final_state == "completed" else "executor_failed"
            ), result=result)
            self._records[request_id] = completed
            self._audit.append(request_id, queued.invocation.tool_id, completed.state, completed.reason)
            return completed

    def _require_record(self, request_id: object) -> ToolBrokerRecord:
        record = self._records.get(request_id) if isinstance(request_id, str) else None
        if record is None:
            raise ToolBrokerError("tool request was not found")
        return record

    def _require_active(self, request_id: object) -> ToolBrokerRecord:
        record = self._require_record(request_id)
        if record.state in TERMINAL_TOOL_STATES:
            raise ToolBrokerError("tool request is already terminal")
        return record

    def _replace_terminal(self, record: ToolBrokerRecord, state: str, reason: str) -> ToolBrokerRecord:
        updated = replace(record, state=state, reason=reason)
        self._records[record.invocation.invocation_id] = updated
        self._audit.append(record.invocation.invocation_id, record.invocation.tool_id, state, reason)
        return updated

    def _terminate(self, request_id: str, *, state: str, reason: str) -> ToolBrokerRecord:
        with self._lock:
            record = self._require_record(request_id)
            if record.state in TERMINAL_TOOL_STATES:
                return record
            if record.approval_id is not None:
                self._approvals.revoke(record.approval_id)
            if record.grant_id is not None:
                self._grants.revoke(record.grant_id)
            return self._replace_terminal(record, state, reason)


__all__ = [
    "DisabledToolExecutor", "ToolBroker", "ToolBrokerError", "ToolBrokerRecord",
    "ToolDispatchContext", "ToolExecutor",
]
