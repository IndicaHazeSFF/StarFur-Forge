import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_relationship import AdventureRelationshipFact
from pipeline.adventure_resource_state import AdventureResourceFact
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition
from pipeline.adventure_session import AdventureSessionState
from pipeline.adventure_turn_context import AdventureTurnContextView
from pipeline.adventure_turn_generation import AdventureTurnGenerationRequest


class AdventureTurnContextViewTests(unittest.TestCase):
    def _record(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return AdventureRegistry(directory.name, now=lambda: datetime(2026, 8, 26, tzinfo=UTC)).create("Quiet Ember")

    def test_view_uses_bounded_session_facts_and_never_exposes_hidden_or_numeric_relationship_values(self):
        record = self._record()
        event = AdventureEvent(1, "AE-000001", "discovery", "The crew finds a brass key.", None, "2026-08-26T00:00:00+00:00")
        relationship = AdventureRelationshipFact("Vespera", "trust", "49/100", "AE-000002")
        public = AdventureResourceFact("fuel", "Fuel", "integer", 20, "public", "AE-000003")
        hidden = AdventureResourceFact("primary_slot", "Primary slot", "equipment", "captain token", "hidden", "AE-000004")
        state = AdventureSessionState(
            record=record, event_count=4, context_events=(event,),
            relationship_facts=(relationship,), context_relationship_facts=(relationship,),
            resource_catalog=AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
                AdventureResourceDefinition("primary_slot", "Primary slot", "equipment", visibility="hidden"),
            )),
            resource_facts=(public, hidden), context_resource_facts=(public,),
        )

        view = AdventureTurnContextView.from_session(state)
        rendered = view.render()

        self.assertEqual(record.adventure_id, view.adventure_id)
        self.assertIn("The crew finds a brass key", rendered)
        self.assertIn("fuel (Fuel): 20", rendered)
        self.assertIn("qualitative internal state", rendered)
        self.assertNotIn("49/100", rendered)
        self.assertNotIn("primary_slot", rendered)
        self.assertNotIn("captain token", rendered)

    def test_view_rejects_unmounted_session_and_generation_request_uses_its_origin(self):
        with self.assertRaisesRegex(ValueError, "mounted"):
            AdventureTurnContextView.from_session(AdventureSessionState.unmounted())

        record = self._record()
        view = AdventureTurnContextView.from_session(AdventureSessionState(record=record, event_count=0))
        request = AdventureTurnGenerationRequest.from_context_view(
            view, user_text="I inspect the hatch.", generation_id="TG-dddddddddddddddddddddddddddddddd",
        )

        self.assertEqual(record, request.record)
        self.assertEqual(0, request.event_count)
        self.assertIn("ADVENTURE TURN CORE CONTEXT", request.authoritative_context)
        with self.assertRaisesRegex(TypeError, "context view"):
            AdventureTurnGenerationRequest.from_context_view(object(), user_text="Turn")


if __name__ == "__main__":
    unittest.main()
