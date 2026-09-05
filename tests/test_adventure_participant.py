import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_initiative import AdventureInitiativeError, AdventureParticipant, AdventureParticipantMemoryPolicy
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

    def test_view_filters_private_event_summaries_before_bounding_and_redacts_numeric_meter(self):
        record = self._record()
        participant = AdventureParticipant(
            "vespera", "Vespera", "npc", f"adventure:{record.adventure_id}:participant:vespera",
            AdventureParticipantMemoryPolicy(max_context_facts=1),
        )
        rook_knowledge = AdventureEvent(
            1, "AE-000001", "character_knowledge", "Rook believes the captain is a traitor.", None,
            "2026-08-27T00:00:00+00:00", knowledge_subject="Rook", knowledge_status="believes",
            knowledge_fact="the captain is a traitor",
        )
        numeric_relationship = AdventureEvent(
            2, "AE-000002", "relationship_change", "Vespera trust is 49 out of 100.", None,
            "2026-08-27T00:00:00+00:00", relationship_subject="Vespera", relationship_dimension="trust",
            relationship_value="49/100",
        )
        discovery = AdventureEvent(
            3, "AE-000003", "discovery", "The crew finds a brass key.", None,
            "2026-08-27T00:00:00+00:00",
        )
        relationship = AdventureRelationshipFact("Vespera", "trust", "49/100", "AE-000002")
        session = AdventureSessionState(
            record=record, event_count=3, context_events=(rook_knowledge, numeric_relationship, discovery),
            relationship_facts=(relationship,), context_relationship_facts=(relationship,),
        )

        view = AdventureParticipantView.from_session(session, participant)
        rendered = view.render()

        # Typed perspective events never enter the generic event summary
        # channel. The private Rook event is excluded before the one-event
        # participant budget is applied; the shared discovery fills it. The
        # subject-owned relationship remains visible as a qualitative
        # projection, never as a raw numeric meter.
        self.assertEqual(("The crew finds a brass key.",), view.events)
        self.assertNotIn("Rook", rendered)
        self.assertNotIn("49", rendered)
        self.assertIn("qualitative internal state", rendered)

    def test_view_honors_memory_policy_when_salient_events_are_disabled(self):
        record = self._record()
        participant = AdventureParticipant(
            "vespera", "Vespera", "npc", f"adventure:{record.adventure_id}:participant:vespera",
            AdventureParticipantMemoryPolicy(retain_salient_events=False),
        )
        event = AdventureEvent(1, "AE-000001", "discovery", "The crew finds a brass key.", None, "2026-08-27T00:00:00+00:00")
        view = AdventureParticipantView.from_session(
            AdventureSessionState(record=record, event_count=1, context_events=(event,)), participant,
        )
        self.assertEqual((), view.events)


if __name__ == "__main__":
    unittest.main()
