import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.resident_action import ResidentAction


class ResidentActionTests(unittest.TestCase):
    def test_idle_action_is_typed_public_and_restart_ephemeral(self):
        action = ResidentAction.idle("Murr")

        self.assertEqual(action.persona_id, "murr")
        self.assertEqual(action.public_dict(), {
            "kind": "idle", "source": "core_default", "storage": "restart_ephemeral",
        })

    def test_action_rejects_unknown_activity_or_authority_source(self):
        with self.assertRaisesRegex(ValueError, "kind"):
            ResidentAction("murr", "autonomous_world_takeover")
        with self.assertRaisesRegex(ValueError, "source"):
            ResidentAction("murr", "reading", "model_inference")


if __name__ == "__main__":
    unittest.main()
