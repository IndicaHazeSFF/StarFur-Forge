import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_turn_mutation_candidate_inbox import (
    AdventureTurnMutationCandidateInbox,
    AdventureTurnMutationCandidateInboxError,
)
from pipeline.adventure_turn_mutation_candidates import parse_untrusted_adventure_turn_mutation_candidates
from pipeline.adventure_turn_provenance import AdventureTurnGenerationProvenance


class AdventureTurnMutationCandidateInboxTests(unittest.TestCase):
    def test_inbox_is_workspace_bound_and_selection_remains_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 26, tzinfo=UTC))
            quiet_ember = registry.create("Quiet Ember")
            other = registry.create("Other Ember")
            batch = parse_untrusted_adventure_turn_mutation_candidates({
                "schema_version": 1,
                "candidates": [{
                    "mutation": {"kind": "state_set", "key": "current_location", "value": "engine room"},
                    "confidence": 0.8,
                }],
            })
            provenance = AdventureTurnGenerationProvenance(
                "TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "adventure_turn_mutation_generation",
                "Ollama", "qwen3:8b", 3,
            )
            inbox = AdventureTurnMutationCandidateInbox.empty().present(
                record=quiet_ember, batch=batch, event_count=3, provenance=provenance,
            )

            selected = inbox.select(quiet_ember, "tm-001", event_count=3)

            self.assertEqual("TM-001", selected.candidate.candidate_id)
            self.assertEqual("state_set", selected.candidate.mutation.kind)
            self.assertEqual("TM-001", selected.provenance.candidate_id)
            self.assertEqual(batch, inbox.batch)
            with self.assertRaisesRegex(AdventureTurnMutationCandidateInboxError, "another workspace"):
                inbox.select(other, "TM-001", event_count=3)
            with self.assertRaisesRegex(AdventureTurnMutationCandidateInboxError, "stale"):
                inbox.select(quiet_ember, "TM-001", event_count=4)
            self.assertFalse(inbox.clear().active)

    def test_active_inbox_requires_unselected_matching_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory).create("Quiet Ember")
            batch = parse_untrusted_adventure_turn_mutation_candidates({
                "schema_version": 1,
                "candidates": [{
                    "mutation": {"kind": "state_set", "key": "weather", "value": "rain"},
                    "confidence": 0.7,
                }],
            })
            selected = AdventureTurnGenerationProvenance(
                "TG-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "adventure_turn_mutation_generation",
                "Ollama", "qwen3:8b", 0, (), "TM-001",
            )
            with self.assertRaisesRegex(AdventureTurnMutationCandidateInboxError, "name no candidate"):
                AdventureTurnMutationCandidateInbox.empty().present(
                    record=record, batch=batch, event_count=0, provenance=selected,
                )


if __name__ == "__main__":
    unittest.main()
