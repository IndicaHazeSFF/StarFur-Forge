import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_turn_mutation_candidates import (
    AdventureTurnMutationCandidateError,
    parse_untrusted_adventure_turn_mutation_candidates,
    render_adventure_turn_mutation_candidate_batch,
)
from pipeline.adventure_turn_provenance import AdventureTurnGenerationProvenance


class AdventureTurnMutationCandidateTests(unittest.TestCase):
    def test_typed_candidates_are_bounded_and_receive_distinct_ids(self):
        batch = parse_untrusted_adventure_turn_mutation_candidates({
            "schema_version": 1,
            "candidates": [
                {"mutation": {"kind": "state_set", "key": "current_location", "value": "engine room"}, "confidence": 0.8},
                {"mutation": {"kind": "relationship_set", "subject": "Vespera", "dimension": "trust", "value": "cautious"}, "confidence": 0.7},
                {"mutation": {"kind": "knowledge_set", "subject": "Rook", "status": "believes", "fact": "the key opens the hatch"}, "confidence": 0.6},
                {"mutation": {"kind": "resource_change", "id": "fuel", "operation": "set", "value": "sufficient"}, "confidence": 0.5},
            ],
        })
        self.assertEqual(["TM-001", "TM-002", "TM-003", "TM-004"], [
            candidate.candidate_id for candidate in batch.candidates
        ])
        self.assertEqual("state_set", batch.candidates[0].mutation.kind)
        self.assertEqual("resource_change", batch.candidates[3].mutation.kind)
        rendered = render_adventure_turn_mutation_candidate_batch(batch, generation_id="TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertIn("TM-001 [state_set]", rendered)
        self.assertIn("Model-declared confidence (advisory)", rendered)
        self.assertIn("untrusted; not staged", rendered)

    def test_ordinary_event_data_cannot_enter_the_typed_mutation_path(self):
        with self.assertRaisesRegex(AdventureTurnMutationCandidateError, "payload is invalid"):
            parse_untrusted_adventure_turn_mutation_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "discovery", "summary": "A key is found.", "confidence": 0.9}],
            })

    def test_closed_flat_compatibility_form_and_no_change_result_are_safe(self):
        batch = parse_untrusted_adventure_turn_mutation_candidates({
            "schema_version": 1,
            "candidates": [{
                "kind": "state_set", "key": "current_location", "value": "engine room", "confidence": 0.8,
            }],
        })
        self.assertEqual("engine room", batch.candidates[0].mutation.state_value)
        no_change = parse_untrusted_adventure_turn_mutation_candidates({"schema_version": 1, "candidates": []})
        self.assertEqual((), no_change.candidates)
        self.assertIn(
            "provider proposed no durable typed changes",
            render_adventure_turn_mutation_candidate_batch(no_change),
        )
        with self.assertRaisesRegex(AdventureTurnMutationCandidateError, "payload fields"):
            parse_untrusted_adventure_turn_mutation_candidates({
                "schema_version": 1,
                "candidates": [{"mutation": {"kind": "discovery", "summary": "A key is found."}, "confidence": 0.9}],
            })

    def test_hidden_or_malformed_candidate_data_fails_closed(self):
        with self.assertRaisesRegex(AdventureTurnMutationCandidateError, "fields are invalid"):
            parse_untrusted_adventure_turn_mutation_candidates({
                "schema_version": 1,
                "candidates": [{
                    "mutation": {"kind": "state_set", "key": "location", "value": "deck"},
                    "confidence": 0.9,
                    "reasoning": "hidden",
                }],
            })

    def test_hidden_resource_candidate_can_be_redacted_at_presentation_boundary(self):
        batch = parse_untrusted_adventure_turn_mutation_candidates({
            "schema_version": 1,
            "candidates": [{
                "mutation": {"kind": "resource_change", "id": "primary_slot", "operation": "equip", "value": "brass key"},
                "confidence": 0.8,
            }],
        })
        rendered = render_adventure_turn_mutation_candidate_batch(
            batch, hidden_resource_ids=frozenset({"primary_slot"}),
        )
        self.assertIn("TM-001 [resource_change] Hidden resource change", rendered)
        self.assertNotIn("primary_slot", rendered)
        self.assertNotIn("brass key", rendered)
        with self.assertRaisesRegex(AdventureTurnMutationCandidateError, "between 0 and 1"):
            parse_untrusted_adventure_turn_mutation_candidates({
                "schema_version": 1,
                "candidates": [{
                    "mutation": {"kind": "state_set", "key": "location", "value": "deck"},
                    "confidence": 1.1,
                }],
            })
        with self.assertRaisesRegex(AdventureTurnMutationCandidateError, "payload fields"):
            parse_untrusted_adventure_turn_mutation_candidates({
                "schema_version": 1,
                "candidates": [{
                    "mutation": {"kind": "state_set", "key": "location", "value": "deck", "reasoning": "hidden"},
                    "confidence": 0.9,
                }],
            })

    def test_bounded_provenance_can_name_a_typed_candidate_without_widening_authority(self):
        provenance = AdventureTurnGenerationProvenance(
            "TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "adventure_turn_mutation_generation",
            "Ollama", "qwen3:8b", 2, (), "TM-001",
        )
        self.assertEqual("TM-001", provenance.candidate_id)


if __name__ == "__main__":
    unittest.main()
