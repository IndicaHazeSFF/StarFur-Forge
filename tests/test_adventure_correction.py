import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.adventure_correction import AdventureCorrectionError, resolve_active_adventure_events
from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_mutation import AdventureEventEnvelope


def _event(sequence, *, supersedes_event_id=None):
    """Build a validated v2 record because v1 intentionally has no supersession."""
    return AdventureEvent.from_dict(AdventureEventEnvelope(
        sequence=sequence,
        event_id=f"AE-{sequence:06d}",
        event_type="discovery",
        recorded_at="2026-08-21T12:00:00+00:00",
        summary=f"Event {sequence}.",
        details=None,
        supersedes_event_id=supersedes_event_id,
    ).to_dict())


class AdventureCorrectionTests(unittest.TestCase):
    def test_unsuperseded_records_remain_active_in_original_order(self):
        first, second = _event(1), _event(2)

        result = resolve_active_adventure_events((first, second))

        self.assertEqual((first, second), result.active_events)
        self.assertEqual(
            (("AE-000001", True, None), ("AE-000002", True, None)),
            tuple((item.event_id, item.active, item.superseded_by_event_id) for item in result.activities),
        )

    def test_correction_chain_leaves_only_the_latest_tip_active_without_deleting_history(self):
        first = _event(1)
        correction = _event(2, supersedes_event_id="AE-000001")
        final = _event(3, supersedes_event_id="AE-000002")

        result = resolve_active_adventure_events((first, correction, final))

        self.assertEqual((final,), result.active_events)
        self.assertEqual(
            (("AE-000001", False, "AE-000002"), ("AE-000002", False, "AE-000003"), ("AE-000003", True, None)),
            tuple((item.event_id, item.active, item.superseded_by_event_id) for item in result.activities),
        )

    def test_unknown_or_duplicate_supersession_fails_closed(self):
        with self.assertRaisesRegex(AdventureCorrectionError, "already exist"):
            resolve_active_adventure_events((_event(1, supersedes_event_id="AE-000099"),))

        first = _event(1)
        second = _event(2, supersedes_event_id="AE-000001")
        third = _event(3, supersedes_event_id="AE-000001")
        with self.assertRaisesRegex(AdventureCorrectionError, "only one correction"):
            resolve_active_adventure_events((first, second, third))


if __name__ == "__main__":
    unittest.main()
