import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.resident_presentation import ResidentPresentationPlan


class ResidentPresentationTests(unittest.TestCase):
    def test_public_activity_maps_to_stable_generic_asset_slots(self):
        plan = ResidentPresentationPlan.from_resident_snapshot({
            "activity": "generating", "persona": {"persona_id": "murr"},
        })

        self.assertEqual(plan.public_dict(), {
            "visual_state": "thinking",
            "activity_label": "Thinking",
            "scene_cue": "A provider turn is in progress.",
            "actor_slot": "resident.murr",
            "animation_slot": "resident.murr.thinking",
            "scene_slot": "apartment.default",
            "storage": "presentation_ephemeral",
        })

    def test_invalid_or_private_snapshot_fields_do_not_be_interpreted(self):
        with self.assertRaisesRegex(ValueError, "activity"):
            ResidentPresentationPlan.from_resident_snapshot({"activity": "making_up_a_state"})
        plan = ResidentPresentationPlan.from_resident_snapshot({
            "activity": "provider_unavailable",
            "persona": {"persona_id": "nova", "static_identity": "private prompt"},
            "raw_memories": ["private"],
        })
        self.assertEqual(plan.public_dict()["animation_slot"], "resident.nova.offline")

    def test_explicit_resident_action_can_only_shape_an_idle_visual(self):
        idle = ResidentPresentationPlan.from_resident_snapshot({
            "activity": "idle", "persona": {"persona_id": "murr", "resident_action": {"kind": "reading"}},
        })
        busy = ResidentPresentationPlan.from_resident_snapshot({
            "activity": "generating", "persona": {"persona_id": "murr", "resident_action": {"kind": "reading"}},
        })

        self.assertEqual(idle.public_dict()["animation_slot"], "resident.murr.reading")
        self.assertEqual(idle.public_dict()["activity_label"], "Reading")
        self.assertEqual(idle.public_dict()["scene_cue"], "A quiet reading cue.")
        self.assertEqual(busy.public_dict()["animation_slot"], "resident.murr.thinking")
        self.assertEqual(busy.public_dict()["activity_label"], "Thinking")


if __name__ == "__main__":
    unittest.main()
