import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_turn_generation import AdventureTurnGenerationRequest
from pipeline.adventure_turn_mutation_generation import AdventureTurnMutationGenerationRequest
from pipeline.adventure_turn_provider import (
    AdventureTurnProviderError,
    ChatAdventureTurnCandidateProvider,
    MAX_ADVENTURE_TURN_PROVIDER_RESPONSE_CHARACTERS,
    validate_adventure_turn_provider_result,
    ChatAdventureTurnMutationCandidateProvider,
    validate_adventure_turn_mutation_provider_result,
)


class _FakeChatProvider:
    name = "fake"

    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, messages, *, model=None, options=None, stream=False):
        self.calls.append((tuple(messages), model, options, stream))
        return self.response

    def list_models(self):
        return []

    def probe_health(self):
        return []


class _TypedMessage:
    def __init__(self, content):
        self.content = content


class _TypedResponse:
    def __init__(self, content):
        self.message = _TypedMessage(content)


class AdventureTurnProviderTests(unittest.TestCase):
    def _request(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        record = AdventureRegistry(directory.name, now=lambda: datetime(2026, 8, 26, tzinfo=UTC)).create("Quiet Ember")
        return AdventureTurnGenerationRequest(record, 0, "Location: chart room.", "I open the hatch.")

    def _mutation_request(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        record = AdventureRegistry(directory.name, now=lambda: datetime(2026, 8, 26, tzinfo=UTC)).create("Quiet Ember")
        return AdventureTurnMutationGenerationRequest(record, 0, "Location: chart room.", "I open the hatch.")

    def test_chat_adapter_calls_only_when_explicitly_proposed_and_returns_decoded_data(self):
        provider = _FakeChatProvider({"message": {"content": '{"schema_version":1,"candidates":[{"event_type":"discovery","summary":"The hatch opens.","confidence":0.8}]}'}})
        adapter = ChatAdventureTurnCandidateProvider(provider, model="turn-model", options={"temperature": 0})

        decoded = adapter.propose(self._request())
        batch = validate_adventure_turn_provider_result(decoded)

        self.assertEqual("TC-001", batch.candidates[0].candidate_id)
        self.assertEqual(1, len(provider.calls))
        messages, model, options, stream = provider.calls[0]
        self.assertEqual("turn-model", model)
        self.assertEqual({"temperature": 0}, options)
        self.assertFalse(stream)
        self.assertEqual("system", messages[0]["role"])

    def test_invalid_response_or_envelope_fails_without_candidate_result(self):
        adapter = ChatAdventureTurnCandidateProvider(
            _FakeChatProvider({"message": {"content": "not json"}}),
        )
        with self.assertRaisesRegex(AdventureTurnProviderError, "strict JSON"):
            adapter.propose(self._request())
        with self.assertRaisesRegex(AdventureTurnProviderError, "invalid candidate envelope"):
            validate_adventure_turn_provider_result({"schema_version": 1, "candidates": []})

    def test_adapter_accepts_typed_ollama_style_responses_and_fenced_json_before_schema_validation(self):
        content = "```json\n{\"schema_version\":1,\"candidates\":[{\"event_type\":\"discovery\",\"summary\":\"The hatch opens.\",\"confidence\":0.8}]}\n```"
        adapter = ChatAdventureTurnCandidateProvider(_FakeChatProvider(_TypedResponse(content)))

        decoded = adapter.propose(self._request())
        batch = validate_adventure_turn_provider_result(decoded)

        self.assertEqual("TC-001", batch.candidates[0].candidate_id)

    def test_empty_or_oversized_provider_text_fails_before_json_decoding(self):
        for content, expected in (
            ("   ", "empty"),
            ("x" * (MAX_ADVENTURE_TURN_PROVIDER_RESPONSE_CHARACTERS + 1), "too large"),
        ):
            with self.subTest(expected=expected):
                adapter = ChatAdventureTurnCandidateProvider(
                    _FakeChatProvider({"message": {"content": content}}),
                )
                with self.assertRaisesRegex(AdventureTurnProviderError, expected):
                    adapter.propose(self._request())

    def test_typed_mutation_adapter_has_a_separate_schema_validator(self):
        provider = _FakeChatProvider({"message": {"content": (
            '{"schema_version":1,"candidates":[{"mutation":{"kind":"state_set",'
            '"key":"current_location","value":"engine room"},"confidence":0.8}]}'
        )}})
        adapter = ChatAdventureTurnMutationCandidateProvider(provider, model="mutation-model")

        decoded = adapter.propose(self._mutation_request())
        batch = validate_adventure_turn_mutation_provider_result(decoded)

        self.assertEqual("TM-001", batch.candidates[0].candidate_id)
        self.assertEqual("state_set", batch.candidates[0].mutation.kind)
        self.assertEqual("mutation-model", provider.calls[0][1])
        with self.assertRaisesRegex(AdventureTurnProviderError, "invalid candidate envelope"):
            validate_adventure_turn_mutation_provider_result({
                "schema_version": 1,
                "candidates": [{"event_type": "discovery", "summary": "A key.", "confidence": 0.8}],
            })


if __name__ == "__main__":
    unittest.main()
