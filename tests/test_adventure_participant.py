import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_initiative import AdventureInitiativeError, AdventureParticipant
from pipeline.adventure_knowledge import AdventureKnowledgeFact
from pipeline.adventure_participant import AdventureParticipantView
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_relationship import AdventureRelationshipFact
from pipeline.adventure_resource_state import AdventureResourceFact
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition
from pipeline.adventure_session import AdventureSessionState


class AdventureParticipantViewTests(unittest.TestCase):
    def _record(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return AdventureRegistry(directory.name, now=lambda: datetime(2026, 8, 27, tzinfo=UTC)).create("Quiet Ember")

    def test_view_exposes_only_participant_relevant_public_context(self):
        record = self._record()
        participant = AdventureParticipant(
            "vespera", "Vespera", "npc", f"adventure:{record.adventure_id}:participant:vespera",
        )
        event = AdventureEvent(1, "AE-000001", "discovery", "The crew finds a brass key.", None, "2026-08-27T00:00:00+00:00")
        vespera_relationship = AdventureRelationshipFact("Vespera", "trust", "cautious", "AE-000002")
        rook_relationship = AdventureRelationshipFact("Rook", "suspicion", "high", "AE-000003")
        vespera_knowledge = AdventureKnowledgeFact("Vespera", "believes", "the hatch is trapped", "AE-000004")
        rook_knowledge = AdventureKnowledgeFact("Rook", "believes", "the key is cursed", "AE-000005")
        fuel = AdventureResourceFact("fuel", "Fuel", "integer", 20, "public", "AE-000006")
        hidden = AdventureResourceFact("primary_slot", "Primary slot", "equipment", "captain token", "hidden", "AE-000007")
        session = AdventureSessionState(
            record=record, event_count=7, context_events=(event,),
            relationship_facts=(vespera_relationship, rook_relationship),
            context_relationship_facts=(vespera_relationship, rook_relationship),
            knowledge_facts=(vespera_knowledge, rook_knowledge),
            context_knowledge_facts=(vespera_knowledge, rook_knowledge),
            resource_catalog=AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
                AdventureResourceDefinition("primary_slot", "Primary slot", "equipment", visibility="hidden"),
            )),
            resource_facts=(fuel, hidden), context_resource_facts=(fuel,),
        )

        view = AdventureParticipantView.from_session(session, participant)
        rendered = view.render()

        self.assertEqual(("The crew finds a brass key.",), view.events)
        self.assertEqual((vespera_relationship,), view.relationships)
        self.assertEqual((vespera_knowledge,), view.knowledge)
        self.assertEqual((fuel,), view.public_resources)
        self.assertIn("trust: cautious", rendered)
        self.assertIn("believes: the hatch is trapped", rendered)
        self.assertNotIn("Rook", rendered)
        self.assertNotIn("primary_slot", rendered)
        self.assertNotIn("captain token", rendered)

    def test_view_rejects_unmounted_or_cross_adventure_participant_namespace(self):
        record = self._record()
        participant = AdventureParticipant(
            "vespera", "Vespera", "npc", "adventure:another-world:participant:vespera",
        )
        with self.assertRaisesRegex(AdventureInitiativeError, "mounted"):
            AdventureParticipantView.from_session(AdventureSessionState.unmounted(), participant)
        with self.assertRaisesRegex(AdventureInitiativeError, "does not match"):
            AdventureParticipantView.from_session(AdventureSessionState(record=record), participant)


if __name__ == "__main__":
    unittest.main()
