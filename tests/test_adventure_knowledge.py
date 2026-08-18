import unittest

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_knowledge import derive_adventure_knowledge


def event(sequence, event_type, *, subject=None, status=None, fact=None):
    return AdventureEvent(
        sequence=sequence, event_id=f"AE-{sequence:06d}", event_type=event_type,
        summary=f"Event {sequence}", details=None, recorded_at="2026-08-17T00:00:00+00:00",
        knowledge_subject=subject, knowledge_status=status, knowledge_fact=fact,
    )


class AdventureKnowledgeTests(unittest.TestCase):
    def test_latest_explicit_stance_replaces_only_same_character_fact(self):
        facts = derive_adventure_knowledge((
            event(1, "discovery"),
            event(2, "character_knowledge", subject="Vespera", status="knows", fact="The player has amnesia"),
            event(3, "character_knowledge", subject="Rook", status="believes", fact="The hatch is trapped"),
            event(4, "character_knowledge", subject="Vespera", status="uncertain", fact="The hatch is trapped"),
            event(5, "character_knowledge", subject="Rook", status="knows", fact="The hatch is trapped"),
        ))
        self.assertEqual(
            [
                ("Rook", "knows", "The hatch is trapped", "AE-000005"),
                ("Vespera", "uncertain", "The hatch is trapped", "AE-000004"),
                ("Vespera", "knows", "The player has amnesia", "AE-000002"),
            ],
            [(fact.subject, fact.status, fact.fact, fact.source_event_id) for fact in facts],
        )

    def test_invalid_structured_knowledge_is_rejected_at_event_boundary(self):
        with self.assertRaisesRegex(ValueError, "only for character_knowledge"):
            event(1, "discovery", subject="Vespera", status="knows", fact="A fact")
        with self.assertRaisesRegex(ValueError, "knowledge status"):
            event(1, "character_knowledge", subject="Vespera", status="guesses", fact="A fact")
        with self.assertRaises(TypeError):
            derive_adventure_knowledge(("not an event",))


if __name__ == "__main__":
    unittest.main()
