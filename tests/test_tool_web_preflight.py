import hashlib
import socket
import unittest
from pathlib import Path
from unittest.mock import patch
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_supervisor import (
    SupervisorLaunchRequest,
    SupervisorPrerequisiteBinding,
)
from pipeline.tool_contracts import ToolProposal, build_core_tool_contract_registry
from pipeline.tool_grants import ToolInvocationIssuer
from pipeline.tool_web_disclosure import WebDisclosureIntent
from pipeline.tool_web_policy import WebDestination, WebResolutionEvidence
from pipeline.tool_web_preflight import (
    WebDestinationPrerequisite,
    WebDisclosurePrerequisite,
    evaluate_web_fetch_preflight,
)


def make_inputs(*, classification="public", source_kind="user_supplied"):
    destination = WebDestination(1, "https://example.com/reference")
    resolution = WebResolutionEvidence(
        1, "example.com", 443, ("93.184.216.34",), "resolver-v1", 100.0, 200.0,
    )
    destination_evidence = WebDestinationPrerequisite(
        1, "TR-web_destination", destination, resolution,
    )
    encoded = destination.url.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    disclosure_evidence = WebDisclosurePrerequisite(
        1,
        "TR-web_disclosure",
        digest,
        WebDisclosureIntent(1, classification, source_kind, len(encoded), digest),
    )
    proposal = ToolProposal.from_mapping({
        "schema_version": 1, "tool_id": "web.fetch", "tool_version": 1,
        "arguments": {"url": destination.url},
    })
    contracts = build_core_tool_contract_registry()
    invocation = ToolInvocationIssuer(contracts, clock=lambda: 100.0).issue(
        proposal, invocation_id="TI-web_preflight",
        trusted_principal_id="local.owner", session_instance_id="session-001",
        persona_id="murr", adventure_id=None, policy_revision="policy-v1",
        resource_refs=("TR-web_destination", "TR-web_disclosure"),
    )
    launch = SupervisorLaunchRequest.from_invocation(
        invocation, worker_generation="TW-web-preflight",
        issued_at=101.0, authorization_deadline=150.0,
        prerequisite_bindings=(
            SupervisorPrerequisiteBinding(
                "network.destination", "TR-web_destination",
                destination_evidence.evidence_sha256,
            ),
            SupervisorPrerequisiteBinding(
                "network.disclosure", "TR-web_disclosure",
                disclosure_evidence.evidence_sha256,
            ),
        ),
    )
    return launch, destination, destination_evidence, disclosure_evidence


class WebFetchPreflightTests(unittest.TestCase):
    def test_exact_public_destination_and_disclosure_are_permitted_without_io(self):
        values = make_inputs()
        with patch.object(socket, "getaddrinfo", side_effect=AssertionError("must not resolve")):
            decision = evaluate_web_fetch_preflight(*values, now_epoch=120.0)
        self.assertTrue(decision.permitted)
        self.assertEqual(("93.184.216.34",), decision.approved_addresses)

    def test_changed_destination_or_commitment_fails_closed(self):
        launch, destination, destination_evidence, disclosure_evidence = make_inputs()
        changed = WebDestination(1, "https://example.com/other")
        self.assertEqual(
            "destination_binding_invalid",
            evaluate_web_fetch_preflight(
                launch, changed, destination_evidence, disclosure_evidence, now_epoch=120.0,
            ).reason,
        )
        altered_launch = SupervisorLaunchRequest.from_invocation(
            ToolInvocationIssuer(
                build_core_tool_contract_registry(), clock=lambda: 100.0,
            ).issue(
                ToolProposal.from_mapping({
                    "schema_version": 1, "tool_id": "web.fetch", "tool_version": 1,
                    "arguments": {"url": destination.url},
                }),
                invocation_id="TI-web_preflight", trusted_principal_id="local.owner",
                session_instance_id="session-001", persona_id="murr", adventure_id=None,
                policy_revision="policy-v1",
                resource_refs=("TR-web_destination", "TR-web_disclosure"),
            ),
            worker_generation="TW-web-preflight-2", issued_at=101.0,
            authorization_deadline=150.0,
            prerequisite_bindings=(
                SupervisorPrerequisiteBinding(
                    "network.destination", "TR-web_destination", "f" * 64,
                ),
                launch.prerequisite_bindings[1],
            ),
        )
        self.assertEqual(
            "destination_binding_invalid",
            evaluate_web_fetch_preflight(
                altered_launch, destination, destination_evidence,
                disclosure_evidence, now_epoch=120.0,
            ).reason,
        )

    def test_private_disclosure_and_stale_resolution_are_denied(self):
        private_values = make_inputs(classification="private", source_kind="private_resource")
        self.assertEqual(
            "disclosure_denied",
            evaluate_web_fetch_preflight(*private_values, now_epoch=120.0).reason,
        )
        public_values = make_inputs()
        self.assertEqual(
            "destination_denied",
            evaluate_web_fetch_preflight(*public_values, now_epoch=200.0).reason,
        )

    def test_missing_exact_requirement_commitment_is_denied(self):
        launch, destination, destination_evidence, disclosure_evidence = make_inputs()
        incomplete = SupervisorLaunchRequest.from_invocation(
            ToolInvocationIssuer(
                build_core_tool_contract_registry(), clock=lambda: 100.0,
            ).issue(
                ToolProposal.from_mapping({
                    "schema_version": 1, "tool_id": "web.fetch", "tool_version": 1,
                    "arguments": {"url": destination.url},
                }),
                invocation_id="TI-web_preflight", trusted_principal_id="local.owner",
                session_instance_id="session-001", persona_id="murr", adventure_id=None,
                policy_revision="policy-v1",
                resource_refs=("TR-web_destination", "TR-web_disclosure"),
            ),
            worker_generation="TW-web-preflight-3", issued_at=101.0,
            authorization_deadline=150.0,
            prerequisite_bindings=(launch.prerequisite_bindings[0],),
        )
        self.assertEqual(
            "launch_binding_invalid",
            evaluate_web_fetch_preflight(
                incomplete, destination, destination_evidence,
                disclosure_evidence, now_epoch=120.0,
            ).reason,
        )


if __name__ == "__main__":
    unittest.main()
