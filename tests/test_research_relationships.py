import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_claims import ResearchClaim, ResearchClaimSet
from pipeline.research_coordinator import ResearchCoordinationResult
from pipeline.research_relationships import (
    parse_research_claim_relationships,
    research_claim_relationship_json_schema,
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


def _review():
    first = _source("TF-one", "https://one.example/fact", "The value is 42.")
    second = _source("TF-two", "https://two.example/fact", "The value is 43.")
    packet = build_research_source_packet("What is the value?", (first, second))
    claims = ResearchClaimSet(1, packet.packet_sha256, (
        ResearchClaim(1, "RC-001", "The value is 42.", (first.source_id,), 0.9),
        ResearchClaim(1, "RC-002", "The value is 43.", (second.source_id,), 0.8),
        ResearchClaim(1, "RC-003", "The sources discuss the same value.", (first.source_id, second.source_id), 0.7),
    ))
    result = ResearchCoordinationResult(1, packet.packet_sha256, "d" * 64, "claims_proposed", claims)
    return SessionResearchReviewStore(
        clock=lambda: 101.0,
        id_factory=lambda: "RR-" + "1" * 24,
    ).create(packet, result)


def _payload(review, relationships):
    return json.dumps({
        "schema_version": 1,
        "review_id": review.review_id,
        "packet_sha256": review.packet_sha256,
        "relationships": relationships,
    })


class ResearchRelationshipTests(unittest.TestCase):
    def test_strict_relationships_are_bound_untrusted_proposals_only(self):
        review = _review()
        raw = _payload(review, [
            {
                "relationship_id": "RL-001",
                "left_claim_id": "RC-001",
                "right_claim_id": "RC-002",
                "relation": "possibly_conflicts",
                "confidence": 0.8,
            },
            {
                "relationship_id": "RL-002",
                "left_claim_id": "RC-001",
                "right_claim_id": "RC-003",
                "relation": "related_only",
                "confidence": 0.6,
            },
        ])

        result = parse_research_claim_relationships(raw, review)

        self.assertEqual(review.review_id, result.review_id)
        self.assertEqual("possibly_conflicts", result.relationships[0].relation)
        self.assertFalse(hasattr(result, "verified"))
        self.assertFalse(hasattr(result, "corroborated"))
        self.assertFalse(hasattr(result, "answer_eligible"))

    def test_stale_unknown_reversed_and_duplicate_pairs_fail_closed(self):
        review = _review()
        base = {
            "relationship_id": "RL-001",
            "left_claim_id": "RC-001",
            "right_claim_id": "RC-002",
            "relation": "possibly_supports_same_proposition",
            "confidence": 0.5,
        }
        stale = json.loads(_payload(review, [base]))
        stale["packet_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "binding"):
            parse_research_claim_relationships(json.dumps(stale), review)

        unknown = dict(base, right_claim_id="RC-999")
        with self.assertRaisesRegex(ValueError, "outside"):
            parse_research_claim_relationships(_payload(review, [unknown]), review)

        reversed_pair = dict(base, left_claim_id="RC-002", right_claim_id="RC-001")
        with self.assertRaisesRegex(ValueError, "canonical"):
            parse_research_claim_relationships(_payload(review, [reversed_pair]), review)

        duplicate = dict(base, relationship_id="RL-002")
        with self.assertRaisesRegex(ValueError, "pairs"):
            parse_research_claim_relationships(_payload(review, [base, duplicate]), review)

    def test_unknown_duplicate_fields_ordering_and_nonfinite_confidence_fail_closed(self):
        review = _review()
        relationship = {
            "relationship_id": "RL-002",
            "left_claim_id": "RC-001",
            "right_claim_id": "RC-002",
            "relation": "insufficient_basis",
            "confidence": 0.1,
        }
        with self.assertRaisesRegex(ValueError, "ordered"):
            parse_research_claim_relationships(_payload(review, [relationship]), review)

        invalid = dict(relationship, relationship_id="RL-001", confidence=float("nan"))
        with self.assertRaisesRegex(ValueError, "confidence"):
            parse_research_claim_relationships(_payload(review, [invalid]), review)

        duplicate_key = (
            '{"schema_version":1,"schema_version":1,"review_id":"' + review.review_id
            + '","packet_sha256":"' + review.packet_sha256 + '","relationships":[]}'
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_research_claim_relationships(duplicate_key, review)

        extra = json.loads(_payload(review, []))
        extra["authority"] = True
        with self.assertRaisesRegex(ValueError, "envelope"):
            parse_research_claim_relationships(json.dumps(extra), review)

    def test_exact_json_schema_is_bound_to_review_claims(self):
        review = _review()
        schema = research_claim_relationship_json_schema(review)

        self.assertEqual(review.review_id, schema["properties"]["review_id"]["const"])
        self.assertEqual(review.packet_sha256, schema["properties"]["packet_sha256"]["const"])
        item = schema["properties"]["relationships"]["items"]
        self.assertEqual(["RC-001", "RC-002", "RC-003"], item["properties"]["left_claim_id"]["enum"])
        self.assertFalse("verified" in item["properties"])


if __name__ == "__main__":
    unittest.main()
