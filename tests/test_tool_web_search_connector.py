import hashlib
import unittest
from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.factual_research_policy import classify_factual_research_request
from pipeline.research_discovery import ResearchDiscoveryIntent, evaluate_research_discovery
from pipeline.sandbox_supervisor import (
    SupervisorCancellation, SupervisorLaunchRequest, SupervisorPrerequisiteBinding,
)
from pipeline.tool_contracts import ToolProposal, build_core_tool_contract_registry
from pipeline.tool_grants import ToolInvocationIssuer
from pipeline.tool_web_search import WebSearchCandidate
from pipeline.tool_web_search_connector import (
    DisabledWebSearchSupervisor, WebSearchResponse, WebSearchSupervisor,
)
from pipeline.tool_web_search_preflight import (
    WEB_SEARCH_PREFLIGHT_POLICY_REVISION, WebSearchDisclosurePrerequisite,
    WebSearchServicePrerequisite,
)


def setup_values():
    query = "Please research the current public reference."
    factual = classify_factual_research_request(query)
    intent = ResearchDiscoveryIntent.from_request(
        query, factual,
        target_kind="public_web_search", data_classification="public",
    )
    disclosure = WebSearchDisclosurePrerequisite(
        1, "TR-search_disclosure", intent,
        evaluate_research_discovery(intent, query, factual),
    )
    service = WebSearchServicePrerequisite(
        1, "TR-search_service", "fixture.search", "local", 5, True,
        100.0, 150.0, WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
    )
    proposal = ToolProposal.from_mapping({
        "schema_version": 1, "tool_id": "web.search", "tool_version": 1,
        "arguments": {"query": query},
    })
    invocation = ToolInvocationIssuer(
        build_core_tool_contract_registry(), clock=lambda: 100.0,
    ).issue(
        proposal, invocation_id="TI-web_search_connector",
        trusted_principal_id="local.owner", session_instance_id="session-001",
        persona_id="murr", adventure_id=None, policy_revision="policy-v1",
        resource_refs=(service.resource_ref, disclosure.resource_ref),
    )
    launch = SupervisorLaunchRequest.from_invocation(
        invocation, worker_generation="TW-web-search-connector",
        issued_at=101.0, authorization_deadline=140.0,
        prerequisite_bindings=(
            SupervisorPrerequisiteBinding(
                "network.search", service.resource_ref, service.evidence_sha256,
            ),
            SupervisorPrerequisiteBinding(
                "network.disclosure", disclosure.resource_ref, disclosure.evidence_sha256,
            ),
        ),
    )
    return proposal, invocation, launch, service, disclosure


class FakePrerequisites:
    available = True

    def __init__(self, service, disclosure):
        self.service = service
        self.disclosure = disclosure

    def service_for(self, ref):
        if ref != self.service.resource_ref:
            raise KeyError(ref)
        return self.service

    def disclosure_for(self, ref):
        if ref != self.disclosure.resource_ref:
            raise KeyError(ref)
        return self.disclosure


class FakeAdapter:
    available = True
    service_id = "fixture.search"

    def __init__(self, *, error=None, mutator=None):
        self.error = error
        self.mutator = mutator
        self.calls = []
        self.cancelled = []

    def search(self, request, cancellation):
        self.calls.append(request)
        if self.error:
            raise self.error
        response = WebSearchResponse(
            1, request.invocation_id, request.binding_fingerprint,
            request.worker_generation, request.service_id, request.query_sha256,
            (
                WebSearchCandidate(1, "https://example.com/one", "First result"),
                WebSearchCandidate(2, "https://example.org/two", "Second result"),
            ),
        )
        return self.mutator(response) if self.mutator else response

    def request_cancel(self, request):
        self.cancelled.append(request)


class FakeQuarantine:
    available = True

    def __init__(self, reference="TF-search_fixture", error=None):
        self.reference = reference
        self.error = error
        self.items = []

    def store(self, artifact):
        if self.error:
            raise self.error
        self.items.append(artifact)
        return self.reference


def make_supervisor(*, adapter=None, quarantine=None):
    proposal, invocation, launch, service, disclosure = setup_values()
    return (
        WebSearchSupervisor(
            FakePrerequisites(service, disclosure), adapter or FakeAdapter(),
            quarantine or FakeQuarantine(), clock=lambda: 120.0,
        ), proposal, invocation, launch,
    )


