import threading
import tempfile
import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_approval import ToolApprovalController
from pipeline.tool_audit import ToolAuditLog
from pipeline.tool_broker import ToolBroker, ToolBrokerError, ToolDispatchContext
from pipeline.tool_contracts import ToolProposal, ToolResult, build_core_tool_contract_registry
from pipeline.tool_grants import SessionToolGrantController, ToolInvocationIssuer
from pipeline.tool_prerequisites import SessionToolPrerequisiteController
from pipeline.tool_runs import ToolRunJournal
from pipeline.sandbox_supervisor import (
    SUPERVISOR_SCHEMA_VERSION, SupervisorCancelReceipt, SupervisorCompletion,
    SupervisorRunStatus,
)


class FakeSupervisor:
    available = True

    def __init__(self, *, completion_factory=None, error=None, cancel_state="requested"):
        self.completion_factory = completion_factory
        self.error = error
        self.cancel_state = cancel_state
        self.calls = 0
        self.cancel_calls = 0
        self.requests = []

    def supports(self, tool_id, tool_version):
        return tool_id == "sandbox.run" and tool_version == 1

    def run(self, request, invocation, proposal, cancellation):
        self.calls += 1
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.completion_factory is not None:
            return self.completion_factory(request, invocation)
        result = ToolResult(
            1, invocation.invocation_id, invocation.tool_id, invocation.tool_version,
            "completed", 0, "ok", "", None,
        )
        return SupervisorCompletion.from_request(
            request, outcome="completed", stop_state="verified_stopped", result=result,
        )

    def request_cancel(self, request, cancellation):
        self.cancel_calls += 1
        return SupervisorCancelReceipt(
            SUPERVISOR_SCHEMA_VERSION, request.invocation_id,
            request.worker_generation, self.cancel_state,
        )

    def query(self, request):
        return SupervisorRunStatus.from_request(request, state="running")


class ExplodingDisabledSupervisor:
    available = False

    def __init__(self):
        self.calls = 0

    def supports(self, tool_id, tool_version):
        raise AssertionError("disabled supervisor support was queried")

    def run(self, request, invocation, proposal, cancellation):
        self.calls += 1
        raise AssertionError("disabled supervisor was called")

    def request_cancel(self, request, cancellation):
        raise AssertionError("disabled supervisor cancellation was called")

    def query(self, request):
        raise AssertionError("disabled supervisor query was called")


class SlowSupervisor(FakeSupervisor):
    def __init__(self, *, cancel_state="requested"):
        super().__init__(cancel_state=cancel_state)
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, request, invocation, proposal, cancellation):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=5)
        if cancellation.requested:
            return SupervisorCompletion.from_request(
                request, outcome="cancelled", stop_state="verified_stopped",
                result=ToolResult(
                    1, invocation.invocation_id, invocation.tool_id,
                    invocation.tool_version, "cancelled", None, "", "",
                    "cancelled",
                ),
            )
        result = ToolResult(
            1, invocation.invocation_id, invocation.tool_id, invocation.tool_version,
            "completed", 0, "ok", "", None,
        )
        return SupervisorCompletion.from_request(
            request, outcome="completed", stop_state="verified_stopped", result=result,
        )

    def request_cancel(self, request, cancellation):
        receipt = super().request_cancel(request, cancellation)
        self.release.set()
        return receipt


def proposal(objective="Run safe tests."):
    return ToolProposal.from_mapping({
        "schema_version": 1, "tool_id": "sandbox.run", "tool_version": 1,
        "arguments": {
            "task_kind": "python_tests", "objective": objective,
            "files": [{"path": "main.py", "content": "print('secret-canary')"}],
        },
    })


