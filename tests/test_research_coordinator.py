import hashlib
import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_coordinator import ResearchClaimCoordinator, ResearchCoordinatorError
from pipeline.providers import ChatProviderOutputLimitError
from pipeline.research_disclosure import (
    ResearchDisclosureIntent,
    ResearchProviderTarget,
    evaluate_research_disclosure,
)
from pipeline.research_sources import build_research_source_packet, research_source_from_web_artifact
from pipeline.tool_web_connector import WebFetchedArtifact
from pipeline.tool_web_parser import QuarantinedWebText
from pipeline.tool_web_policy import WebDestination


def inputs(deployment="local"):
    text = "The public value is 42."
    digest = hashlib.sha256(text.encode()).hexdigest()
    artifact = WebFetchedArtifact(
        1, "a" * 64, WebDestination(1, "https://example.com/fact"),
        "93.184.216.34", 100.0, "b" * 64, "c" * 64,
        QuarantinedWebText(1, "text/plain", "untrusted_external", text, len(text), digest, digest),
    )
    source = research_source_from_web_artifact("TF-fact_1", artifact)
    packet = build_research_source_packet("What is the public value?", [source])
    target = ResearchProviderTarget.create("ollama", "qwen3:8b", deployment)
    decision = evaluate_research_disclosure(
        ResearchDisclosureIntent.from_packet(packet, target), packet,
    )
    return packet, target, decision


class _Provider:
    available = True

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def propose_claims(self, messages, *, model, schema):
        self.calls.append((messages, model, schema))
        if self.error:
            raise self.error
        return self.response


class ResearchCoordinatorTests(unittest.TestCase):
    def test_reported_output_limit_stays_distinct_and_nonpublishing(self):
        packet, target, decision = inputs()
        provider = _Provider(error=ChatProviderOutputLimitError())
        with self.assertRaises(ResearchCoordinatorError) as caught:
            ResearchClaimCoordinator(provider).propose(packet, target, decision)
        self.assertEqual("provider_output_limit", caught.exception.reason)
        self.assertEqual(1, len(provider.calls))

    def test_valid_cited_claim_is_nonpublishing_result(self):
        packet, target, decision = inputs()
        provider = _Provider(json.dumps({
            "schema_version": 1,
            "packet_sha256": packet.packet_sha256,
            "claims": [{
                "claim_id": "RC-001",
                "statement": "The public value is 42.",
                "source_ids": [packet.source_ids()[0]],
                "confidence": 0.9,
            }],
        }))
        result = ResearchClaimCoordinator(provider).propose(packet, target, decision)
        self.assertEqual("claims_proposed", result.status)
        self.assertEqual("qwen3:8b", provider.calls[0][1])
        self.assertEqual(packet.packet_sha256, provider.calls[0][2]["properties"]["packet_sha256"]["const"])
        self.assertEqual(list(packet.source_ids()), provider.calls[0][2]["properties"]["claims"]["items"]["properties"]["source_ids"]["items"]["enum"])
        self.assertFalse(hasattr(result, "answer"))
        self.assertFalse(hasattr(result, "memory"))

    def test_empty_claim_set_is_transparent_no_support(self):
        packet, target, decision = inputs()
        provider = _Provider(json.dumps({
            "schema_version": 1,
            "packet_sha256": packet.packet_sha256,
            "claims": [],
        }))
        result = ResearchClaimCoordinator(provider).propose(packet, target, decision)
        self.assertEqual("no_supported_claims", result.status)

    def test_denied_disclosure_never_calls_provider(self):
        packet, target, decision = inputs("hosted")
        provider = _Provider("unused")
        with self.assertRaisesRegex(ResearchCoordinatorError, "failed safely") as caught:
            ResearchClaimCoordinator(provider).propose(packet, target, decision)
        self.assertEqual("disclosure_denied", caught.exception.reason)
        self.assertEqual([], provider.calls)

    def test_unavailable_failure_and_invalid_output_are_bounded(self):
        packet, target, decision = inputs()
        unavailable = _Provider("unused")
        unavailable.available = False
        with self.assertRaises(ResearchCoordinatorError) as caught:
            ResearchClaimCoordinator(unavailable).propose(packet, target, decision)
        self.assertEqual("provider_unavailable", caught.exception.reason)

        failing = _Provider(error=RuntimeError("private provider detail"))
        with self.assertRaises(ResearchCoordinatorError) as caught:
            ResearchClaimCoordinator(failing).propose(packet, target, decision)
        self.assertEqual("provider_failed", caught.exception.reason)
        self.assertNotIn("private provider detail", str(caught.exception))

        invalid = _Provider("not json")
        with self.assertRaises(ResearchCoordinatorError) as caught:
            ResearchClaimCoordinator(invalid).propose(packet, target, decision)
        self.assertEqual("response_invalid", caught.exception.reason)

    def test_wrong_adapter_shape_rejects_at_construction(self):
        with self.assertRaisesRegex(TypeError, "provider is invalid"):
            ResearchClaimCoordinator(object())


if __name__ == "__main__":
    unittest.main()