class WebSearchConnectorTests(unittest.TestCase):
    def test_fake_search_returns_reference_and_quarantines_candidates(self):
        quarantine = FakeQuarantine()
        worker, proposal, invocation, launch = make_supervisor(quarantine=quarantine)
        completion = worker.run(launch, invocation, proposal, SupervisorCancellation())
        self.assertEqual("completed", completion.outcome)
        self.assertEqual(("TF-search_fixture",), completion.result.artifact_refs)
        self.assertEqual(("", ""), (completion.result.stdout, completion.result.stderr))
        artifact = quarantine.items[0]
        self.assertEqual("untrusted_discovery", artifact.trust_label)
        self.assertEqual("fixture.search", artifact.service_id)
        self.assertEqual(2, len(artifact.results))
        self.assertFalse(hasattr(artifact, "query"))
        self.assertEqual(
            hashlib.sha256("Please research the current public reference.".encode()).hexdigest(),
            artifact.query_sha256,
        )

    def test_adapter_receives_exact_preflight_limit_and_binding(self):
        adapter = FakeAdapter()
        worker, proposal, invocation, launch = make_supervisor(adapter=adapter)
        self.assertEqual(
            "completed",
            worker.run(launch, invocation, proposal, SupervisorCancellation()).outcome,
        )
        request = adapter.calls[0]
        self.assertEqual(("fixture.search", 5), (request.service_id, request.maximum_results))
        self.assertEqual(launch.binding_fingerprint, request.binding_fingerprint)

    def test_service_or_response_mismatch_denies_without_quarantine(self):
        proposal, invocation, launch, service, disclosure = setup_values()
        adapter = FakeAdapter()
        adapter.service_id = "other.search"
        quarantine = FakeQuarantine()
        worker = WebSearchSupervisor(
            FakePrerequisites(service, disclosure), adapter, quarantine,
            clock=lambda: 120.0,
        )
        completion = worker.run(launch, invocation, proposal, SupervisorCancellation())
        self.assertEqual("permission_denied", completion.result.error_category)
        self.assertEqual([], adapter.calls)

        adapter = FakeAdapter(mutator=lambda value: replace(value, query_sha256="0" * 64))
        worker, proposal, invocation, launch = make_supervisor(
            adapter=adapter, quarantine=quarantine,
        )
        completion = worker.run(launch, invocation, proposal, SupervisorCancellation())
        self.assertEqual("failed", completion.outcome)
        self.assertEqual([], quarantine.items)

    def test_adapter_or_quarantine_exception_is_uncertain_and_redacted(self):
        worker, proposal, invocation, launch = make_supervisor(
            adapter=FakeAdapter(error=RuntimeError("private provider detail")),
        )
        completion = worker.run(launch, invocation, proposal, SupervisorCancellation())
        self.assertEqual(("outcome_unknown", "not_verified"), (
            completion.outcome, completion.stop_state,
        ))
        self.assertNotIn("private provider detail", repr(completion.public_dict()))

        worker, proposal, invocation, launch = make_supervisor(
            quarantine=FakeQuarantine(error=RuntimeError("private storage detail")),
        )
        completion = worker.run(launch, invocation, proposal, SupervisorCancellation())
        self.assertEqual("outcome_unknown", completion.outcome)

    def test_cancel_before_adapter_makes_no_search(self):
        adapter = FakeAdapter()
        worker, proposal, invocation, launch = make_supervisor(adapter=adapter)
        cancellation = SupervisorCancellation()
        cancellation.request()
        completion = worker.run(launch, invocation, proposal, cancellation)
        self.assertEqual("cancelled", completion.outcome)
        self.assertEqual([], adapter.calls)

    def test_stale_prerequisite_denies_before_adapter(self):
        proposal, invocation, launch, service, disclosure = setup_values()
        service = replace(service, expires_at_epoch=110.0)
        adapter = FakeAdapter()
        worker = WebSearchSupervisor(
            FakePrerequisites(service, disclosure), adapter, FakeQuarantine(),
            clock=lambda: 120.0,
        )
        completion = worker.run(launch, invocation, proposal, SupervisorCancellation())
        self.assertEqual("permission_denied", completion.result.error_category)
        self.assertEqual([], adapter.calls)

    def test_disabled_default_denies_exact_operation(self):
        disabled = DisabledWebSearchSupervisor()
        self.assertFalse(disabled.available)
        self.assertFalse(disabled.supports("web.search", 1))


if __name__ == "__main__":
    unittest.main()
