from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.factual_research_policy import classify_factual_research_request
from pipeline.research_discovery import ResearchDiscoveryIntent, evaluate_research_discovery
from pipeline.sandbox_supervisor import SupervisorLaunchRequest, SupervisorPrerequisiteBinding
from pipeline.tool_contracts import ToolProposal, build_core_tool_contract_registry
from pipeline.tool_grants import ToolInvocationIssuer
from pipeline.tool_web_search_preflight import (
    WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
    WebSearchDisclosurePrerequisite,
    WebSearchServicePrerequisite,
    evaluate_web_search_preflight,
)


QUERY = "Please research the current RTX 4070 price."


def make_inputs(*, available=True, expires=180.0):
    factual = classify_factual_research_request(QUERY)
    intent = ResearchDiscoveryIntent.from_request(
        QUERY, factual, target_kind="public_web_search", data_classification="public",
    )
    discovery = evaluate_research_discovery(intent, QUERY, factual)
    service = WebSearchServicePrerequisite(
        1, "TR-search_service", "fixture.search", "hosted", 5, available,
        100.0, expires, WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
    )
    disclosure = WebSearchDisclosurePrerequisite(
        1, "TR-search_disclosure", intent, discovery,
    )
    proposal = ToolProposal.from_mapping({
        "schema_version": 1,
        "tool_id": "web.search",
        "tool_version": 1,
        "arguments": {"query": QUERY},
    })
    contracts = build_core_tool_contract_registry()
    invocation = ToolInvocationIssuer(contracts, clock=lambda: 100.0).issue(
        proposal,
        invocation_id="TI-search_preflight",
        trusted_principal_id="local.owner",
        session_instance_id="session-001",
        persona_id="murr",
        adventure_id=None,
        policy_revision="policy-v1",
        resource_refs=("TR-search_service", "TR-search_disclosure"),
    )
    launch = SupervisorLaunchRequest.from_invocation(
        invocation,
        worker_generation="TW-search-preflight",
        issued_at=101.0,
        authorization_deadline=150.0,
        prerequisite_bindings=(
            SupervisorPrerequisiteBinding(
                "network.search", service.resource_ref, service.evidence_sha256,
            ),
            SupervisorPrerequisiteBinding(
                "network.disclosure", disclosure.resource_ref, disclosure.evidence_sha256,
            ),
        ),
    )
    return launch, proposal, service, disclosure


class WebSearchPreflightTests(unittest.TestCase):
    def test_exact_fresh_public_query_is_permitted_without_executing(self):
        decision = evaluate_web_search_preflight(*make_inputs(), now_epoch=120.0)
        self.assertTrue(decision.permitted)
        self.assertEqual("fixture.search", decision.service_id)
        self.assertEqual(5, decision.maximum_results)
        self.assertFalse(hasattr(decision, "query"))
        self.assertFalse(hasattr(decision, "authorized"))

    def test_changed_query_or_prerequisite_binding_denies(self):
        launch, proposal, service, disclosure = make_inputs()
        changed = ToolProposal(1, "web.search", 1, {"query": "different query"})
        self.assertEqual(
            "query_binding_invalid",
            evaluate_web_search_preflight(
                launch, changed, service, disclosure, now_epoch=120.0,
            ).reason,
        )
        altered = replace(service, service_id="other.search")
        self.assertEqual(
            "service_binding_invalid",
            evaluate_web_search_preflight(
                launch, proposal, altered, disclosure, now_epoch=120.0,
            ).reason,
        )

    def test_unavailable_or_stale_service_denies(self):
        values = make_inputs(available=False)
        self.assertEqual(
            "service_unavailable",
            evaluate_web_search_preflight(*values, now_epoch=120.0).reason,
        )
        stale = make_inputs(expires=110.0)
        self.assertEqual(
            "service_evidence_stale",
            evaluate_web_search_preflight(*stale, now_epoch=120.0).reason,
        )

    def test_missing_or_altered_disclosure_commitment_denies(self):
        launch, proposal, service, disclosure = make_inputs()
        incomplete = replace(launch, prerequisite_bindings=(launch.prerequisite_bindings[0],))
        self.assertEqual(
            "launch_binding_invalid",
            evaluate_web_search_preflight(
                incomplete, proposal, service, disclosure, now_epoch=120.0,
            ).reason,
        )
        altered = replace(disclosure, resource_ref="TR-other_disclosure")
        self.assertEqual(
            "disclosure_binding_invalid",
            evaluate_web_search_preflight(
                launch, proposal, service, altered, now_epoch=120.0,
            ).reason,
        )


if __name__ == "__main__":
    unittest.main()
