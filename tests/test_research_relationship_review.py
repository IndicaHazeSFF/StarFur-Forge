import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_claims import ResearchClaim, ResearchClaimSet
from pipeline.research_coordinator import ResearchCoordinationResult
from pipeline.research_relationship_coordinator import ResearchRelationshipCoordinationResult
from pipeline.research_relationship_review import (
    MAX_SESSION_RESEARCH_RELATIONSHIP_REVIEWS,
    SessionResearchRelationshipReviewStore,
)
from pipeline.research_relationships import ResearchClaimRelationshipSet
from pipeline.research_review import ResearchReviewRecord


PACKET = "a" * 64
TARGET = "b" * 64


def claim_review():
    claims = ResearchClaimSet(1, PACKET, (
        ResearchClaim(1, "RC-001", "One.", ("RS-" + "1" * 24,), 0.9),
        ResearchClaim(1, "RC-002", "Two.", ("RS-" + "1" * 24,), 0.8),
    ))
    result = ResearchCoordinationResult(1, PACKET, TARGET, "claims_proposed", claims)
    # Construct bounded evidence directly; this store does not derive it.
    from pipeline.research_evidence import ResearchEvidenceAssessment, ResearchClaimEvidence
    assessment = ResearchEvidenceAssessment(
        1, PACKET, (
            ResearchClaimEvidence(1, "RC-001", 1, 1, "single_source"),
            ResearchClaimEvidence(1, "RC-002", 1, 1, "single_source"),
        ),
    )
    return ResearchReviewRecord(
        1, "RR-" + "2" * 24, 1.0, PACKET, "3" * 64, 10,
        "claims_proposed", (("RS-" + "1" * 24, "https://example.com", 1.0),), assessment, result,
    )


def relationship_result(review):
    relationships = ResearchClaimRelationshipSet(1, review.review_id, PACKET, ())
    return ResearchRelationshipCoordinationResult(
        1, review.review_id, PACKET, TARGET, "no_relationships", relationships,
    )


class ResearchRelationshipReviewTests(unittest.TestCase):
    def test_store_is_bounded_session_local_and_binds_to_claim_review(self):
        review = claim_review()
        store = SessionResearchRelationshipReviewStore(clock=lambda: 2.0, id_factory=lambda: "RX-" + "4" * 24)
        record = store.create(review, relationship_result(review))
        self.assertEqual(review.review_id, record.claim_review_id)
        self.assertEqual("no_relationships", record.status)
        self.assertEqual(record, store.get(record.relationship_review_id))
        self.assertEqual(1, len(store.summaries()))

    def test_bad_or_duplicate_ids_fail_without_replacing_records(self):
        review = claim_review()
        store = SessionResearchRelationshipReviewStore(id_factory=lambda: "invalid")
        with self.assertRaisesRegex(ValueError, "ID is invalid"):
            store.create(review, relationship_result(review))
        self.assertEqual((), store.summaries())
        self.assertIsNone(store.get("RX-forged"))

    def test_oldest_record_evicts_at_fixed_bound(self):
        review = claim_review()
        ids = iter("RX-" + f"{number:024x}" for number in range(MAX_SESSION_RESEARCH_RELATIONSHIP_REVIEWS + 1))
        store = SessionResearchRelationshipReviewStore(id_factory=lambda: next(ids))
        for _ in range(MAX_SESSION_RESEARCH_RELATIONSHIP_REVIEWS + 1):
            store.create(review, relationship_result(review))
        self.assertEqual(MAX_SESSION_RESEARCH_RELATIONSHIP_REVIEWS, len(store.summaries()))
        self.assertIsNone(store.get("RX-" + f"{0:024x}"))


if __name__ == "__main__":
    unittest.main()
