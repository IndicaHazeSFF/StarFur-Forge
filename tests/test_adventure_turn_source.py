from datetime import UTC, datetime
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_transcript import AdventureTranscriptRecord
from pipeline.adventure_turn_source import (
    AdventureTurnSourceError,
    select_latest_completed_transcript_turn,
)


def _record(sequence, role, text):
    return AdventureTranscriptRecord(
        sequence=sequence,
        record_id=f"AT-{sequence:06d}",
        role=role,
        text=text,
        recorded_at=datetime(2026, 8, 26, tzinfo=UTC).isoformat(),
    )


class AdventureTurnSourceTests(unittest.TestCase):
    def test_selects_only_the_latest_adjacent_explicit_user_narrator_pair(self):
        source = select_latest_completed_transcript_turn((
            _record(1, "user", "I turn the brass key."),
            _record(2, "narrator", "The hatch groans open."),
        ))

        self.assertEqual(("AT-000001", "AT-000002"), source.record_ids)
        self.assertEqual("I turn the brass key.", source.user_text)
        self.assertEqual("The hatch groans open.", source.narrator_text)

    def test_rejects_missing_or_nonadjacent_completed_pairs(self):
        with self.assertRaisesRegex(AdventureTurnSourceError, "no completed"):
            select_latest_completed_transcript_turn(())
        with self.assertRaisesRegex(AdventureTurnSourceError, "latest transcript"):
            select_latest_completed_transcript_turn((
                _record(1, "user", "I wait."), _record(2, "user", "I listen."),
            ))


if __name__ == "__main__":
    unittest.main()
