import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_brief import build_research_cited_brief
from pipeline.research_coordinator import ResearchClaimCoordinator
from pipeline.research_disclosure import ResearchDisclosureIntent, ResearchProviderTarget, evaluate_research_disclosure
from pipeline.research_review import SessionResearchReviewStore
from pipeline.research_sources import build_research_source_packet, research_source_from_web_artifact
from pipeline.tool_web_connector import WebFetchedArtifact
from pipeline.tool_web_parser import QuarantinedWebText
from pipeline.tool_web_policy import WebDestination


def review_record(*, empty=False):
    text = "Public fact."
    digest = hashlib.sha256(text.encode()).hexdigest()
    artifact = WebFetchedArtifact(
        1, "a" * 64, WebDestination(1, "https://example.com/fact"), "93.184.216.34", 100.0,
        "b" * 64, "c" * 64,
        QuarantinedWebText(1, "text/plain", "untrusted_external", text, len(text), digest, digest),
    )
    packet = build_research_source_packet("Question?", [research_source_from_web_artifact("TF-a", artifact)])
    target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
    decision = evaluate_research_disclosure(ResearchDisclosureIntent.from_packet(packet, target), packet)

    class Provider:
        available = True

        def propose_claims(self, _messages, *, model, schema):
            return json.dumps({
                "schema_version": 1,
                "packet_sha256": packet.packet_sha256,
                "claims": [] if empty else [{
                    "claim_id": "RC-001", "statement": "Public fact.",
                    "source_ids": [packet.source_ids()[0]], "confidence": 0.8,
                }],
            })

    result = ResearchClaimCoordinator(Provider()).propose(packet, target, decision)
    return SessionResearchReviewStore(id_factory=lambda: "RR-" + "2" * 24).create(packet, result)


class ResearchBriefTests(unittest.TestCase):
    def test_brief_projects_only_reviewed_cited_claims_and_public_urls(self):
        brief = build_research_cited_brief(review_record())
        self.assertEqual("claims_available", brief.status)
        self.assertEqual("Public fact.", brief.claims[0].statement)
        self.assertEqual("https://example.com/fact", brief.claims[0].citations[0].url)
        self.assertEqual(100.0, brief.claims[0].citations[0].fetched_at_epoch)
        self.assertEqual("single_source", brief.claims[0].citation_diversity)
        self.assertFalse(hasattr(brief, "answer"))
        self.assertFalse(hasattr(brief, "verified"))

    def test_empty_review_becomes_no_supported_claims_brief(self):
        brief = build_research_cited_brief(review_record(empty=True))
        self.assertEqual("no_supported_claims", brief.status)
        self.assertEqual((), brief.claims)


if __name__ == "__main__":
    unittest.main()
