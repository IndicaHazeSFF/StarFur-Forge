import unittest

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_replay import select_replay_spine


def event(sequence, event_type):
    return AdventureEvent(
        sequence=sequence,
        event_id=f"AE-{sequence:06d}",
        event_type=event_type,
        summary=f"Event {sequence}",
        details=None,
        recorded_at="2026-08-17T00:00:00+00:00",
    )


class AdventureReplayTests(unittest.TestCase):
    def test_spine_preserves_first_key_categories_and_recency_in_chronological_order(self):
        events = (
            event(1, "state_change"),
            event(2, "discovery"),
            event(3, "choice"),
            event(4, "discovery"),
            event(5, "promise"),
            event(6, "inventory_change"),
            event(7, "relationship_change"),
            event(8, "state_change"),
            event(9, "unresolved_hook"),
            event(10, "emotional_transition"),
        )
        spine = select_replay_spine(events, limit=5)

        self.assertEqual([1, 4, 5, 7, 9], [item.sequence for item in spine])
        self.assertEqual(spine, select_replay_spine(reversed(events), limit=5))

    def test_small_or_empty_logs_remain_unchanged(self):
        values = (event(1, "discovery"), event(2, "choice"))
        self.assertEqual((), select_replay_spine(()))
        self.assertEqual(values, select_replay_spine(values))

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            select_replay_spine((), limit=0)
        with self.assertRaises(TypeError):
            select_replay_spine(("not an event",))
        with self.assertRaises(ValueError):
            select_replay_spine((event(1, "discovery"), event(1, "choice")))


if __name__ == "__main__":
    unittest.main()
