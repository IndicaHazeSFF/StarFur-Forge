import unittest

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_relationship import derive_adventure_relationships


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


if __name__ == "__main__":
    unittest.main()
