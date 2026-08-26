import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_turn_candidates import parse_untrusted_adventure_turn_candidates
from pipeline.adventure_turn_generation import AdventureTurnGenerationRequest, AdventureTurnGenerationResult


class AdventureTurnGenerationRequestTests(unittest.TestCase):
    def test_request_renders_bounded_authoritative_and_untrusted_turn_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 26, tzinfo=UTC)).create("Quiet Ember")
            request = AdventureTurnGenerationRequest(
                record=record,
                event_count=3,
                authoritative_context="Current location: chart room.",
                user_text="I open the brass hatch.",
                narrator_text="The latch gives way with a groan.",
            )
            system, source = request.messages()

            self.assertEqual("system", system["role"])
            self.assertIn("Return JSON only", system["content"])
            self.assertIn("untrusted proposal", system["content"])
            self.assertIn("AUTHORITATIVE CORE CONTEXT", source["content"])
            self.assertIn("USER TURN TEXT (untrusted source)", source["content"])
            self.assertIn("NARRATOR TURN TEXT (untrusted source)", source["content"])
            self.assertRegex(request.generation_id, r"^TG-[0-9a-f]{32}$")

    def test_request_retains_only_validated_explicit_transcript_record_references(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 26, tzinfo=UTC)).create("Quiet Ember")
            request = AdventureTurnGenerationRequest(
                record, 0, "Context", "I open the hatch.", "The hatch opens.",
                source_record_ids=("AT-000001", "AT-000002"),
            )
            self.assertEqual(("AT-000001", "AT-000002"), request.source_record_ids)
            self.assertEqual("adventure_turn_generation", request.provenance.task_id)
            self.assertEqual("unconfigured", request.provenance.provider_name)
            self.assertEqual(("AT-000001", "AT-000002"), request.provenance.source_record_ids)
            self.assertIsNone(request.provenance.candidate_id)
            with self.assertRaisesRegex(ValueError, "source record"):
                AdventureTurnGenerationRequest(record, 0, "Context", "I wait.", source_record_ids=("",))

    def test_result_binds_validated_candidates_to_the_original_request(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 26, tzinfo=UTC)).create("Quiet Ember")
            request = AdventureTurnGenerationRequest(
                record, 2, "Location: chart room.", "I open the hatch.",
                generation_id="TG-cccccccccccccccccccccccccccccccc",
            )
            batch = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "discovery", "summary": "The hatch opens.", "confidence": 0.8}],
            })
            result = AdventureTurnGenerationResult(request, batch)
            self.assertEqual(request.generation_id, result.generation_id)
            with self.assertRaisesRegex(TypeError, "result request"):
                AdventureTurnGenerationResult(object(), batch)

    def test_request_rejects_empty_or_oversized_untrusted_turn_text(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 26, tzinfo=UTC)).create("Quiet Ember")
            with self.assertRaisesRegex(ValueError, "user text"):
                AdventureTurnGenerationRequest(record, 0, "Context", "")
            with self.assertRaisesRegex(ValueError, "authoritative context"):
                AdventureTurnGenerationRequest(record, 0, "x" * 16_001, "Turn")


if __name__ == "__main__":
    unittest.main()
