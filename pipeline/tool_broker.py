"""Provider-free tool broker with a disabled-by-default supervisor boundary.

This S3 broker joins validation, exact grants, and one-use approvals without
exposing commands or providers.  The Core factory uses ``DisabledToolSupervisor``
and therefore cannot execute ``sandbox.run``.  Injected supervisors are test-only
until a later reviewed isolation backend is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
import time
from typing import Callable

from .tool_approval import ToolApprovalController, ToolApprovalError
from .tool_audit import TOOL_AUDIT_REASONS, TOOL_LIFECYCLE_STATES, ToolAuditLog
from .tool_contracts import ToolContractRegistry, ToolProposal, ToolResult
from .tool_grants import (
    SessionToolGrantController, ToolGrantError, ToolInvocation, ToolInvocationIssuer,
)
from .tool_permissions import evaluate_tool_permission
from .tool_runs import ToolRunJournal, ToolRunJournalError, ToolRunOwnerLease
from .sandbox_supervisor import (
    DisabledToolSupervisor, SupervisorCancellation, SupervisorCancelReceipt,
    SupervisorCompletion, SupervisorLaunchRequest, ToolExecutionSupervisor,
    new_worker_generation,
)


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


@dataclass(frozen=True)
class _LaunchAuthorization:
    grant_id: str
    grant_revocation_generation: int
    authorization_deadline: float


@dataclass(frozen=True)
class _ActiveSupervision:
    request: SupervisorLaunchRequest
    cancellation: SupervisorCancellation


class ToolBroker:
    def __init__(
        self, contracts: ToolContractRegistry, issuer: ToolInvocationIssuer,
        grants: SessionToolGrantController, approvals: ToolApprovalController,
        *, supervisor: ToolExecutionSupervisor | None = None,
        audit: ToolAuditLog | None = None,
        run_journal: ToolRunJournal | None = None,
        run_journal_owner: ToolRunOwnerLease | None = None,
        clock: Callable[[], float] = time.time,
        worker_generation_factory: Callable[[], str] = new_worker_generation,
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
        if run_journal is not None and not isinstance(run_journal, ToolRunJournal):
            raise TypeError("tool broker run journal is invalid")
        if (run_journal is None) != (run_journal_owner is None):
            raise TypeError("tool broker journal and owner lease must be supplied together")
        if run_journal_owner is not None and not isinstance(run_journal_owner, ToolRunOwnerLease):
            raise TypeError("tool broker run journal owner lease is invalid")
        if isinstance(maximum_requests, bool) or not isinstance(maximum_requests, int) or not 1 <= maximum_requests <= 1024:
            raise ValueError("tool broker request limit is invalid")
        selected_supervisor = supervisor or DisabledToolSupervisor()
        if (
            not isinstance(getattr(selected_supervisor, "available", None), bool)
            or not callable(getattr(selected_supervisor, "run", None))
            or not callable(getattr(selected_supervisor, "request_cancel", None))
            or not callable(getattr(selected_supervisor, "query", None))
        ):
            raise TypeError("tool broker supervisor is invalid")
        if not callable(clock) or not callable(worker_generation_factory):
            raise TypeError("tool broker lifecycle dependency is invalid")
        self._contracts = contracts
        self._issuer = issuer
        self._grants = grants
        self._approvals = approvals
        self._supervisor = selected_supervisor
        self._audit = audit or ToolAuditLog()
        self._run_journal = run_journal
        self._run_journal_owner = run_journal_owner
        self._maximum_requests = maximum_requests
        self._clock = clock
        self._worker_generation_factory = worker_generation_factory
        self._records: dict[str, ToolBrokerRecord] = {}
        self._launch_authorizations: dict[str, _LaunchAuthorization] = {}
        self._active_supervision: dict[str, _ActiveSupervision] = {}
        self._used_worker_generations: set[str] = set()
        self._lock = RLock()
        if self._run_journal is not None:
            # The lifetime owner lease prevents another live process from being
            # reconciled. Recovery never restores a request, grant, or approval.
            self._run_journal.reconcile(owner=self._run_journal_owner)

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
            if self._run_journal is not None:
                try:
                    self._run_journal.record_intent(
                        invocation, owner=self._run_journal_owner,
                    )
                except ToolRunJournalError as error:
                    raise ToolBrokerError("tool request intent cannot be journaled") from error
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
        running: list[str] = []
        with self._lock:
            for request_id, record in tuple(self._records.items()):
                if record.state not in TERMINAL_TOOL_STATES and not context.matches(record.invocation):
                    if record.state == "running":
                        running.append(request_id)
                    else:
                        self._replace_terminal(record, "denied", "binding_stale")
                    changed += 1
        for request_id in running:
            self.cancel(request_id)
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
        with self._lock:
            record = self._require_record(request_id)
            running = record.state == "running"
        if running:
            return self.cancel(request_id)
        return self._terminate(request_id, state="denied", reason="denied_by_controller")

    def cancel(self, request_id: str) -> ToolBrokerRecord:
        with self._lock:
            record = self._require_record(request_id)
            if record.state in TERMINAL_TOOL_STATES:
                return record
            active = self._active_supervision.get(request_id)
            if record.state != "running" or active is None:
                return self._terminate(request_id, state="cancelled", reason="cancelled")
            active.cancellation.request()
            if record.grant_id is not None:
                self._grants.revoke(record.grant_id)
            requested = replace(record, reason="cancel_requested")
            self._records[request_id] = requested
            self._audit.append(
                request_id, record.invocation.tool_id, "running", "cancel_requested",
            )

        try:
            receipt = self._supervisor.request_cancel(active.request, active.cancellation)
        except Exception:
            return self._finish_unknown_if_running(request_id)
        if not isinstance(receipt, SupervisorCancelReceipt) or not receipt.matches(active.request):
            return self._finish_unknown_if_running(request_id)
        if receipt.state == "unknown":
            return self._finish_unknown_if_running(request_id)
        if receipt.state == "verified_stopped":
            with self._lock:
                current = self._require_record(request_id)
                if current.state in TERMINAL_TOOL_STATES:
                    return current
                self._active_supervision.pop(request_id, None)
                return self._replace_terminal(current, "cancelled", "cancelled")
        with self._lock:
            return self._require_record(request_id)

    def dispatch(self, request_id: str, *, context: ToolDispatchContext) -> ToolBrokerRecord:
        """Authorize, queue, and attempt one execution through the injected adapter."""
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
            if record.state in {"queued", "running"}:
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
            approval = self._approvals.get(record.approval_id)
            if approval is None:
                return self._replace_terminal(queued, "denied", "authorization_missing")
            self._launch_authorizations[request_id] = _LaunchAuthorization(
                grant.grant_id,
                grant.revocation_generation,
                min(record.invocation.expires_at, grant.expires_at, approval.expires_at),
            )
            self._audit.append(request_id, record.invocation.tool_id, "queued", "dispatch_queued")
            return queued

    def run_queued(self, request_id: str, *, context: ToolDispatchContext) -> ToolBrokerRecord:
        """Run one queued request without holding the broker lock through the effect."""
        if not isinstance(context, ToolDispatchContext):
            raise TypeError("tool dispatch context is invalid")
        with self._lock:
            queued = self._require_record(request_id)
            if queued.state in TERMINAL_TOOL_STATES:
                return queued
            if queued.state == "running":
                return queued
            if queued.state != "queued":
                raise ToolBrokerError("tool request is not queued")
            if not context.matches(queued.invocation):
                return self._replace_terminal(queued, "denied", "binding_stale")
            launch_time = self._clock()
            if not self._launch_is_authorized(queued, now=launch_time):
                return self._replace_terminal(queued, "denied", "authorization_expired")
            if not self._supervisor.available:
                return self._replace_terminal(queued, "failed", "supervisor_unavailable")
            authorization = self._launch_authorizations[request_id]
            try:
                worker_generation = self._worker_generation_factory()
                if worker_generation in self._used_worker_generations:
                    raise ValueError("worker generation was reused")
                request = SupervisorLaunchRequest.from_invocation(
                    queued.invocation,
                    worker_generation=worker_generation,
                    issued_at=launch_time,
                    authorization_deadline=authorization.authorization_deadline,
                )
            except (TypeError, ValueError):
                return self._replace_terminal(queued, "failed", "supervisor_binding_invalid")
            self._used_worker_generations.add(request.worker_generation)
            cancellation = SupervisorCancellation()
            running = replace(queued, state="running", reason="dispatch_started")
            self._records[request_id] = running
            self._active_supervision[request_id] = _ActiveSupervision(request, cancellation)
            self._audit.append(request_id, queued.invocation.tool_id, "running", "dispatch_started")

        try:
            completion = self._supervisor.run(
                request, queued.invocation, queued.proposal, cancellation,
            )
        except Exception:
            return self._finish_unknown_if_running(request_id)

        with self._lock:
            current = self._require_record(request_id)
            if current.state in TERMINAL_TOOL_STATES:
                return current
            self._active_supervision.pop(request_id, None)
            try:
                if not isinstance(completion, SupervisorCompletion) or not completion.matches(request):
                    raise ValueError("invalid supervisor completion")
                result = completion.result
                if result is not None:
                    if (
                        result.invocation_id != queued.invocation.invocation_id
                        or result.tool_id != queued.invocation.tool_id
                        or result.tool_version != queued.invocation.tool_version
                    ):
                        raise ValueError("invalid result binding")
                    contract = self._contracts.get(
                        queued.invocation.tool_id, queued.invocation.tool_version,
                    )
                    if contract is None:
                        raise ValueError("result contract unavailable")
                    result = contract.validate_result(result)
            except (TypeError, ValueError):
                return self._replace_terminal(
                    current, "outcome_unknown", "supervisor_outcome_unknown",
                )
            if completion.outcome == "outcome_unknown":
                return self._replace_terminal(
                    current, "outcome_unknown", "supervisor_outcome_unknown",
                )
            return self._replace_terminal(
                current,
                completion.outcome,
                {
                    "completed": "completed",
                    "cancelled": "cancelled",
                    "timed_out": "timed_out",
                    "failed": "supervisor_failed",
                }[completion.outcome],
                result=result,
            )

    def _launch_is_authorized(self, record: ToolBrokerRecord, *, now: float) -> bool:
        authorization = self._launch_authorizations.get(record.invocation.invocation_id)
        if authorization is None or now >= authorization.authorization_deadline:
            return False
        grant = self._grants.get(authorization.grant_id)
        return bool(
            grant is not None
            and not grant.revoked
            and grant.invocation_id == record.invocation.invocation_id
            and grant.binding == record.invocation.binding_tuple()
            and grant.revocation_generation == authorization.grant_revocation_generation
        )

    def _finish_unknown_if_running(self, request_id: str) -> ToolBrokerRecord:
        with self._lock:
            record = self._require_record(request_id)
            if record.state in TERMINAL_TOOL_STATES:
                return record
            self._active_supervision.pop(request_id, None)
            return self._replace_terminal(
                record, "outcome_unknown", "supervisor_outcome_unknown",
            )

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

    def _replace_terminal(
        self, record: ToolBrokerRecord, state: str, reason: str, *, result: ToolResult | None = None,
    ) -> ToolBrokerRecord:
        if self._run_journal is not None:
            try:
                self._run_journal.record_outcome(
                    record.invocation, owner=self._run_journal_owner,
                    state=state, reason=self._journal_reason_for_state(state),
                )
            except ToolRunJournalError:
                # If an effect may have completed but its durable outcome cannot
                # be recorded, fail closed locally.  The existing durable intent
                # will reconcile to unknown after restart; no retry is implied.
                updated = replace(record, state="outcome_unknown", reason="journal_write_failed", result=result)
                self._records[record.invocation.invocation_id] = updated
                self._audit.append(
                    record.invocation.invocation_id, record.invocation.tool_id,
                    "outcome_unknown", "journal_write_failed",
                )
                return updated
        updated = replace(record, state=state, reason=reason, result=result)
        self._records[record.invocation.invocation_id] = updated
        self._audit.append(record.invocation.invocation_id, record.invocation.tool_id, state, reason)
        return updated

    @staticmethod
    def _journal_reason_for_state(state: str) -> str:
        return {
            "completed": "completed", "failed": "failed", "denied": "denied",
            "cancelled": "cancelled", "timed_out": "timed_out",
            "outcome_unknown": "supervisor_outcome_unknown",
        }.get(state, "supervisor_outcome_unknown")

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
    "ToolBroker", "ToolBrokerError", "ToolBrokerRecord", "ToolDispatchContext",
]
