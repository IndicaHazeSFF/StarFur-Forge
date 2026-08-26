import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_turn_context import AdventureTurnContextView
from pipeline.adventure_turn_mutation_generation import AdventureTurnMutationGenerationRequest
from pipeline.task_profiles import TASK_ADVENTURE_TURN_MUTATION_GENERATION


class AdventureTurnMutationGenerationTests(unittest.TestCase):
    def test_request_has_its_own_closed_schema_and_task_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 26, tzinfo=UTC)).create("Quiet Ember")
            request = AdventureTurnMutationGenerationRequest(
                record, 2, "Location: chart room.", "I open the hatch.",
                narrator_text="The hatch groans open.",
                generation_id="TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )
            messages = request.messages()

            self.assertEqual(TASK_ADVENTURE_TURN_MUTATION_GENERATION, request.task_id)
            self.assertIn('"mutation"', messages[0]["content"])
            self.assertIn("state_set", messages[0]["content"])
            self.assertIn("ordinary events", messages[0]["content"])
            self.assertIn("The hatch groans open.", messages[1]["content"])
            self.assertEqual(request.generation_id, request.provenance.generation_id)

    def test_context_factory_requires_the_existing_bounded_context_view(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 26, tzinfo=UTC))
            record = registry.create("Quiet Ember")
            view = AdventureTurnContextView(record, 0, ())
            request = AdventureTurnMutationGenerationRequest.from_context_view(
                view, user_text="I inspect the hatch.", generation_id="TG-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            )
            self.assertEqual(record, request.record)
            with self.assertRaisesRegex(TypeError, "context view"):
                AdventureTurnMutationGenerationRequest.from_context_view(object(), user_text="Nope")


if __name__ == "__main__":
    unittest.main()
