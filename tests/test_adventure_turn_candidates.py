import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_turn_candidates import (
    AdventureTurnCandidateError,
    parse_untrusted_adventure_turn_candidates,
)


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

    def test_structured_or_malformed_provider_data_fails_before_any_staging_or_write(self):
        with self.assertRaisesRegex(AdventureTurnCandidateError, "dedicated typed policy"):
            parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "state_change", "summary": "Set location.", "confidence": 0.9}],
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


if __name__ == "__main__":
    unittest.main()
