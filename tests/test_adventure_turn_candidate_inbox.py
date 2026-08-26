import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_turn_candidate_inbox import (
    AdventureTurnCandidateInbox,
    AdventureTurnCandidateInboxError,
)
from pipeline.adventure_turn_candidates import parse_untrusted_adventure_turn_candidates
from pipeline.adventure_turn_generation import (
    AdventureTurnGenerationRequest,
    AdventureTurnGenerationResult,
)


class AdventureTurnCandidateInboxTests(unittest.TestCase):
    def test_inbox_is_workspace_bound_and_selection_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 25, tzinfo=UTC))
            quiet_ember = registry.create("Quiet Ember")
            other = registry.create("Other Ember")
            batch = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery",
                    "summary": "The crew finds a brass key.",
                    "confidence": 0.8,
                }],
            })
            result = AdventureTurnGenerationResult(
                AdventureTurnGenerationRequest(
                    quiet_ember, 3, "Location: chart room.", "I inspect the hatch.",
                    generation_id="TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ),
                batch,
            )
            inbox = AdventureTurnCandidateInbox.empty().present(result)

            selected = inbox.select(quiet_ember, "tc-001", event_count=3)

            self.assertEqual("TC-001", selected.candidate.candidate_id)
            self.assertEqual("TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", selected.generation_id)
            self.assertEqual("adventure_turn_generation", selected.provenance.task_id)
            self.assertEqual(3, selected.provenance.origin_event_count)
            self.assertEqual("TC-001", selected.provenance.candidate_id)
            self.assertEqual(batch, inbox.batch)
            with self.assertRaisesRegex(AdventureTurnCandidateInboxError, "another workspace"):
                inbox.select(other, "TC-001", event_count=3)
            with self.assertRaisesRegex(AdventureTurnCandidateInboxError, "not found"):
                inbox.select(quiet_ember, "TC-999", event_count=3)
            with self.assertRaisesRegex(AdventureTurnCandidateInboxError, "stale"):
                inbox.select(quiet_ember, "TC-001", event_count=4)
            self.assertFalse(inbox.clear().active)

    def test_empty_inbox_cannot_select_a_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 25, tzinfo=UTC)).create("Quiet Ember")
            with self.assertRaisesRegex(AdventureTurnCandidateInboxError, "no adventure-turn candidates"):
                AdventureTurnCandidateInbox.empty().select(record, "TC-001", event_count=0)

    def test_inbox_requires_one_trusted_generation_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 25, tzinfo=UTC)).create("Quiet Ember")
            batch = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "choice", "summary": "The crew waits.", "confidence": 0.6}],
            })
            with self.assertRaisesRegex(TypeError, "GenerationResult"):
                AdventureTurnCandidateInbox.empty().present(batch)
            request = AdventureTurnGenerationRequest(
                record, 2, "Location: chart room.", "I wait.",
                generation_id="TG-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            )
            inbox = AdventureTurnCandidateInbox.empty().present(AdventureTurnGenerationResult(request, batch))
            self.assertEqual(2, inbox.event_count)
            self.assertEqual(request.generation_id, inbox.generation_id)


if __name__ == "__main__":
    unittest.main()
