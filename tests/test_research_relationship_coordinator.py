import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_claims import ResearchClaim, ResearchClaimSet
from pipeline.research_coordinator import ResearchCoordinationResult
from pipeline.research_disclosure import ResearchProviderTarget
from pipeline.research_relationship_coordinator import (
    ResearchRelationshipCoordinator,
    ResearchRelationshipCoordinatorError,
)
from pipeline.research_relationship_disclosure import (
    ResearchRelationshipDisclosureIntent,
    evaluate_research_relationship_disclosure,
)
from pipeline.research_review import SessionResearchReviewStore
from pipeline.research_sources import build_research_source_packet, research_source_from_web_artifact
from pipeline.tool_web_connector import WebFetchedArtifact
from pipeline.tool_web_parser import QuarantinedWebText
from pipeline.tool_web_policy import WebDestination


def _source(ref, url, text):
    digest = hashlib.sha256(text.encode()).hexdigest()
    artifact = WebFetchedArtifact(
        1, "a" * 64, WebDestination(1, url), "93.184.216.34", 100.0,
        "b" * 64, "c" * 64,
        QuarantinedWebText(1, "text/plain", "untrusted_external", text, len(text), digest, digest),
    )
    return research_source_from_web_artifact(ref, artifact)


def _inputs():
    first = _source("TF-one", "https://one.example/fact", "The value is 42.")
    second = _source("TF-two", "https://two.example/fact", "The value is 43.")
    packet = build_research_source_packet("What is the value?", (first, second))
    claims = ResearchClaimSet(1, packet.packet_sha256, (
        ResearchClaim(1, "RC-001", "The value is 42.", (first.source_id,), 0.9),
        ResearchClaim(1, "RC-002", "The value is 43.", (second.source_id,), 0.8),
    ))
    result = ResearchCoordinationResult(1, packet.packet_sha256, "d" * 64, "claims_proposed", claims)
    review = SessionResearchReviewStore(
        clock=lambda: 101.0,
        id_factory=lambda: "RR-" + "4" * 24,
    ).create(packet, result)
    target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
    decision = evaluate_research_relationship_disclosure(
        ResearchRelationshipDisclosureIntent.from_review(review, target), review,
    )
    return review, target, decision


class Provider:
    def __init__(self, review, *, available=True, raw=None, fail=False):
        self.available = available
        self.review = review
        self.raw = raw
        self.fail = fail
        self.calls = []

    def propose_relationships(self, messages, *, model, schema):
        self.calls.append((messages, model, schema))
        if self.fail:
            raise RuntimeError("provider failure")
        if self.raw is not None:
            return self.raw
        return json.dumps({
            "schema_version": 1,
            "review_id": self.review.review_id,
            "packet_sha256": self.review.packet_sha256,
            "relationships": [{
                "relationship_id": "RL-001",
                "left_claim_id": "RC-001",
                "right_claim_id": "RC-002",
                "relation": "possibly_conflicts",
                "confidence": 0.8,
            }],
        })


class ResearchRelationshipCoordinatorTests(unittest.TestCase):
    def test_one_injected_attempt_returns_untrusted_bound_proposals(self):
        review, target, decision = _inputs()
        provider = Provider(review)

        result = ResearchRelationshipCoordinator(provider).propose(review, target, decision)

        self.assertEqual("relationships_proposed", result.status)
        self.assertEqual("possibly_conflicts", result.relationships.relationships[0].relation)
        self.assertEqual(1, len(provider.calls))
        self.assertEqual(target.model, provider.calls[0][1])
        self.assertEqual(review.review_id, provider.calls[0][2]["properties"]["review_id"]["const"])
        self.assertFalse(hasattr(result, "verified"))
        self.assertFalse(hasattr(result, "answer"))

    def test_empty_response_is_explicitly_nonpublishing(self):
        review, target, decision = _inputs()
        raw = json.dumps({
            "schema_version": 1,
            "review_id": review.review_id,
            "packet_sha256": review.packet_sha256,
            "relationships": [],
        })
        result = ResearchRelationshipCoordinator(Provider(review, raw=raw)).propose(
            review, target, decision,
        )
        self.assertEqual("no_relationships", result.status)

    def test_denied_disclosure_and_unavailable_provider_fail_before_or_at_call(self):
        review, target, decision = _inputs()
        hosted = ResearchProviderTarget.create("hosted", "model-v1", "hosted")
        hosted_decision = evaluate_research_relationship_disclosure(
            ResearchRelationshipDisclosureIntent.from_review(review, hosted), review,
        )
        provider = Provider(review)
        with self.assertRaises(ResearchRelationshipCoordinatorError) as denied:
            ResearchRelationshipCoordinator(provider).propose(review, hosted, hosted_decision)
        self.assertEqual("disclosure_denied", denied.exception.reason)
        self.assertEqual([], provider.calls)

        with self.assertRaises(ResearchRelationshipCoordinatorError) as unavailable:
            ResearchRelationshipCoordinator(Provider(review, available=False)).propose(
                review, target, decision,
            )
        self.assertEqual("provider_unavailable", unavailable.exception.reason)

    def test_provider_failure_or_invalid_response_is_bounded(self):
        review, target, decision = _inputs()
        with self.assertRaises(ResearchRelationshipCoordinatorError) as failed:
            ResearchRelationshipCoordinator(Provider(review, fail=True)).propose(
                review, target, decision,
            )
        self.assertEqual("provider_failed", failed.exception.reason)

        with self.assertRaises(ResearchRelationshipCoordinatorError) as invalid:
            ResearchRelationshipCoordinator(Provider(review, raw="not json")).propose(
                review, target, decision,
            )
        self.assertEqual("response_invalid", invalid.exception.reason)


if __name__ == "__main__":
    unittest.main()
