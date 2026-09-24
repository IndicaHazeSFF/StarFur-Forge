from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_answer_binding import evaluate_research_answer_binding
from test_research_brief import review_record


class ResearchAnswerBindingTests(unittest.TestCase):
    def test_exact_canonical_question_matches_its_review_without_storing_text(self):
        record = review_record()

        decision = evaluate_research_answer_binding(record, "  Question?\n")

        self.assertEqual("matches_review", decision.status)
        self.assertEqual(record.review_id, decision.review_id)
        self.assertEqual(record.packet_sha256, decision.packet_sha256)
        self.assertNotIn("Question?", repr(record))
        self.assertNotIn("Question?", repr(decision))
        self.assertFalse(hasattr(decision, "answer"))
        self.assertFalse(hasattr(decision, "verified"))

    def test_different_question_fails_closed_without_reusing_review_claims(self):
        record = review_record()

        decision = evaluate_research_answer_binding(record, "A different question?")

        self.assertEqual("question_mismatch", decision.status)
        self.assertEqual(record.question_sha256, record.question_sha256)
        self.assertNotEqual(record.question_sha256, decision.question_sha256)

    def test_invalid_review_or_question_rejects(self):
        with self.assertRaises(TypeError):
            evaluate_research_answer_binding(object(), "Question?")
        with self.assertRaises(TypeError):
            evaluate_research_answer_binding(review_record(), None)


if __name__ == "__main__":
    unittest.main()
