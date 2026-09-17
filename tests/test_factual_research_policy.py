from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.factual_research_policy import (
    FactualResearchContext,
    classify_factual_research_request,
)


class FactualResearchPolicyTests(unittest.TestCase):
    def test_explicit_research_request_requires_research(self):
        for text in (
            "Please research which answer is correct.",
            "Can you verify this using sources?",
            "Look this up on the web.",
            "Fact-check that claim.",
        ):
            with self.subTest(text=text):
                decision = classify_factual_research_request(text)
                self.assertEqual("research_required", decision.disposition)
                self.assertEqual("explicit_research_request", decision.reason)

    def test_freshness_sensitive_question_requires_research(self):
        decision = classify_factual_research_request("What is the current price of this GPU?")
        self.assertEqual("research_required", decision.disposition)
        self.assertEqual("freshness_sensitive_request", decision.reason)

    def test_high_stakes_question_requires_research(self):
        decision = classify_factual_research_request("Should I change this medication dosage?")
        self.assertEqual("research_required", decision.disposition)
        self.assertEqual("high_stakes_request", decision.reason)

    def test_ordinary_chat_result_does_not_claim_grounding(self):
        decision = classify_factual_research_request("How does the StarFur event log work?")
        self.assertEqual("ordinary_chat_unclassified", decision.disposition)
        self.assertEqual("no_mandatory_research_signal", decision.reason)
        self.assertFalse(hasattr(decision, "grounded"))
        self.assertFalse(hasattr(decision, "authorized"))

    def test_similar_project_language_does_not_trigger_freshness(self):
        decision = classify_factual_research_request("What does current_location mean?")
        self.assertEqual("ordinary_chat_unclassified", decision.disposition)

    def test_fictional_context_allows_story_generation(self):
        context = FactualResearchContext(roleplay_active=True)
        decision = classify_factual_research_request(
            "What medication dosage does the ship doctor prescribe?",
            context=context,
        )
        self.assertEqual("fictional_generation_allowed", decision.disposition)
        self.assertEqual("fictional_context", decision.reason)

    def test_explicit_verification_overrides_fictional_context(self):
        context = FactualResearchContext(adventure_active=True)
        decision = classify_factual_research_request(
            "Pause the story and verify this using sources.",
            context=context,
        )
        self.assertEqual("research_required", decision.disposition)
        self.assertEqual("explicit_research_request", decision.reason)

    def test_context_labels_are_not_authority(self):
        context = FactualResearchContext(roleplay_active=False, adventure_active=False)
        self.assertFalse(hasattr(context, "permission"))
        self.assertFalse(hasattr(context, "provider"))
        self.assertFalse(hasattr(context, "tool"))

    def test_invalid_input_fails_closed(self):
        with self.assertRaises(TypeError):
            classify_factual_research_request(None)
        with self.assertRaises(ValueError):
            classify_factual_research_request("\x00")


if __name__ == "__main__":
    unittest.main()
