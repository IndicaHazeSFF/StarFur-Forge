import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_relationship import AdventureRelationshipFact
from pipeline.adventure_session import AdventureSessionState
from pipeline.adventure_turn_coordinator import AdventureTurnCoordinator, AdventureTurnCoordinatorError


class _Provider:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def propose(self, request):
        self.requests.append(request)
        return self.response


class AdventureTurnCoordinatorTests(unittest.TestCase):
    def _record(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return AdventureRegistry(directory.name, now=lambda: datetime(2026, 8, 26, tzinfo=UTC)).create("Quiet Ember")

    def _session(self):
        record = self._record()
        event = AdventureEvent(1, "AE-000001", "discovery", "The crew finds a brass key.", None, "2026-08-26T00:00:00+00:00")
        relationship = AdventureRelationshipFact("Vespera", "trust", "49/100", "AE-000002")
        return AdventureSessionState(
            record=record, event_count=2, context_events=(event,),
            relationship_facts=(relationship,), context_relationship_facts=(relationship,),
        )

    def test_coordinator_captures_typed_safe_context_and_returns_only_noncanonical_candidates(self):
        provider = _Provider({
            "schema_version": 1,
            "candidates": [{"event_type": "discovery", "summary": "The hatch opens.", "confidence": 0.8}],
        })
        session = self._session()

        result = AdventureTurnCoordinator(provider).propose(
            session, user_text="I turn the brass key.", narrator_text="The lock clicks.",
        )

        self.assertEqual(session.record, result.request.record)
        self.assertEqual(session.event_count, result.request.event_count)
        self.assertEqual("TC-001", result.batch.candidates[0].candidate_id)
        self.assertEqual(1, len(provider.requests))
        prompt = provider.requests[0].authoritative_context
        self.assertIn("The crew finds a brass key", prompt)
        self.assertIn("qualitative internal state", prompt)
        self.assertNotIn("49/100", prompt)
        # The coordinator holds no event-log or inbox reference, so its result
        # is necessarily noncanonical until a later explicit selection/stage.
        self.assertFalse(hasattr(result, "event_id"))

    def test_unmounted_or_invalid_provider_output_fails_before_any_candidate_result(self):
        provider = _Provider({"schema_version": 1, "candidates": []})
        coordinator = AdventureTurnCoordinator(provider)

        with self.assertRaisesRegex(AdventureTurnCoordinatorError, "failed safely"):
            coordinator.propose(AdventureSessionState.unmounted(), user_text="I wait.")
        self.assertEqual([], provider.requests)

        with self.assertRaisesRegex(AdventureTurnCoordinatorError, "failed safely"):
            coordinator.propose(self._session(), user_text="I wait.")
        self.assertEqual(1, len(provider.requests))


if __name__ == "__main__":
    unittest.main()
