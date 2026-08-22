import unittest

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_mutation import AdventureEventEnvelope, AdventureMutation, MUTATION_RELATIONSHIP_SET
from pipeline.adventure_relationship import (
    derive_adventure_relationships,
    select_adventure_relationship_context,
)


def event(sequence, event_type, *, subject=None, dimension=None, value=None):
    return AdventureEvent(
        sequence=sequence, event_id=f"AE-{sequence:06d}", event_type=event_type,
        summary=f"Event {sequence}", details=None, recorded_at="2026-08-17T00:00:00+00:00",
        relationship_subject=subject, relationship_dimension=dimension, relationship_value=value,
    )


class AdventureRelationshipTests(unittest.TestCase):
    def test_latest_explicit_qualitative_value_wins_per_character_and_dimension(self):
        facts = derive_adventure_relationships((
            event(1, "discovery"),
            event(2, "relationship_change", subject="Vespera", dimension="trust", value="guarded"),
            event(3, "relationship_change", subject="Vespera", dimension="comfort", value="relaxed"),
            event(4, "relationship_change", subject="Vespera", dimension="trust", value="cautious"),
            event(5, "relationship_change", subject="Rook", dimension="suspicion", value="high"),
        ))
        self.assertEqual(
            [
                ("Rook", "suspicion", "high", "AE-000005"),
                ("Vespera", "comfort", "relaxed", "AE-000003"),
                ("Vespera", "trust", "cautious", "AE-000004"),
            ],
            [(fact.subject, fact.dimension, fact.value, fact.source_event_id) for fact in facts],
        )

    def test_invalid_structured_relationship_is_rejected_at_event_boundary(self):
        with self.assertRaisesRegex(ValueError, "only for relationship_change"):
            event(1, "discovery", subject="Vespera", dimension="trust", value="cautious")
        with self.assertRaisesRegex(ValueError, "relationship dimension"):
            event(1, "relationship_change", subject="Vespera", dimension="Trust Level", value="cautious")
        with self.assertRaises(TypeError):
            derive_adventure_relationships(("not an event",))

    def test_full_projection_is_not_truncated_by_bounded_context_selection(self):
        facts = derive_adventure_relationships(tuple(
            event(index + 1, "relationship_change", subject=f"Character {index:02}", dimension="trust", value="guarded")
            for index in range(13)
        ))

        self.assertEqual(13, len(facts))
        self.assertEqual(12, len(select_adventure_relationship_context(facts)))
        self.assertEqual("Character 12", facts[-1].subject)
        self.assertNotIn("Character 12", [fact.subject for fact in select_adventure_relationship_context(facts)])
        self.assertEqual((facts[0],), select_adventure_relationship_context(facts, limit=1))
        self.assertEqual(13, len(facts))

    def test_superseded_relationship_event_remains_in_history_but_not_current_projection(self):
        original = AdventureEvent.from_dict(AdventureEventEnvelope(
            sequence=1, event_id="AE-000001", event_type="relationship_change",
            recorded_at="2026-08-21T00:00:00+00:00", summary="Vespera is guarded.", details=None,
            mutation=AdventureMutation(
                MUTATION_RELATIONSHIP_SET, relationship_subject="Vespera",
                relationship_dimension="trust", relationship_value="guarded",
            ),
        ).to_dict())
        correction = AdventureEvent.from_dict(AdventureEventEnvelope(
            sequence=2, event_id="AE-000002", event_type="relationship_change",
            recorded_at="2026-08-21T00:01:00+00:00", summary="Vespera is cautious.", details=None,
            supersedes_event_id="AE-000001",
            mutation=AdventureMutation(
                MUTATION_RELATIONSHIP_SET, relationship_subject="Vespera",
                relationship_dimension="trust", relationship_value="cautious",
            ),
        ).to_dict())

        facts = derive_adventure_relationships((original, correction))

        self.assertEqual(
            [("Vespera", "trust", "cautious", "AE-000002")],
            [(fact.subject, fact.dimension, fact.value, fact.source_event_id) for fact in facts],
        )
        self.assertEqual("guarded", original.relationship_value)


if __name__ == "__main__":
    unittest.main()
