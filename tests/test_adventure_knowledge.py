import unittest

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_knowledge import derive_adventure_knowledge, select_adventure_knowledge_context
from pipeline.adventure_mutation import AdventureEventEnvelope, AdventureMutation, MUTATION_KNOWLEDGE_SET


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

    def test_full_projection_is_not_truncated_by_bounded_context_selection(self):
        facts = derive_adventure_knowledge(tuple(
            event(index + 1, "character_knowledge", subject=f"Character {index:02}", status="knows", fact="the hatch is trapped")
            for index in range(13)
        ))

        self.assertEqual(13, len(facts))
        self.assertEqual(12, len(select_adventure_knowledge_context(facts)))
        self.assertEqual("Character 12", facts[-1].subject)
        self.assertNotIn("Character 12", [fact.subject for fact in select_adventure_knowledge_context(facts)])
        self.assertEqual((facts[0],), select_adventure_knowledge_context(facts, limit=1))
        self.assertEqual(13, len(facts))

    def test_superseded_knowledge_event_remains_in_history_but_not_current_projection(self):
        original = AdventureEvent.from_dict(AdventureEventEnvelope(
            sequence=1, event_id="AE-000001", event_type="character_knowledge",
            recorded_at="2026-08-21T00:00:00+00:00", summary="Rook believes the hatch is trapped.", details=None,
            mutation=AdventureMutation(
                MUTATION_KNOWLEDGE_SET, knowledge_subject="Rook", knowledge_status="believes",
                knowledge_fact="the hatch is trapped",
            ),
        ).to_dict())
        correction = AdventureEvent.from_dict(AdventureEventEnvelope(
            sequence=2, event_id="AE-000002", event_type="character_knowledge",
            recorded_at="2026-08-21T00:01:00+00:00", summary="Rook knows the hatch is trapped.", details=None,
            supersedes_event_id="AE-000001",
            mutation=AdventureMutation(
                MUTATION_KNOWLEDGE_SET, knowledge_subject="Rook", knowledge_status="knows",
                knowledge_fact="the hatch is trapped",
            ),
        ).to_dict())

        facts = derive_adventure_knowledge((original, correction))

        self.assertEqual(
            [("Rook", "knows", "the hatch is trapped", "AE-000002")],
            [(fact.subject, fact.status, fact.fact, fact.source_event_id) for fact in facts],
        )
        self.assertEqual("believes", original.knowledge_status)


if __name__ == "__main__":
    unittest.main()
