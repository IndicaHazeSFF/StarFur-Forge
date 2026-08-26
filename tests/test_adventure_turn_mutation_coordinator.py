import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_session import AdventureSessionState
from pipeline.adventure_turn_mutation_coordinator import (
    AdventureTurnMutationCoordinator,
    AdventureTurnMutationCoordinatorError,
)
from pipeline.adventure_turn_provider import AdventureTurnProviderError


class _Provider:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def propose(self, request):
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class AdventureTurnMutationCoordinatorTests(unittest.TestCase):
    def _session(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        registry = AdventureRegistry(directory.name, now=lambda: datetime(2026, 8, 26, tzinfo=UTC))
        record = registry.create("Quiet Ember")
        return AdventureSessionState(record=record, event_count=0)

    def test_coordinator_returns_validated_typed_candidates_without_writing(self):
        provider = _Provider({
            "schema_version": 1,
            "candidates": [{
                "mutation": {"kind": "state_set", "key": "current_location", "value": "engine room"},
                "confidence": 0.8,
            }],
        })
        result = AdventureTurnMutationCoordinator(provider).propose(
            self._session(), user_text="I open the hatch.", provider_name="Ollama", model_name="qwen3:8b",
        )

        self.assertEqual("TM-001", result.batch.candidates[0].candidate_id)
        self.assertEqual("adventure_turn_mutation_generation", result.request.task_id)
        self.assertEqual("Ollama", result.request.provenance.provider_name)
        self.assertEqual(1, len(provider.requests))

    def test_provider_or_schema_failure_becomes_one_safe_coordinator_failure(self):
        no_change = AdventureTurnMutationCoordinator(_Provider({"schema_version": 1, "candidates": []})).propose(
            self._session(), user_text="I wait.",
        )
        self.assertEqual((), no_change.batch.candidates)
        with self.assertRaisesRegex(AdventureTurnMutationCoordinatorError, "failed safely") as caught:
            AdventureTurnMutationCoordinator(_Provider({
                "schema_version": 1,
                "candidates": [{"event_type": "discovery", "summary": "A key is found.", "confidence": 0.8}],
            })).propose(
                self._session(), user_text="I wait.",
            )
        self.assertEqual("mutation_candidate_envelope_invalid", caught.exception.reason)
        with self.assertRaisesRegex(AdventureTurnMutationCoordinatorError, "failed safely") as caught:
            AdventureTurnMutationCoordinator(_Provider(
                AdventureTurnProviderError("unavailable", reason="provider_unavailable")
            )).propose(self._session(), user_text="I wait.")
        self.assertEqual("provider_unavailable", caught.exception.reason)


if __name__ == "__main__":
    unittest.main()
