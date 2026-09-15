import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_supervisor import (
    SupervisorCancellation,
    SupervisorCancelReceipt,
    SupervisorCompletion,
    SupervisorLaunchRequest,
    SupervisorRunStatus,
)
from pipeline.tool_contracts import ToolProposal, ToolResult, build_core_tool_contract_registry
from pipeline.tool_execution_router import ToolExecutionBinding, ToolExecutionRouter
from pipeline.tool_grants import ToolInvocationIssuer


def proposal(tool_id="sandbox.run"):
    arguments = (
        {"task_kind": "python_tests", "objective": "Check exact routing.",
         "files": [{"path": "main.py", "content": "print('ok')"}]}
        if tool_id == "sandbox.run" else {"url": "https://example.com/reference"}
    )
    return ToolProposal.from_mapping({
        "schema_version": 1, "tool_id": tool_id, "tool_version": 1,
        "arguments": arguments,
    })


def invocation(tool_id="sandbox.run"):
    contracts = build_core_tool_contract_registry()
    return ToolInvocationIssuer(contracts, clock=lambda: 1000.0).issue(
        proposal(tool_id), invocation_id="TI-router_1",
        trusted_principal_id="local.owner", session_instance_id="session-001",
        persona_id="murr", adventure_id=None, policy_revision="policy-v1",
    )


def launch(tool_id="sandbox.run"):
    return SupervisorLaunchRequest.from_invocation(
        invocation(tool_id), worker_generation="TW-router-001",
        issued_at=1001.0, authorization_deadline=1100.0,
    )


class FakeExactSupervisor:
    available = True

    def __init__(self, tool_id):
        self.tool_id = tool_id
        self.calls = 0

    def supports(self, tool_id, tool_version):
        return (tool_id, tool_version) == (self.tool_id, 1)

    def run(self, request, invocation_value, proposal_value, cancellation):
        self.calls += 1
        artifact_refs = ("TF-web_result",) if self.tool_id == "web.fetch" else ()
        result = ToolResult(
            1, invocation_value.invocation_id, invocation_value.tool_id,
            invocation_value.tool_version, "completed",
            None if self.tool_id == "web.fetch" else 0,
            "" if self.tool_id == "web.fetch" else "ok", "", None, artifact_refs,
        )
        return SupervisorCompletion.from_request(
            request, outcome="completed", stop_state="verified_stopped", result=result,
        )

    def request_cancel(self, request, cancellation):
        return SupervisorCancelReceipt(1, request.invocation_id, request.worker_generation, "requested")

    def query(self, request):
        return SupervisorRunStatus.from_request(request, state="running")


class ToolExecutionRouterTests(unittest.TestCase):
    def test_routes_only_to_exact_tool_and_version(self):
        sandbox = FakeExactSupervisor("sandbox.run")
        web = FakeExactSupervisor("web.fetch")
        router = ToolExecutionRouter((
            ToolExecutionBinding("sandbox.run", 1, sandbox),
            ToolExecutionBinding("web.fetch", 1, web),
        ))
        self.assertTrue(router.supports("sandbox.run", 1))
        self.assertTrue(router.supports("web.fetch", 1))
        self.assertFalse(router.supports("web.fetch", 2))
        result = router.run(
            launch("web.fetch"), invocation("web.fetch"), proposal("web.fetch"),
            SupervisorCancellation(),
        )
        self.assertEqual("web.fetch", result.tool_id)
        self.assertEqual((0, 1), (sandbox.calls, web.calls))

    def test_unbound_or_adapter_rejected_operation_fails_closed(self):
        adapter = FakeExactSupervisor("sandbox.run")
        router = ToolExecutionRouter((ToolExecutionBinding("web.fetch", 1, adapter),))
        self.assertFalse(router.available)
        self.assertFalse(router.supports("web.fetch", 1))
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            router.run(
                launch("web.fetch"), invocation("web.fetch"), proposal("web.fetch"),
                SupervisorCancellation(),
            )
        self.assertEqual(0, adapter.calls)

    def test_mismatched_proposal_never_reaches_adapter(self):
        adapter = FakeExactSupervisor("sandbox.run")
        router = ToolExecutionRouter((ToolExecutionBinding("sandbox.run", 1, adapter),))
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            router.run(
                launch("sandbox.run"), invocation("sandbox.run"), proposal("web.fetch"),
                SupervisorCancellation(),
            )
        self.assertEqual(0, adapter.calls)

    def test_duplicate_binding_is_rejected(self):
        adapter = FakeExactSupervisor("sandbox.run")
        with self.assertRaisesRegex(ValueError, "unique"):
            ToolExecutionRouter((
                ToolExecutionBinding("sandbox.run", 1, adapter),
                ToolExecutionBinding("sandbox.run", 1, adapter),
            ))


if __name__ == "__main__":
    unittest.main()