class ToolBrokerTests(unittest.TestCase):
    def make_broker(
        self, supervisor=None, run_journal=None, run_journal_owner=None,
        *, prerequisites=None, clock=lambda: 1000.0,
        worker_generation_factory=lambda: "TW-broker-worker",
    ):
        contracts = build_core_tool_contract_registry()
        ids = iter((f"TG-grant_{index}" for index in range(20)))
        approvals = iter((f"TA-approval_{index}" for index in range(20)))
        broker = ToolBroker(
            contracts,
            ToolInvocationIssuer(contracts, clock=lambda: 1000.0),
            SessionToolGrantController(clock=lambda: 1000.0, id_factory=lambda: next(ids)),
            ToolApprovalController(clock=lambda: 1000.0, id_factory=lambda: next(approvals)),
            supervisor=supervisor,
            audit=ToolAuditLog(clock=lambda: 1000.0),
            run_journal=run_journal,
            run_journal_owner=run_journal_owner,
            prerequisites=prerequisites,
            clock=clock,
            worker_generation_factory=worker_generation_factory,
        )
        return broker

    def submit(self, broker, request_id="TI-request_1", **overrides):
        values = {
            "request_id": request_id,
            "trusted_principal_id": "local.owner",
            "session_instance_id": "session-001",
            "persona_id": "murr",
            "adventure_id": None,
            "policy_revision": "policy-v1",
            "resource_refs": ("TR-backend_fixture",),
        }
        values.update(overrides)
        return broker.submit(proposal(), **values)

    def context(self, **overrides):
        values = {
            "principal_id": "local.owner", "session_instance_id": "session-001",
            "persona_id": "murr", "adventure_id": None, "policy_revision": "policy-v1",
        }
        values.update(overrides)
        return ToolDispatchContext(**values)

    def authorize(self, broker, request_id="TI-request_1"):
        broker.grant(request_id)
        broker.approve(request_id)
        return broker.record_prerequisite(
            request_id,
            requirement_id="sandbox.backend",
            resource_ref="TR-backend_fixture",
            evidence_sha256="a" * 64,
        )

    def test_revoked_prerequisite_is_rechecked_immediately_before_launch(self):
        controller = SessionToolPrerequisiteController(
            clock=lambda: 1000.0, id_factory=lambda: "TP-broker_fixture",
        )
        supervisor = FakeSupervisor()
        broker = self.make_broker(supervisor, prerequisites=controller)
        self.submit(broker)
        receipt = self.authorize(broker)
        self.assertEqual("queued", broker.queue("TI-request_1", context=self.context()).state)
        controller.revoke(receipt.prerequisite_id)
        denied = broker.run_queued("TI-request_1", context=self.context())
        self.assertEqual(("denied", "authorization_expired"), (denied.state, denied.reason))
        self.assertEqual(0, supervisor.calls)

    def test_exact_prerequisite_commitment_reaches_supervisor_launch(self):
        supervisor = FakeSupervisor()
        broker = self.make_broker(supervisor)
        self.submit(broker)
        self.authorize(broker)
        completed = broker.dispatch("TI-request_1", context=self.context())
        self.assertEqual("completed", completed.state)
        self.assertEqual(1, len(supervisor.requests))
        commitments = supervisor.requests[0].prerequisite_bindings
        self.assertEqual(1, len(commitments))
        self.assertEqual("sandbox.backend", commitments[0].requirement_id)
        self.assertEqual("TR-backend_fixture", commitments[0].resource_ref)
        self.assertEqual("a" * 64, commitments[0].evidence_sha256)

    def test_exact_resource_prerequisite_is_required_before_queueing(self):
        supervisor = FakeSupervisor()
        broker = self.make_broker(supervisor)
        self.submit(broker)
        broker.grant("TI-request_1")
        broker.approve("TI-request_1")
        denied = broker.queue("TI-request_1", context=self.context())
        self.assertEqual(("denied", "resource_prerequisite_missing"), (denied.state, denied.reason))
        self.assertEqual(0, supervisor.calls)

        broker = self.make_broker(supervisor)
        self.submit(broker, request_id="TI-request_2")
        with self.assertRaisesRegex(ToolBrokerError, "could not be recorded"):
            broker.record_prerequisite(
                "TI-request_2",
                requirement_id="sandbox.backend",
                resource_ref="TR-wrong_fixture",
                evidence_sha256="a" * 64,
            )
        with self.assertRaisesRegex(ToolBrokerError, "not required"):
            broker.record_prerequisite(
                "TI-request_2",
                requirement_id="network.egress",
                resource_ref="TR-backend_fixture",
                evidence_sha256="a" * 64,
            )

    def test_default_disabled_supervisor_fails_without_calling_it(self):
        supervisor = ExplodingDisabledSupervisor()
        broker = self.make_broker(supervisor)
        self.submit(broker)
        self.authorize(broker)
        result = broker.dispatch("TI-request_1", context=self.context())

        self.assertEqual("failed", result.state)
        self.assertEqual("supervisor_unavailable", result.reason)
        self.assertEqual(0, supervisor.calls)

    def test_available_supervisor_for_another_tool_is_not_called(self):
        supervisor = FakeSupervisor()
        supervisor.supports = lambda tool_id, tool_version: (
            tool_id == "web.fetch" and tool_version == 1
        )
        broker = self.make_broker(supervisor)
        self.submit(broker)
        self.authorize(broker)
        result = broker.dispatch("TI-request_1", context=self.context())
        self.assertEqual(("failed", "executor_unavailable"), (result.state, result.reason))
        self.assertEqual(0, supervisor.calls)
        self.assertIsNone(result.result)

    def test_missing_authority_and_stale_context_deny_without_execution(self):
        supervisor = FakeSupervisor()
        broker = self.make_broker(supervisor)
        self.submit(broker)
        denied = broker.dispatch("TI-request_1", context=self.context())
        self.assertEqual(("denied", "authorization_missing"), (denied.state, denied.reason))
        self.assertEqual(0, supervisor.calls)

        broker = self.make_broker(supervisor)
        self.submit(broker, request_id="TI-request_2")
        self.authorize(broker, "TI-request_2")
        stale = broker.dispatch(
            "TI-request_2", context=self.context(session_instance_id="session-recreated"),
        )
        self.assertEqual(("denied", "binding_stale"), (stale.state, stale.reason))
        self.assertEqual(0, supervisor.calls)

    def test_duplicate_submission_is_idempotent_and_conflict_fails(self):
        broker = self.make_broker()
        first = self.submit(broker)
        repeated = self.submit(broker)
        self.assertIs(first, repeated)
        with self.assertRaisesRegex(ToolBrokerError, "conflicting"):
            broker.submit(
                proposal("Changed."), request_id="TI-request_1",
                trusted_principal_id="local.owner", session_instance_id="session-001",
                persona_id="murr", adventure_id=None, policy_revision="policy-v1",
            )

    def test_success_is_once_only_and_public_status_excludes_payload(self):
        supervisor = FakeSupervisor()
        broker = self.make_broker(supervisor)
        self.submit(broker)
        self.authorize(broker)
        completed = broker.dispatch("TI-request_1", context=self.context())
        repeated = broker.dispatch("TI-request_1", context=self.context())

        self.assertEqual("completed", completed.state)
        self.assertEqual(1, supervisor.calls)
        self.assertIs(completed, repeated)
        rendered = repr(completed.public_dict()) + repr(broker.audit.public_dict())
        self.assertNotIn("secret-canary", rendered)
        self.assertNotIn("stdout", repr(completed.public_dict()))

    def test_cancel_and_invalid_or_exploding_supervisor_fail_closed(self):
        broker = self.make_broker(FakeSupervisor())
        self.submit(broker)
        self.assertEqual("cancelled", broker.cancel("TI-request_1").state)

        malformed = FakeSupervisor(completion_factory=lambda request, invocation: object())
        broker = self.make_broker(malformed)
        self.submit(broker, request_id="TI-request_2")
        self.authorize(broker, "TI-request_2")
        self.assertEqual("supervisor_outcome_unknown", broker.dispatch(
            "TI-request_2", context=self.context(),
        ).reason)

        exploding = FakeSupervisor(error=RuntimeError("secret-token-do-not-leak"))
        broker = self.make_broker(exploding)
        self.submit(broker, request_id="TI-request_3")
        self.authorize(broker, "TI-request_3")
        failed = broker.dispatch("TI-request_3", context=self.context())
        self.assertEqual("supervisor_outcome_unknown", failed.reason)
        self.assertNotIn("secret-token", repr(failed.public_dict()) + repr(broker.audit.public_dict()))

    def test_queued_request_can_be_cancelled_before_any_effect(self):
        supervisor = FakeSupervisor()
        broker = self.make_broker(supervisor)
        self.submit(broker)
        self.authorize(broker)
        queued = broker.queue("TI-request_1", context=self.context())
        self.assertEqual("queued", queued.state)
        self.assertEqual("cancelled", broker.cancel("TI-request_1").state)
        self.assertEqual("cancelled", broker.run_queued(
            "TI-request_1", context=self.context(),
        ).state)
        self.assertEqual(0, supervisor.calls)

    def test_concurrent_dispatch_invokes_supervisor_once(self):
        supervisor = SlowSupervisor()
        supervisor.release.set()
        broker = self.make_broker(supervisor)
        self.submit(broker)
        self.authorize(broker)
        barrier = threading.Barrier(5)
        states = []
        states_lock = threading.Lock()

        def dispatch():
            barrier.wait()
            state = broker.dispatch("TI-request_1", context=self.context()).state
            with states_lock:
                states.append(state)

        threads = [threading.Thread(target=dispatch) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, supervisor.calls)
        self.assertEqual("completed", broker.get("TI-request_1").state)
        self.assertTrue(set(states).issubset({"running", "completed"}))

    def test_launch_rechecks_expiry_and_revocation_after_queue(self):
        now = [1000.0]
        supervisor = FakeSupervisor()
        broker = self.make_broker(supervisor, clock=lambda: now[0])
        self.submit(broker)
        self.authorize(broker)
        queued = broker.queue("TI-request_1", context=self.context())
        broker._grants.revoke(queued.grant_id)

        denied = broker.run_queued("TI-request_1", context=self.context())

        self.assertEqual(("denied", "authorization_expired"), (denied.state, denied.reason))
        self.assertEqual(0, supervisor.calls)

        broker = self.make_broker(supervisor, clock=lambda: now[0])
        self.submit(broker, request_id="TI-request_2")
        self.authorize(broker, "TI-request_2")
        broker.queue("TI-request_2", context=self.context())
        now[0] = 1201.0
        expired = broker.run_queued("TI-request_2", context=self.context())
        self.assertEqual(("denied", "authorization_expired"), (expired.state, expired.reason))
        self.assertEqual(0, supervisor.calls)

    def test_running_cancel_reaches_supervisor_without_waiting_for_run_lock(self):
        supervisor = SlowSupervisor()
        broker = self.make_broker(supervisor)
        self.submit(broker)
        self.authorize(broker)
        worker = threading.Thread(
            target=lambda: broker.dispatch("TI-request_1", context=self.context()),
        )
        worker.start()
        self.assertTrue(supervisor.started.wait(timeout=1))

        requested = broker.cancel("TI-request_1")
        worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(1, supervisor.cancel_calls)
        self.assertIn(requested.state, {"running", "cancelled"})
        self.assertEqual("cancelled", broker.get("TI-request_1").state)
        self.assertEqual(1, supervisor.calls)

    def test_verified_timeout_is_terminal_but_unverified_or_mismatched_is_unknown(self):
        def timeout(request, invocation):
            return SupervisorCompletion.from_request(
                request, outcome="timed_out", stop_state="verified_stopped",
                result=ToolResult(
                    1, invocation.invocation_id, invocation.tool_id,
                    invocation.tool_version, "timed_out", None, "", "",
                    "timed_out",
                ),
            )

        broker = self.make_broker(FakeSupervisor(completion_factory=timeout))
        self.submit(broker)
        self.authorize(broker)
        self.assertEqual("timed_out", broker.dispatch(
            "TI-request_1", context=self.context(),
        ).state)

        def mismatched(request, invocation):
            result = ToolResult(
                1, invocation.invocation_id, invocation.tool_id,
                invocation.tool_version, "completed", 0, "", "", None,
            )
            return SupervisorCompletion(
                request.schema_version, request.invocation_id, request.tool_id,
                request.tool_version, request.binding_fingerprint,
                request.policy_revision, "TW-wrong-worker", "completed",
                "verified_stopped", result,
            )

        broker = self.make_broker(FakeSupervisor(completion_factory=mismatched))
        self.submit(broker, request_id="TI-request_2")
        self.authorize(broker, "TI-request_2")
        unknown = broker.dispatch("TI-request_2", context=self.context())
        self.assertEqual(("outcome_unknown", "supervisor_outcome_unknown"), (
            unknown.state, unknown.reason,
        ))

    def test_worker_generation_reuse_denies_second_launch(self):
        supervisor = FakeSupervisor()
        broker = self.make_broker(
            supervisor, worker_generation_factory=lambda: "TW-reused-worker",
        )
        self.submit(broker)
        self.authorize(broker)
        self.assertEqual("completed", broker.dispatch(
            "TI-request_1", context=self.context(),
        ).state)

        self.submit(broker, request_id="TI-request_2")
        self.authorize(broker, "TI-request_2")
        rejected = broker.dispatch("TI-request_2", context=self.context())

        self.assertEqual(
            ("failed", "supervisor_binding_invalid"), (rejected.state, rejected.reason),
        )
        self.assertEqual(1, supervisor.calls)

    def test_unknown_cancel_receipt_fences_running_work(self):
        supervisor = SlowSupervisor(cancel_state="unknown")
        broker = self.make_broker(supervisor)
        self.submit(broker)
        self.authorize(broker)
        worker = threading.Thread(
            target=lambda: broker.dispatch("TI-request_1", context=self.context()),
        )
        worker.start()
        self.assertTrue(supervisor.started.wait(timeout=1))

        unknown = broker.cancel("TI-request_1")
        worker.join(timeout=2)

        self.assertEqual(("outcome_unknown", "supervisor_outcome_unknown"), (
            unknown.state, unknown.reason,
        ))
        self.assertEqual("outcome_unknown", broker.get("TI-request_1").state)

    def test_optional_durable_journal_records_outcome_and_never_restores_authority(self):
        with tempfile.TemporaryDirectory() as root:
            journal = ToolRunJournal(
                root, clock=lambda: 1000.0,
                owner_epoch_factory=lambda: "TO-broker-owner",
            )
            owner = journal.acquire_owner("core.broker-test")
            try:
                supervisor = FakeSupervisor()
                broker = self.make_broker(
                    supervisor, run_journal=journal, run_journal_owner=owner,
                )
                self.submit(broker)
                self.authorize(broker)
                self.assertEqual("completed", broker.dispatch(
                    "TI-request_1", context=self.context(),
                ).state)
                self.assertEqual(("intent", "outcome"), tuple(item.kind for item in journal.records()))

                # A new broker only reconciles durable records; it does not recreate
                # a dispatchable request, grant, or approval.
                restarted = self.make_broker(
                    FakeSupervisor(), run_journal=journal, run_journal_owner=owner,
                )
                self.assertEqual((), restarted.records())
            finally:
                if owner.active:
                    journal.release_owner(owner)

    def test_live_shared_owner_is_not_reconciled_and_historical_submit_is_fenced(self):
        with tempfile.TemporaryDirectory() as root:
            journal = ToolRunJournal(
                root, clock=lambda: 1000.0,
                owner_epoch_factory=lambda: "TO-shared-owner",
            )
            owner = journal.acquire_owner("core.broker-test")
            try:
                first = self.make_broker(
                    FakeSupervisor(), run_journal=journal, run_journal_owner=owner,
                )
                self.submit(first)

                second = self.make_broker(
                    FakeSupervisor(), run_journal=journal, run_journal_owner=owner,
                )
                self.assertEqual(("intent",), tuple(item.kind for item in journal.records()))
                with self.assertRaisesRegex(ToolBrokerError, "cannot be journaled"):
                    self.submit(second)

                self.authorize(first)
                self.assertEqual("completed", first.dispatch(
                    "TI-request_1", context=self.context(),
                ).state)
            finally:
                if owner.active:
                    journal.release_owner(owner)

    def test_post_launch_failure_is_durably_unknown_and_never_retried(self):
        with tempfile.TemporaryDirectory() as root:
            journal = ToolRunJournal(
                root, clock=lambda: 1000.0,
                owner_epoch_factory=lambda: "TO-unknown-owner",
            )
            owner = journal.acquire_owner("core.broker-test")
            try:
                supervisor = FakeSupervisor(error=RuntimeError("lost worker"))
                broker = self.make_broker(
                    supervisor, run_journal=journal, run_journal_owner=owner,
                )
                self.submit(broker)
                self.authorize(broker)

                unknown = broker.dispatch("TI-request_1", context=self.context())
                repeated = broker.dispatch("TI-request_1", context=self.context())

                self.assertEqual("outcome_unknown", unknown.state)
                self.assertIs(unknown, repeated)
                self.assertEqual(1, supervisor.calls)
                self.assertEqual(
                    ("submitted", "supervisor_outcome_unknown"),
                    tuple(item.reason for item in journal.records()),
                )
            finally:
                if owner.active:
                    journal.release_owner(owner)

    def test_journal_requires_an_explicit_owner_lease(self):
        with tempfile.TemporaryDirectory() as root:
            journal = ToolRunJournal(root)
            with self.assertRaisesRegex(TypeError, "supplied together"):
                self.make_broker(run_journal=journal)


if __name__ == "__main__":
    unittest.main()
