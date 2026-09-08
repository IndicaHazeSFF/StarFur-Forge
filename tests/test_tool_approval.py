import threading
import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_approval import ToolApprovalController, ToolApprovalError, ToolApprovalEvidence
from pipeline.tool_contracts import ToolProposal, build_core_tool_contract_registry
from pipeline.tool_grants import SessionToolGrantController, ToolInvocationIssuer


class MutableClock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value


def proposal():
    return ToolProposal.from_mapping({
        "schema_version": 1, "tool_id": "sandbox.run", "tool_version": 1,
        "arguments": {
            "task_kind": "python_tests", "objective": "Run tests.",
            "files": [{"path": "main.py", "content": "print('ok')"}],
        },
    })


class ToolApprovalTests(unittest.TestCase):
    def setUp(self):
        self.clock = MutableClock()
        self.issuer = ToolInvocationIssuer(
            build_core_tool_contract_registry(), clock=self.clock, id_factory=lambda: "TI-approval_1",
        )
        self.invocation = self.issuer.issue(
            proposal(), trusted_principal_id="local.owner", session_instance_id="session-001",
            persona_id="murr", adventure_id=None, policy_revision="policy-v1",
        )
        self.grants = SessionToolGrantController(
            clock=self.clock, id_factory=lambda: "TG-approval_1",
        )
        self.grant = self.grants.issue(self.invocation)
        approval_ids = iter((f"TA-approval_{index}" for index in range(1, 10)))
        self.approvals = ToolApprovalController(
            clock=self.clock, id_factory=lambda: next(approval_ids),
        )

    def test_approval_is_exact_and_single_use(self):
        approval = self.approvals.approve(self.invocation, self.grant)
        evidence = self.approvals.claim(approval.approval_id, self.invocation, self.grant)
        self.assertIsInstance(evidence, ToolApprovalEvidence)
        with self.assertRaisesRegex(ToolApprovalError, "already consumed"):
            self.approvals.claim(approval.approval_id, self.invocation, self.grant)

    def test_boolean_or_changed_revocation_generation_cannot_confirm(self):
        approval = self.approvals.approve(self.invocation, self.grant)
        with self.assertRaisesRegex(ToolApprovalError, "not found"):
            self.approvals.claim(True, self.invocation, self.grant)
        revoked = self.grants.revoke(self.grant.grant_id)
        with self.assertRaisesRegex(ToolApprovalError, "stale or mismatched"):
            self.approvals.claim(approval.approval_id, self.invocation, revoked)

    def test_expired_or_cross_invocation_approval_fails(self):
        approval = self.approvals.approve(self.invocation, self.grant, lifetime_seconds=10)
        self.clock.value += 10
        with self.assertRaisesRegex(ToolApprovalError, "expired"):
            self.approvals.claim(approval.approval_id, self.invocation, self.grant)

        self.clock.value = 1001
        other_issuer = ToolInvocationIssuer(
            build_core_tool_contract_registry(), clock=self.clock, id_factory=lambda: "TI-approval_2",
        )
        other = other_issuer.issue(
            proposal(), trusted_principal_id="local.owner", session_instance_id="session-002",
            persona_id="murr", adventure_id=None, policy_revision="policy-v1",
        )
        other_grants = SessionToolGrantController(
            clock=self.clock, id_factory=lambda: "TG-approval_2",
        )
        other_grant = other_grants.issue(other)
        other_approval = self.approvals.approve(other, other_grant)
        with self.assertRaisesRegex(ToolApprovalError, "stale or mismatched"):
            self.approvals.claim(other_approval.approval_id, self.invocation, self.grant)

    def test_concurrent_claim_has_exactly_one_winner(self):
        approval = self.approvals.approve(self.invocation, self.grant)
        barrier = threading.Barrier(6)
        outcomes = []
        lock = threading.Lock()

        def claim():
            barrier.wait()
            try:
                self.approvals.claim(approval.approval_id, self.invocation, self.grant)
                value = "won"
            except ToolApprovalError:
                value = "denied"
            with lock:
                outcomes.append(value)

        threads = [threading.Thread(target=claim) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, outcomes.count("won"))
        self.assertEqual(5, outcomes.count("denied"))


if __name__ == "__main__":
    unittest.main()
