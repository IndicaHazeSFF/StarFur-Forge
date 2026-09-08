import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_audit import ToolAuditLog


class ToolAuditTests(unittest.TestCase):
    def test_log_is_bounded_ordered_and_contains_no_payload_fields(self):
        audit = ToolAuditLog(maximum_events=2, clock=lambda: 1000.0)
        audit.append("TI-one", "sandbox.run", "proposed", "proposal_validated")
        audit.append("TI-one", "sandbox.run", "awaiting_approval", "approval_required")
        audit.append("TI-two", "sandbox.run", "cancelled", "cancelled")

        events = audit.events()
        self.assertEqual((2, 3), tuple(item.sequence for item in events))
        public = audit.public_dict()
        self.assertEqual("session_ephemeral", public["storage"])
        rendered = repr(public).casefold()
        for forbidden in ("arguments", "prompt", "stdout", "stderr", "provider_payload"):
            self.assertNotIn(forbidden, rendered)

    def test_public_limit_is_explicit(self):
        audit = ToolAuditLog()
        with self.assertRaisesRegex(ValueError, "public"):
            audit.public_dict(maximum_events=65)
        self.assertEqual([], audit.public_dict(maximum_events=0)["events"])


if __name__ == "__main__":
    unittest.main()
