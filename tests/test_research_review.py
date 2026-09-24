import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_coordinator import ResearchClaimCoordinator
from pipeline.research_disclosure import (
    ResearchDisclosureIntent,
    ResearchProviderTarget,
    evaluate_research_disclosure,
)
from pipeline.research_review import MAX_SESSION_RESEARCH_REVIEWS, SessionResearchReviewStore
from pipeline.research_sources import build_research_source_packet, research_source_from_web_artifact
from pipeline.tool_web_connector import WebFetchedArtifact
from pipeline.tool_web_parser import QuarantinedWebText
from pipeline.tool_web_policy import WebDestination


def packet_and_result():
    text = "The public value is 42."
    digest = hashlib.sha256(text.encode()).hexdigest()
    artifact = WebFetchedArtifact(
        1, "a" * 64, WebDestination(1, "https://example.com/fact"),
        "93.184.216.34", 100.0, "b" * 64, "c" * 64,
        QuarantinedWebText(1, "text/plain", "untrusted_external", text, len(text), digest, digest),
    )
    packet = build_research_source_packet(
        "What is the public value?", [research_source_from_web_artifact("TF-fact_1", artifact)],
    )
    target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
    decision = evaluate_research_disclosure(ResearchDisclosureIntent.from_packet(packet, target), packet)

    class Provider:
        available = True

        def propose_claims(self, _messages, *, model, schema):
            return json.dumps({
                "schema_version": 1,
                "packet_sha256": packet.packet_sha256,
                "claims": [{
                    "claim_id": "RC-001",
                    "statement": "The public value is 42.",
                    "source_ids": [packet.source_ids()[0]],
                    "confidence": 0.9,
                }],
            })

    return packet, ResearchClaimCoordinator(Provider()).propose(packet, target, decision)


class ResearchReviewTests(unittest.TestCase):
    def test_review_is_session_local_claim_metadata_not_an_answer_or_source_copy(self):
        packet, result = packet_and_result()
        store = SessionResearchReviewStore(clock=lambda: 100.0, id_factory=lambda: "RR-" + "1" * 24)
        record = store.create(packet, result)

        self.assertEqual("claims_proposed", record.status)
        self.assertEqual(packet.source_ids()[0], record.source_labels[0][0])
        self.assertEqual(100.0, record.source_labels[0][2])
        self.assertNotIn("The public value is 42.", repr(record.source_labels))
        self.assertFalse(hasattr(record, "answer"))
        self.assertFalse(hasattr(record, "memory"))
        self.assertEqual(record, store.get(record.review_id))
        self.assertEqual(1, store.summaries()[0]["claim_count"])

    def test_store_evicts_oldest_record_at_a_small_fixed_limit(self):
        packet, result = packet_and_result()
        counter = iter(range(MAX_SESSION_RESEARCH_REVIEWS + 1))
        store = SessionResearchReviewStore(
            id_factory=lambda: "RR-" + f"{next(counter):024x}",
        )
        ids = [store.create(packet, result).review_id for _ in range(MAX_SESSION_RESEARCH_REVIEWS + 1)]

        self.assertIsNone(store.get(ids[0]))
        self.assertEqual(MAX_SESSION_RESEARCH_REVIEWS, len(store.summaries()))
        self.assertEqual(ids[-1], store.summaries()[0]["review_id"])

    def test_mismatched_result_cannot_be_recorded(self):
        packet, result = packet_and_result()
        other_packet = build_research_source_packet("Another question?", packet.sources)
        with self.assertRaisesRegex(ValueError, "binding"):
            SessionResearchReviewStore().create(other_packet, result)


if __name__ == "__main__":
    unittest.main()
