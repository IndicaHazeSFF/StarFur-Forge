from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.factual_research_policy import classify_factual_research_request
from pipeline.research_discovery import (
    ResearchDiscoveryIntent,
    evaluate_research_discovery,
)


def required_decision(query="Please research the current GPU price."):
    return classify_factual_research_request(query)


class ResearchDiscoveryPolicyTests(unittest.TestCase):
    def test_public_web_query_requires_separate_broker_confirmation(self):
        query = "Please research the current GPU price."
        factual = required_decision(query)
        intent = ResearchDiscoveryIntent.from_request(
            query, factual, target_kind="public_web_search", data_classification="public",
        )
        decision = evaluate_research_discovery(intent, query, factual)
        self.assertEqual("confirmation_required", decision.status)
        self.assertEqual("public_search_requires_broker_confirmation", decision.reason)
        self.assertFalse(hasattr(decision, "authorized"))
        self.assertFalse(hasattr(decision, "query"))

    def test_local_discovery_is_eligible_without_implying_execution(self):
        query = "What is the current price of this GPU?"
        factual = required_decision(query)
        intent = ResearchDiscoveryIntent.from_request(
            query, factual, target_kind="local_catalog", data_classification="private",
        )
        decision = evaluate_research_discovery(intent, query, factual)
        self.assertEqual("eligible", decision.status)
        self.assertEqual("local_discovery_eligible", decision.reason)
        self.assertFalse(hasattr(decision, "provider"))
        self.assertFalse(hasattr(decision, "tool"))

    def test_private_or_secret_web_disclosure_denies(self):
        query = "Please research my private medical record."
        factual = required_decision(query)
        for classification, reason in (
            ("private", "private_query_disclosure_unsupported"),
            ("secret", "secret_query_disclosure_forbidden"),
        ):
            with self.subTest(classification=classification):
                intent = ResearchDiscoveryIntent.from_request(
                    query, factual,
                    target_kind="public_web_search",
                    data_classification=classification,
                )
                decision = evaluate_research_discovery(intent, query, factual)
                self.assertEqual("denied", decision.status)
                self.assertEqual(reason, decision.reason)

    def test_nonresearch_request_cannot_be_promoted_into_discovery(self):
        query = "Tell me a joke."
        factual = classify_factual_research_request(query)
        intent = ResearchDiscoveryIntent.from_request(
            query, factual, target_kind="local_catalog", data_classification="public",
        )
        decision = evaluate_research_discovery(intent, query, factual)
        self.assertEqual("denied", decision.status)
        self.assertEqual("research_not_required", decision.reason)

    def test_query_or_classification_binding_cannot_be_swapped(self):
        query = "Please research the current GPU price."
        factual = required_decision(query)
        intent = ResearchDiscoveryIntent.from_request(
            query, factual, target_kind="public_web_search", data_classification="public",
        )
        changed = evaluate_research_discovery(intent, "Please research another product.", factual)
        self.assertEqual("request_binding_mismatch", changed.reason)
        stale = evaluate_research_discovery(
            replace(intent, trigger_reason="high_stakes_request"), query, factual,
        )
        self.assertEqual("request_binding_mismatch", stale.reason)

    def test_intent_contains_only_bounded_metadata(self):
        query = "Please verify a public claim."
        intent = ResearchDiscoveryIntent.from_request(
            query,
            required_decision(query),
            target_kind="public_web_search",
            data_classification="public",
        )
        self.assertEqual(len(" ".join(query.split()).encode("utf-8")), intent.query_byte_count)
        self.assertFalse(hasattr(intent, "query"))
        self.assertFalse(hasattr(intent, "confirmation"))
        self.assertFalse(hasattr(intent, "grant"))


if __name__ == "__main__":
    unittest.main()
