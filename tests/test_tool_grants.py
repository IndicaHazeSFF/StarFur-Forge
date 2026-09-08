import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_contracts import ToolProposal, build_core_tool_contract_registry
from pipeline.tool_grants import (
    SessionToolGrantController, ToolGrantError, ToolInvocationIssuer,
)
from pipeline.tool_permissions import evaluate_tool_permission


class MutableClock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value


def proposal(objective="Run tests."):
    return ToolProposal.from_mapping({
        "schema_version": 1,
        "tool_id": "sandbox.run",
        "tool_version": 1,
        "arguments": {
            "task_kind": "python_tests",
            "objective": objective,
            "files": [{"path": "main.py", "content": "print('ok')\n"}],
        },
    })


class ToolGrantTests(unittest.TestCase):
    def setUp(self):
        self.clock = MutableClock()
        self.invocation_ids = iter((f"TI-inv_{index}" for index in range(20)))
        self.grant_ids = iter((f"TG-grant_{index}" for index in range(20)))
        self.contracts = build_core_tool_contract_registry()
        self.issuer = ToolInvocationIssuer(
            self.contracts, clock=self.clock, id_factory=lambda: next(self.invocation_ids),
        )
        self.grants = SessionToolGrantController(
            clock=self.clock, id_factory=lambda: next(self.grant_ids),
        )

    def issue(self, **overrides):
        values = {
            "trusted_principal_id": "local.owner",
            "session_instance_id": "session-001",
            "persona_id": "murr",
            "adventure_id": None,
            "policy_revision": "policy-v1",
            "lifetime_seconds": 300,
        }
        values.update(overrides)
        return self.issuer.issue(proposal(), **values)

    def test_invocation_binds_exact_context_operation_resources_and_policy(self):
        invocation = self.issuer.issue(
            proposal(), trusted_principal_id="local.owner", session_instance_id="session-001",
            persona_id="murr", adventure_id="adventure:ember", policy_revision="policy-v1",
            resource_refs=("TR-source_1",), lifetime_seconds=300,
        )
        self.assertEqual("sandbox.run", invocation.tool_id)
        self.assertEqual(1, invocation.tool_version)
        self.assertEqual(("TR-source_1",), invocation.resource_refs)
        self.assertEqual("policy-v1", invocation.policy_revision)
        self.assertEqual(64, len(invocation.operation_digest))

    def test_grant_is_exact_finite_and_permission_evaluation_still_requires_confirmation(self):
        invocation = self.issue()
        grant = self.grants.issue(invocation, maximum_uses=1)
        permission = self.grants.claim(grant.grant_id, invocation)
        descriptor = self.contracts.get("sandbox.run", 1).descriptor

        self.assertEqual("confirmation_required", evaluate_tool_permission(
            descriptor, (permission,), confirmed=False,
        ).reason)
        self.assertTrue(evaluate_tool_permission(descriptor, (permission,), confirmed=True).allowed)
        with self.assertRaisesRegex(ToolGrantError, "exhausted"):
            self.grants.claim(grant.grant_id, invocation)

    def test_changed_session_persona_adventure_policy_or_arguments_fails_binding(self):
        original = self.issue(adventure_id="adventure:ember")
        grant = self.grants.issue(original)
        variants = (
            self.issue(trusted_principal_id="other.owner", adventure_id="adventure:ember"),
            self.issue(session_instance_id="session-002", adventure_id="adventure:ember"),
            self.issue(persona_id="nova", adventure_id="adventure:ember"),
            self.issue(adventure_id="adventure:other"),
            self.issue(adventure_id="adventure:ember", policy_revision="policy-v2"),
            self.issuer.issue(
                proposal(), trusted_principal_id="local.owner", session_instance_id="session-001",
                persona_id="murr", adventure_id="adventure:ember", policy_revision="policy-v1",
                resource_refs=("TR-other_resource",),
            ),
            self.issuer.issue(
                proposal("Changed operation."), trusted_principal_id="local.owner",
                session_instance_id="session-001", persona_id="murr",
                adventure_id="adventure:ember", policy_revision="policy-v1",
            ),
        )
        for variant in variants:
            with self.subTest(binding=variant.binding_tuple()), self.assertRaisesRegex(
                ToolGrantError, "does not match",
            ):
                self.grants.claim(grant.grant_id, variant)

    def test_expiry_revocation_session_recreation_and_invalid_booleans_fail_closed(self):
        invocation = self.issue(lifetime_seconds=100)
        grant = self.grants.issue(invocation, lifetime_seconds=50)
        self.clock.value += 50
        with self.assertRaisesRegex(ToolGrantError, "expired"):
            self.grants.claim(grant.grant_id, invocation)

        self.clock.value = 2000
        current = self.issue(session_instance_id="server-instance-a")
        current_grant = self.grants.issue(current)
        self.assertEqual(1, self.grants.revoke_session(
            principal_id="local.owner", session_instance_id="server-instance-a",
        ))
        with self.assertRaisesRegex(ToolGrantError, "revoked"):
            self.grants.claim(current_grant.grant_id, current)

        old_instance = self.issue(session_instance_id="server-instance-a2")
        old_instance_grant = self.grants.issue(old_instance)
        recreated = self.issue(session_instance_id="server-instance-b")
        with self.assertRaisesRegex(ToolGrantError, "does not match"):
            self.grants.claim(old_instance_grant.grant_id, recreated)
        with self.assertRaisesRegex(ToolGrantError, "use limit"):
            self.grants.issue(recreated, maximum_uses=True)


if __name__ == "__main__":
    unittest.main()
