import unittest

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_state import derive_adventure_state, select_adventure_state_context


def event(sequence, event_type, *, key=None, value=None):
    return AdventureEvent(
        sequence=sequence, event_id=f"AE-{sequence:06d}", event_type=event_type,
        summary=f"Event {sequence}", details=None, recorded_at="2026-08-17T00:00:00+00:00",
        state_key=key, state_value=value,
    )


class AdventureStateTests(unittest.TestCase):
    def test_latest_explicit_state_value_wins_without_parsing_prose(self):
        facts = derive_adventure_state((
            event(1, "discovery"),
            event(2, "state_change", key="location", value="bridge"),
            event(3, "state_change", key="objective", value="open the hatch"),
            event(4, "state_change", key="location", value="engine room"),
        ))
        self.assertEqual(
            [("location", "engine room", "AE-000004"), ("objective", "open the hatch", "AE-000003")],
            [(fact.key, fact.value, fact.source_event_id) for fact in facts],
        )

    def test_invalid_structured_state_is_rejected_at_event_boundary(self):
        with self.assertRaisesRegex(ValueError, "only for state_change"):
            event(1, "discovery", key="location", value="bridge")
        with self.assertRaisesRegex(ValueError, "state key"):
            event(1, "state_change", key="Current Location", value="bridge")
        with self.assertRaises(TypeError):
            derive_adventure_state(("not an event",))

    def test_full_projection_is_not_truncated_by_bounded_context_selection(self):
        facts = derive_adventure_state(tuple(
            event(index + 1, "state_change", key=f"fact_{index:02}", value=f"value {index}")
            for index in range(13)
        ))

        self.assertEqual(13, len(facts))
        self.assertEqual(12, len(select_adventure_state_context(facts)))
        self.assertEqual("fact_12", facts[-1].key)
        self.assertNotIn("fact_12", [fact.key for fact in select_adventure_state_context(facts)])
        self.assertEqual((facts[0],), select_adventure_state_context(facts, limit=1))
        self.assertEqual(13, len(facts))


if __name__ == "__main__":
    unittest.main()
