import unittest
from dataclasses import replace
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_claims import ResearchClaim, ResearchClaimSet
from pipeline.research_coordinator import ResearchCoordinationResult
from pipeline.research_evidence import ResearchClaimEvidence, ResearchEvidenceAssessment
from pipeline.research_relationship_brief import build_research_relationship_brief
from pipeline.research_relationship_coordinator import ResearchRelationshipCoordinationResult
from pipeline.research_relationship_review import ResearchRelationshipReviewRecord
from pipeline.research_relationships import ResearchClaimRelationship, ResearchClaimRelationshipSet
from pipeline.research_review import ResearchReviewRecord


PACKET = "a" * 64
TARGET = "b" * 64
SOURCE = "RS-" + "1" * 24
REVIEW_ID = "RR-" + "2" * 24
RELATIONSHIP_REVIEW_ID = "RX-" + "3" * 24


def fixtures():
    claims = ResearchClaimSet(1, PACKET, (
        ResearchClaim(1, "RC-001", "One.", (SOURCE,), 0.9),
        ResearchClaim(1, "RC-002", "Two.", (SOURCE,), 0.8),
    ))
    claim_result = ResearchCoordinationResult(1, PACKET, TARGET, "claims_proposed", claims)
    evidence = ResearchEvidenceAssessment(1, PACKET, (
        ResearchClaimEvidence(1, "RC-001", 1, 1, "single_source"),
        ResearchClaimEvidence(1, "RC-002", 1, 1, "single_source"),
    ))
    review = ResearchReviewRecord(
        1, REVIEW_ID, 1.0, PACKET, "4" * 64, 10, "claims_proposed",
        ((SOURCE, "https://example.com", 1.0),), evidence, claim_result,
    )
    relationships = ResearchClaimRelationshipSet(1, REVIEW_ID, PACKET, (
        ResearchClaimRelationship(
            1, "RL-001", "RC-001", "RC-002", "related_only", 0.7,
        ),
    ))
    result = ResearchRelationshipCoordinationResult(
        1, REVIEW_ID, PACKET, TARGET, "relationships_proposed", relationships,
    )
    relationship_review = ResearchRelationshipReviewRecord(
        1, RELATIONSHIP_REVIEW_ID, 2.0, REVIEW_ID, PACKET, TARGET,
        "relationships_proposed", result,
    )
    return review, relationship_review


class ResearchRelationshipBriefTests(unittest.TestCase):
    def test_projects_only_exact_reviewed_relationships(self):
        review, relationship_review = fixtures()
        brief = build_research_relationship_brief(review, relationship_review)
        self.assertEqual(RELATIONSHIP_REVIEW_ID, brief.relationship_review_id)
        self.assertEqual("One.", brief.items[0].left_statement)
        self.assertEqual("Two.", brief.items[0].right_statement)
        self.assertEqual("related_only", brief.items[0].relation)

    def test_mismatched_claim_review_fails_closed(self):
        review, relationship_review = fixtures()
        altered = replace(review, review_id="RR-" + "5" * 24)
        with self.assertRaisesRegex(ValueError, "binding"):
            build_research_relationship_brief(altered, relationship_review)


if __name__ == "__main__":
    unittest.main()
