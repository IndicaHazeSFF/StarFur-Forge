import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_supervisor import (
    SUPERVISOR_SCHEMA_VERSION,
    SupervisorCancellation,
    SupervisorCancelReceipt,
    SupervisorCompletion,
    SupervisorLaunchRequest,
    SupervisorRunStatus,
)
from pipeline.tool_contracts import ToolProposal, ToolResult, build_core_tool_contract_registry
from pipeline.tool_grants import ToolInvocationIssuer


def proposal():
    return ToolProposal.from_mapping({
        "schema_version": 1,
        "tool_id": "sandbox.run",
        "tool_version": 1,
        "arguments": {
            "task_kind": "python_tests",
            "objective": "Verify supervisor contracts.",
            "files": [{"path": "main.py", "content": "print('bounded')"}],
        },
    })


def invocation():
    contracts = build_core_tool_contract_registry()
    return ToolInvocationIssuer(contracts, clock=lambda: 1000.0).issue(
        proposal(), invocation_id="TI-supervisor_1",
        trusted_principal_id="local.owner", session_instance_id="session-001",
        persona_id="murr", adventure_id=None, policy_revision="policy-v1",
        lifetime_seconds=300,
    )


def request():
    return SupervisorLaunchRequest.from_invocation(
        invocation(), worker_generation="TW-worker-001",
        issued_at=1001.0, authorization_deadline=1100.0,
    )


def completed_result():
    return ToolResult(
        1, "TI-supervisor_1", "sandbox.run", 1,
        "completed", 0, "private output", "", None,
    )


class SandboxSupervisorContractTests(unittest.TestCase):
    def test_launch_is_immutable_and_bound_to_exact_invocation(self):
        launch = request()
        self.assertTrue(launch.matches_invocation(invocation()))
        with self.assertRaises(AttributeError):
            launch.worker_generation = "TW-changed"
        with self.assertRaisesRegex(ValueError, "deadline"):
            SupervisorLaunchRequest.from_invocation(
                invocation(), worker_generation="TW-worker-001",
                issued_at=1100.0, authorization_deadline=1100.0,
            )
        changed = ToolInvocationIssuer(
            build_core_tool_contract_registry(), clock=lambda: 1000.0,
        ).issue(
            ToolProposal.from_mapping({
                "schema_version": 1, "tool_id": "sandbox.run", "tool_version": 1,
                "arguments": {
                    "task_kind": "python_tests", "objective": "Changed operation.",
                    "files": [{"path": "main.py", "content": "print('bounded')"}],
                },
            }),
            invocation_id="TI-supervisor_1", trusted_principal_id="local.owner",
            session_instance_id="session-001", persona_id="murr", adventure_id=None,
            policy_revision="policy-v1", lifetime_seconds=300,
        )
        self.assertFalse(launch.matches_invocation(changed))

    def test_cancellation_signal_is_a_request_not_stop_proof(self):
        signal = SupervisorCancellation()
        self.assertFalse(signal.requested)
        signal.request()
        self.assertTrue(signal.requested)
        receipt = SupervisorCancelReceipt(
            SUPERVISOR_SCHEMA_VERSION, request().invocation_id,
            request().worker_generation, "requested",
        )
        self.assertTrue(receipt.matches(request()))
        self.assertNotEqual("verified_stopped", receipt.state)

        status = SupervisorRunStatus.from_request(request(), state="cancel_requested")
        self.assertTrue(status.matches(request()))
        self.assertNotIn(request().binding_fingerprint, repr(status.public_dict()))

    def test_completion_requires_binding_and_verified_terminal_stop(self):
        launch = request()
        completion = SupervisorCompletion.from_request(
            launch, outcome="completed", stop_state="verified_stopped",
            result=completed_result(),
        )
        self.assertTrue(completion.matches(launch))
        public = repr(completion.public_dict())
        self.assertNotIn("private output", public)
        self.assertNotIn(launch.binding_fingerprint, public)
        self.assertNotIn("policy-v1", public)

        with self.assertRaisesRegex(ValueError, "verified stop"):
            SupervisorCompletion.from_request(
                launch, outcome="timed_out", stop_state="not_verified",
            )
        with self.assertRaisesRegex(ValueError, "requires completed result"):
            SupervisorCompletion.from_request(
                launch, outcome="completed", stop_state="verified_stopped",
            )
        with self.assertRaisesRegex(ValueError, "does not match"):
            SupervisorCompletion.from_request(
                launch, outcome="failed", stop_state="verified_stopped",
                result=completed_result(),
            )

    def test_unknown_outcome_retains_uncertainty_without_result_payload(self):
        completion = SupervisorCompletion.from_request(
            request(), outcome="outcome_unknown", stop_state="not_verified",
        )
        self.assertEqual("outcome_unknown", completion.outcome)
        with self.assertRaisesRegex(ValueError, "cannot include a result"):
            SupervisorCompletion.from_request(
                request(), outcome="outcome_unknown", stop_state="not_verified",
                result=completed_result(),
            )


if __name__ == "__main__":
    unittest.main()
