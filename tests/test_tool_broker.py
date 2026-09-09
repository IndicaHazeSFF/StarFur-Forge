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
from pipeline.tool_runs import ToolRunJournal


class FakeExecutor:
    available = True

    def __init__(self, *, result_factory=None, error=None):
        self.result_factory = result_factory
        self.error = error
        self.calls = 0

    def execute(self, invocation, proposal):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.result_factory is not None:
            return self.result_factory(invocation)
        return ToolResult(
            1, invocation.invocation_id, invocation.tool_id, invocation.tool_version,
            "completed", 0, "ok", "", None,
        )


class ExplodingDisabledExecutor:
    available = False

    def __init__(self):
        self.calls = 0

    def execute(self, invocation, proposal):
        self.calls += 1
        raise AssertionError("disabled executor was called")


def proposal(objective="Run safe tests."):
    return ToolProposal.from_mapping({
        "schema_version": 1, "tool_id": "sandbox.run", "tool_version": 1,
        "arguments": {
            "task_kind": "python_tests", "objective": objective,
            "files": [{"path": "main.py", "content": "print('secret-canary')"}],
        },
    })


class ToolBrokerTests(unittest.TestCase):
    def make_broker(self, executor=None, run_journal=None, run_journal_owner=None):
        contracts = build_core_tool_contract_registry()
        ids = iter((f"TG-grant_{index}" for index in range(20)))
        approvals = iter((f"TA-approval_{index}" for index in range(20)))
        broker = ToolBroker(
            contracts,
            ToolInvocationIssuer(contracts, clock=lambda: 1000.0),
            SessionToolGrantController(clock=lambda: 1000.0, id_factory=lambda: next(ids)),
            ToolApprovalController(clock=lambda: 1000.0, id_factory=lambda: next(approvals)),
            executor=executor,
            audit=ToolAuditLog(clock=lambda: 1000.0),
            run_journal=run_journal,
            run_journal_owner=run_journal_owner,
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

    def test_default_disabled_executor_fails_without_calling_it(self):
        executor = ExplodingDisabledExecutor()
        broker = self.make_broker(executor)
        self.submit(broker)
        self.authorize(broker)
        result = broker.dispatch("TI-request_1", context=self.context())

        self.assertEqual("failed", result.state)
        self.assertEqual("executor_unavailable", result.reason)
        self.assertEqual(0, executor.calls)
        self.assertIsNone(result.result)

    def test_missing_authority_and_stale_context_deny_without_execution(self):
        executor = FakeExecutor()
        broker = self.make_broker(executor)
        self.submit(broker)
        denied = broker.dispatch("TI-request_1", context=self.context())
        self.assertEqual(("denied", "authorization_missing"), (denied.state, denied.reason))
        self.assertEqual(0, executor.calls)

        broker = self.make_broker(executor)
        self.submit(broker, request_id="TI-request_2")
        self.authorize(broker, "TI-request_2")
        stale = broker.dispatch(
            "TI-request_2", context=self.context(session_instance_id="session-recreated"),
        )
        self.assertEqual(("denied", "binding_stale"), (stale.state, stale.reason))
        self.assertEqual(0, executor.calls)

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
        executor = FakeExecutor()
        broker = self.make_broker(executor)
        self.submit(broker)
        self.authorize(broker)
        completed = broker.dispatch("TI-request_1", context=self.context())
        repeated = broker.dispatch("TI-request_1", context=self.context())

        self.assertEqual("completed", completed.state)
        self.assertEqual(1, executor.calls)
        self.assertIs(completed, repeated)
        rendered = repr(completed.public_dict()) + repr(broker.audit.public_dict())
        self.assertNotIn("secret-canary", rendered)
        self.assertNotIn("stdout", repr(completed.public_dict()))

    def test_cancel_and_invalid_or_exploding_executor_fail_closed(self):
        broker = self.make_broker(FakeExecutor())
        self.submit(broker)
        self.assertEqual("cancelled", broker.cancel("TI-request_1").state)

        malformed = FakeExecutor(result_factory=lambda invocation: object())
        broker = self.make_broker(malformed)
        self.submit(broker, request_id="TI-request_2")
        self.authorize(broker, "TI-request_2")
        self.assertEqual("result_invalid", broker.dispatch(
            "TI-request_2", context=self.context(),
        ).reason)

        exploding = FakeExecutor(error=RuntimeError("secret-token-do-not-leak"))
        broker = self.make_broker(exploding)
        self.submit(broker, request_id="TI-request_3")
        self.authorize(broker, "TI-request_3")
        failed = broker.dispatch("TI-request_3", context=self.context())
        self.assertEqual("executor_failed", failed.reason)
        self.assertNotIn("secret-token", repr(failed.public_dict()) + repr(broker.audit.public_dict()))

    def test_queued_request_can_be_cancelled_before_any_effect(self):
        executor = FakeExecutor()
        broker = self.make_broker(executor)
        self.submit(broker)
        self.authorize(broker)
        queued = broker.queue("TI-request_1", context=self.context())
        self.assertEqual("queued", queued.state)
        self.assertEqual("cancelled", broker.cancel("TI-request_1").state)
        self.assertEqual("cancelled", broker.run_queued(
            "TI-request_1", context=self.context(),
        ).state)
        self.assertEqual(0, executor.calls)

    def test_concurrent_dispatch_invokes_executor_once(self):
        executor = FakeExecutor()
        broker = self.make_broker(executor)
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
        self.assertEqual(1, executor.calls)
        self.assertEqual(["completed"] * 5, sorted(states))

    def test_optional_durable_journal_records_outcome_and_never_restores_authority(self):
        with tempfile.TemporaryDirectory() as root:
            journal = ToolRunJournal(
                root, clock=lambda: 1000.0,
                owner_epoch_factory=lambda: "TO-broker-owner",
            )
            owner = journal.acquire_owner("core.broker-test")
            try:
                executor = FakeExecutor()
                broker = self.make_broker(
                    executor, run_journal=journal, run_journal_owner=owner,
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
                    FakeExecutor(), run_journal=journal, run_journal_owner=owner,
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
                    FakeExecutor(), run_journal=journal, run_journal_owner=owner,
                )
                self.submit(first)

                second = self.make_broker(
                    FakeExecutor(), run_journal=journal, run_journal_owner=owner,
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

    def test_journal_requires_an_explicit_owner_lease(self):
        with tempfile.TemporaryDirectory() as root:
            journal = ToolRunJournal(root)
            with self.assertRaisesRegex(TypeError, "supplied together"):
                self.make_broker(run_journal=journal)


if __name__ == "__main__":
    unittest.main()
