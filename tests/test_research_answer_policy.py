from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_answer_policy import evaluate_research_answer_policy
from tests.test_research_brief import review_record


class ResearchAnswerPolicyTests(unittest.TestCase):
    def test_claim_review_is_only_source_backed_and_unverified(self):
        decision = evaluate_research_answer_policy(review_record())
        self.assertEqual("source_backed_unverified", decision.status)
        self.assertEqual("explicit_local_review_claims", decision.reason)
        self.assertEqual(1, decision.claim_count)
        self.assertFalse(hasattr(decision, "verified"))
        self.assertFalse(hasattr(decision, "corroborated"))

    def test_empty_review_fails_closed_as_insufficient_support(self):
        decision = evaluate_research_answer_policy(review_record(empty=True))
        self.assertEqual("insufficient_support", decision.status)
        self.assertEqual("no_supported_claims", decision.reason)
        self.assertEqual(0, decision.claim_count)


if __name__ == "__main__":
    unittest.main()
