from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_contracts import ToolProposal, build_core_tool_contract_registry
from pipeline.tool_grants import ToolInvocationIssuer
from pipeline.tool_prerequisites import (
    SessionToolPrerequisiteController,
    ToolPrerequisiteError,
)


def invocation(*, invocation_id="TI-prerequisite_1", resource_refs=("TR-backend_1",), policy="policy-v1"):
    contracts = build_core_tool_contract_registry()
    proposal = ToolProposal.from_mapping({
        "schema_version": 1,
        "tool_id": "sandbox.run",
        "tool_version": 1,
        "arguments": {
            "task_kind": "python_tests",
            "objective": "Bound prerequisite fixture.",
            "files": [{"path": "main.py", "content": "print('ok')"}],
        },
    })
    return ToolInvocationIssuer(contracts, clock=lambda: 100.0).issue(
        proposal,
        trusted_principal_id="local.owner",
        session_instance_id="session-001",
        persona_id="murr",
        adventure_id=None,
        policy_revision=policy,
        resource_refs=resource_refs,
        lifetime_seconds=300,
        invocation_id=invocation_id,
    )


class ToolPrerequisiteTests(unittest.TestCase):
    def make_controller(self, now=None):
        current = [100.0] if now is None else now
        ids = iter((f"TP-receipt_{index}" for index in range(10)))
        return SessionToolPrerequisiteController(
            clock=lambda: current[0], id_factory=lambda: next(ids),
        ), current

    def test_receipt_binds_exact_invocation_requirement_resource_and_policy(self):
        controller, _ = self.make_controller()
        bound = invocation()
        receipt = controller.issue(
            bound,
            requirement_id="sandbox.backend",
            resource_ref="TR-backend_1",
            evidence_sha256="a" * 64,
        )
        self.assertTrue(receipt.matches(bound, "sandbox.backend"))
        self.assertFalse(receipt.matches(invocation(invocation_id="TI-other_1"), "sandbox.backend"))
        self.assertFalse(receipt.matches(invocation(policy="policy-v2"), "sandbox.backend"))
        with self.assertRaises(FrozenInstanceError):
            receipt.claimed = True

    def test_all_exact_requirements_are_claimed_atomically_once(self):
        controller, _ = self.make_controller()
        bound = invocation(resource_refs=("TR-backend_1", "TR-network_1"))
        first = controller.issue(
            bound, requirement_id="sandbox.backend", resource_ref="TR-backend_1",
            evidence_sha256="a" * 64,
        )
        second = controller.issue(
            bound, requirement_id="network.egress", resource_ref="TR-network_1",
            evidence_sha256="b" * 64,
        )
        claimed = controller.claim_all(bound, ("sandbox.backend", "network.egress"))
        self.assertEqual((first.prerequisite_id, second.prerequisite_id), tuple(
            item.prerequisite_id for item in claimed
        ))
        self.assertTrue(all(item.claimed for item in claimed))
        self.assertTrue(controller.claims_are_valid(bound, tuple(
            (item.prerequisite_id, item.revocation_generation) for item in claimed
        )))
        controller.revoke(claimed[0].prerequisite_id)
        self.assertFalse(controller.claims_are_valid(bound, tuple(
            (item.prerequisite_id, item.revocation_generation) for item in claimed
        )))
        with self.assertRaisesRegex(ToolPrerequisiteError, "missing|unavailable"):
            controller.claim_all(bound, ("sandbox.backend", "network.egress"))

    def test_missing_requirement_does_not_consume_an_available_receipt(self):
        controller, _ = self.make_controller()
        bound = invocation(resource_refs=("TR-backend_1", "TR-network_1"))
        controller.issue(
            bound, requirement_id="sandbox.backend", resource_ref="TR-backend_1",
            evidence_sha256="a" * 64,
        )
        with self.assertRaisesRegex(ToolPrerequisiteError, "missing"):
            controller.claim_all(bound, ("sandbox.backend", "network.egress"))
        claimed = controller.claim_all(bound, ("sandbox.backend",))
        self.assertTrue(claimed[0].claimed)

    def test_expiry_revocation_and_wrong_resource_fail_closed(self):
        controller, now = self.make_controller()
        bound = invocation()
        receipt = controller.issue(
            bound, requirement_id="sandbox.backend", resource_ref="TR-backend_1",
            evidence_sha256="a" * 64, lifetime_seconds=10,
        )
        now[0] = 110.0
        with self.assertRaisesRegex(ToolPrerequisiteError, "missing|unavailable"):
            controller.claim_all(bound, ("sandbox.backend",))

        controller, _ = self.make_controller()
        receipt = controller.issue(
            bound, requirement_id="sandbox.backend", resource_ref="TR-backend_1",
            evidence_sha256="a" * 64,
        )
        controller.revoke(receipt.prerequisite_id)
        with self.assertRaisesRegex(ToolPrerequisiteError, "missing|unavailable"):
            controller.claim_all(bound, ("sandbox.backend",))
        with self.assertRaisesRegex(ToolPrerequisiteError, "not invocation-bound"):
            controller.issue(
                bound, requirement_id="network.egress", resource_ref="TR-other_1",
                evidence_sha256="b" * 64,
            )

    def test_duplicate_capacity_and_malformed_evidence_deny(self):
        bound = invocation()
        controller, _ = self.make_controller()
        controller.issue(
            bound, requirement_id="sandbox.backend", resource_ref="TR-backend_1",
            evidence_sha256="a" * 64,
        )
        with self.assertRaisesRegex(ToolPrerequisiteError, "already"):
            controller.issue(
                bound, requirement_id="sandbox.backend", resource_ref="TR-backend_1",
                evidence_sha256="b" * 64,
            )
        with self.assertRaisesRegex(ToolPrerequisiteError, "digest"):
            controller.issue(
                invocation(invocation_id="TI-other_2"), requirement_id="sandbox.backend",
                resource_ref="TR-backend_1", evidence_sha256="raw evidence",
            )
        limited = SessionToolPrerequisiteController(
            clock=lambda: 100.0, id_factory=lambda: "TP-only", maximum_receipts=1,
        )
        limited.issue(
            bound, requirement_id="sandbox.backend", resource_ref="TR-backend_1",
            evidence_sha256="a" * 64,
        )
        with self.assertRaisesRegex(ToolPrerequisiteError, "capacity"):
            limited.issue(
                invocation(invocation_id="TI-other_3"), requirement_id="sandbox.backend",
                resource_ref="TR-backend_1", evidence_sha256="b" * 64,
            )

    def test_receipts_contain_no_raw_evidence_or_authority_fields(self):
        controller, _ = self.make_controller()
        receipt = controller.issue(
            invocation(), requirement_id="sandbox.backend", resource_ref="TR-backend_1",
            evidence_sha256="a" * 64,
        )
        rendered = repr(receipt).casefold()
        for forbidden in ("raw_evidence", "grant", "approval", "provider", "content"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
