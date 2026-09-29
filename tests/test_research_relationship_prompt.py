import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_claims import ResearchClaim, ResearchClaimSet
from pipeline.research_coordinator import ResearchCoordinationResult
from pipeline.research_disclosure import ResearchProviderTarget
from pipeline.research_relationship_disclosure import (
    ResearchRelationshipDisclosureIntent,
    evaluate_research_relationship_disclosure,
)
from pipeline.research_relationship_prompt import build_research_relationship_messages
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


def _review(*, claim_count=2):
    first = _source("TF-one", "https://one.example/fact", "The value is 42.")
    second = _source("TF-two", "https://two.example/fact", "The value is 43.")
    packet = build_research_source_packet("What is the value?", (first, second))
    claims = (
        ResearchClaim(1, "RC-001", "The value is 42.", (first.source_id,), 0.9),
        ResearchClaim(1, "RC-002", "The value is 43.", (second.source_id,), 0.8),
    )[:claim_count]
    claim_set = ResearchClaimSet(1, packet.packet_sha256, claims)
    result = ResearchCoordinationResult(1, packet.packet_sha256, "d" * 64, "claims_proposed", claim_set)
    return SessionResearchReviewStore(
        clock=lambda: 101.0,
        id_factory=lambda: "RR-" + "2" * 24,
    ).create(packet, result)


class ResearchRelationshipPromptTests(unittest.TestCase):
    def test_exact_local_review_metadata_is_permitted_and_framed_as_untrusted(self):
        review = _review()
        target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
        intent = ResearchRelationshipDisclosureIntent.from_review(review, target)
        decision = evaluate_research_relationship_disclosure(intent, review)

        self.assertEqual("permitted", decision.status)
        system, user = build_research_relationship_messages(review, target, decision)
        self.assertIn("untrusted DATA", system["content"])
        self.assertIn("not verification", system["content"])
        self.assertIn("possibly_conflicts", system["content"])
        self.assertIn(review.review_id, user["content"])
        self.assertIn("The value is 42.", user["content"])
        self.assertIn("untrusted_review_metadata_only", user["content"])
        for forbidden in ("93.184.216.34", "TF-one", "fetched_at_epoch", "confidence"):
            self.assertNotIn(forbidden, user["content"])

    def test_hosted_insufficient_and_stale_review_disclosure_are_denied(self):
        review = _review()
        hosted = ResearchProviderTarget.create("hosted", "model-v1", "hosted")
        hosted_intent = ResearchRelationshipDisclosureIntent.from_review(review, hosted)
        hosted_decision = evaluate_research_relationship_disclosure(hosted_intent, review)
        self.assertEqual("hosted_disclosure_unsupported", hosted_decision.reason)
        with self.assertRaisesRegex(ValueError, "not permitted"):
            build_research_relationship_messages(review, hosted, hosted_decision)

        one_claim = _review(claim_count=1)
        local = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
        one_intent = ResearchRelationshipDisclosureIntent.from_review(one_claim, local)
        self.assertEqual(
            "insufficient_claims",
            evaluate_research_relationship_disclosure(one_intent, one_claim).reason,
        )

        intent = ResearchRelationshipDisclosureIntent.from_review(review, local)
        stale = type(intent)(
            1, "RR-" + "3" * 24, intent.packet_sha256, intent.claim_count,
            intent.source_count, intent.review_character_count,
            intent.data_classification, intent.purpose, local, intent.policy_revision,
        )
        self.assertEqual(
            "review_binding_mismatch",
            evaluate_research_relationship_disclosure(stale, review).reason,
        )

    def test_tampered_counts_or_target_cannot_render(self):
        review = _review()
        target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
        intent = ResearchRelationshipDisclosureIntent.from_review(review, target)
        changed = type(intent)(
            1, intent.review_id, intent.packet_sha256, intent.claim_count,
            intent.source_count, intent.review_character_count - 1,
            intent.data_classification, intent.purpose, target, intent.policy_revision,
        )
        decision = evaluate_research_relationship_disclosure(changed, review)
        self.assertEqual("intent_mismatch", decision.reason)

        permitted = evaluate_research_relationship_disclosure(intent, review)
        other = ResearchProviderTarget.create("ollama", "other-model", "local")
        with self.assertRaisesRegex(ValueError, "not permitted"):
            build_research_relationship_messages(review, other, permitted)


if __name__ == "__main__":
    unittest.main()
