from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.factual_research_policy import classify_factual_research_request
from pipeline.tool_web_search_preflight import (
    WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
    WebSearchServicePrerequisite,
)
from pipeline.tool_web_search_runtime import SessionWebSearchPrerequisiteStore


QUERY = "Please research the current price of an RTX 4070."


def service(ref, *, service_id="fixture.search", deployment="local", maximum_results=4):
    return WebSearchServicePrerequisite(
        1, ref, service_id, deployment, maximum_results, True, 100.0, 180.0,
        WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
    )


class SearchPrerequisiteStoreTests(unittest.TestCase):
    def test_reservation_is_inert_then_exact_observation_prepares_evidence(self):
        store = SessionWebSearchPrerequisiteStore(
            service_id="fixture.search", deployment="local", maximum_results=4,
        )
        service_ref, disclosure_ref = store.reserve_public(
            QUERY, classify_factual_research_request(QUERY),
        )
        with self.assertRaises(KeyError):
            store.service_for(service_ref)
        prepared_service, disclosure = store.prepare_reserved(
            service_ref, disclosure_ref, service(service_ref),
        )
        self.assertEqual("fixture.search", prepared_service.service_id)
        self.assertEqual("confirmation_required", disclosure.decision.status)
        self.assertEqual(prepared_service, store.service_for(service_ref))
        self.assertEqual(disclosure, store.disclosure_for(disclosure_ref))
        self.assertFalse(hasattr(disclosure, "query"))

    def test_unrequired_research_or_wrong_profile_never_prepares(self):
        store = SessionWebSearchPrerequisiteStore(
            service_id="fixture.search", deployment="local", maximum_results=4,
        )
        with self.assertRaisesRegex(ValueError, "not eligible"):
            store.reserve_public("Tell me a fictional story", classify_factual_research_request(
                "Tell me a fictional story",
            ))
        service_ref, disclosure_ref = store.reserve_public(
            QUERY, classify_factual_research_request(QUERY),
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            store.prepare_reserved(
                service_ref, disclosure_ref,
                service(service_ref, service_id="other.search"),
            )
        with self.assertRaises(KeyError):
            store.disclosure_for(disclosure_ref)

    def test_revoke_removes_reservation_or_prepared_evidence(self):
        store = SessionWebSearchPrerequisiteStore(
            service_id="fixture.search", deployment="local", maximum_results=4,
        )
        service_ref, disclosure_ref = store.reserve_public(
            QUERY, classify_factual_research_request(QUERY),
        )
        self.assertTrue(store.revoke(service_ref))
        self.assertFalse(store.revoke(disclosure_ref))
        with self.assertRaisesRegex(ValueError, "not found"):
            store.prepare_reserved(service_ref, disclosure_ref, service(service_ref))


if __name__ == "__main__":
    unittest.main()
