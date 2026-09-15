from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_status import ToolStatusSummary


class ToolStatusSummaryTests(unittest.TestCase):
    def test_empty_summary_is_bounded_and_session_ephemeral(self):
        self.assertEqual(ToolStatusSummary.empty().public_dict(), {
            "schema_version": 1,
            "total_count": 0,
            "pending_review_count": 0,
            "approved_count": 0,
            "queued_count": 0,
            "running_count": 0,
            "terminal_count": 0,
            "storage": "session_ephemeral",
        })

    def test_states_are_grouped_without_request_details(self):
        summary = ToolStatusSummary.from_states((
            "awaiting_approval", "approved", "queued", "running", "completed",
            "denied", "outcome_unknown",
        ))
        self.assertEqual(
            (7, 1, 1, 1, 1, 3),
            (
                summary.total_count, summary.pending_review_count,
                summary.approved_count, summary.queued_count,
                summary.running_count, summary.terminal_count,
            ),
        )
        rendered = repr(summary.public_dict()).casefold()
        for forbidden in ("invocation", "argument", "grant", "approval_id", "result", "path"):
            self.assertNotIn(forbidden, rendered)

    def test_invalid_or_excessive_states_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "invalid lifecycle"):
            ToolStatusSummary.from_states(("made_up",))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            ToolStatusSummary.from_states(("completed",) * 129)

    def test_summary_is_immutable_and_categories_must_balance(self):
        summary = ToolStatusSummary.empty()
        with self.assertRaises(FrozenInstanceError):
            summary.total_count = 1
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            ToolStatusSummary(1, 1, 0, 0, 0, 0, 0)


if __name__ == "__main__":
    unittest.main()
