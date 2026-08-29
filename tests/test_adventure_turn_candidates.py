import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_turn_candidates import (
    AdventureTurnCandidateError,
    ORDINARY_GENERATED_EVENT_TYPES,
    parse_untrusted_adventure_turn_candidates,
    render_adventure_turn_candidate_batch,
)
from pipeline.adventure_turn_policy import ORDINARY_ADVENTURE_EVENT_TYPES


class AdventureTurnCandidateTests(unittest.TestCase):
    def test_ordinary_candidates_are_bounded_and_receive_deterministic_ids(self):
        batch = parse_untrusted_adventure_turn_candidates({
            "schema_version": 1,
            "candidates": [
                {"event_type": "discovery", "summary": "The crew finds a brass key.", "confidence": 0.8},
                {"event_type": "unresolved_hook", "summary": "The engine noise returns.", "details": "Distant but persistent.", "confidence": 0.5},
            ],
        })
        self.assertEqual(["TC-001", "TC-002"], [candidate.candidate_id for candidate in batch.candidates])
        self.assertEqual("discovery", batch.candidates[0].draft.event_type)
        self.assertEqual(0.5, batch.candidates[1].confidence)

    def test_rendered_candidates_remain_explicitly_untrusted_and_non_staged(self):
        batch = parse_untrusted_adventure_turn_candidates({
            "schema_version": 1,
            "candidates": [{
                "event_type": "discovery",
                "summary": "The crew finds a brass key.",
                "details": "It is warm to the touch.",
                "confidence": 0.8,
            }],
        })
        rendered = render_adventure_turn_candidate_batch(batch)
        self.assertIn("TC-001 [discovery] The crew finds a brass key.", rendered)
        self.assertIn("Details: It is warm to the touch.", rendered)
        self.assertIn("untrusted; not staged", rendered)
        self.assertIn("must explicitly validate and stage", rendered)
        with self.assertRaises(TypeError):
            render_adventure_turn_candidate_batch(object())

    def test_structured_or_malformed_provider_data_fails_before_any_staging_or_write(self):
        with self.assertRaisesRegex(AdventureTurnCandidateError, "not permitted"):
            parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "state_change", "summary": "Set location.", "confidence": 0.9}],
            })
        with self.assertRaisesRegex(AdventureTurnCandidateError, "not permitted"):
            parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "premise", "summary": "A new premise.", "confidence": 0.9}],
            })
        with self.assertRaisesRegex(AdventureTurnCandidateError, "fields are invalid"):
            parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "discovery", "summary": "Key found.", "confidence": 0.9, "reasoning": "hidden"}],
            })
        with self.assertRaisesRegex(AdventureTurnCandidateError, "between 0 and 1"):
            parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "discovery", "summary": "Key found.", "confidence": 1.1}],
            })

    def test_generated_event_allowlist_is_explicit_and_ordinary_only(self):
        self.assertIs(ORDINARY_GENERATED_EVENT_TYPES, ORDINARY_ADVENTURE_EVENT_TYPES)
        self.assertEqual({
            "choice", "discovery", "promise", "lie", "emotional_transition",
            "unresolved_hook", "inventory_change", "location_change",
        }, set(ORDINARY_GENERATED_EVENT_TYPES))


if __name__ == "__main__":
    unittest.main()
