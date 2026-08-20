import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from pipeline.persona_state import BehaviorContext, DynamicTraits, MomentaryState, PersonaState


class PersonaStateTests(unittest.TestCase):
    def test_valid_state_is_immutable_and_has_bounded_public_view(self):
        state = PersonaState(
            "murr", "Murr", "A warm fox companion.",
            DynamicTraits(warmth=0.9, humor=0.7),
            MomentaryState(energy=0.6, attention=0.8, valence=0.2, activity="chatting"),
        )
        context = BehaviorContext.from_persona_state(state)
        self.assertEqual(state.persona_id, "murr")
        self.assertEqual(context.public_dict()["momentary_state"]["activity"], "chatting")
        with self.assertRaises(AttributeError):
            state.display_name = "Other"

    def test_trait_and_momentary_bounds_are_validated(self):
        with self.assertRaisesRegex(ValueError, "warmth"):
            DynamicTraits(warmth=1.01)
        with self.assertRaisesRegex(TypeError, "attention"):
            MomentaryState(attention=True)
        with self.assertRaisesRegex(ValueError, "valence"):
            MomentaryState(valence=-1.1)
        with self.assertRaisesRegex(ValueError, "activity"):
            MomentaryState(activity=" ")

    def test_mapping_builders_reject_unknown_or_unvalidated_fields(self):
        self.assertEqual(DynamicTraits.from_mapping({"warmth": 0.7}).warmth, 0.7)
        self.assertEqual(MomentaryState.from_mapping({"activity": "reading"}).activity, "reading")
        with self.assertRaisesRegex(ValueError, "Unknown dynamic"):
            DynamicTraits.from_mapping({"mood": 0.2})
        with self.assertRaisesRegex(ValueError, "Unknown momentary"):
            MomentaryState.from_mapping({"secret": "no"})

    def test_persona_identity_and_nested_types_are_validated(self):
        with self.assertRaisesRegex(ValueError, "persona_id"):
            PersonaState("Murr Fox", "Murr", "Identity")
        with self.assertRaisesRegex(TypeError, "dynamic_traits"):
            PersonaState("murr", "Murr", "Identity", dynamic_traits={})
        with self.assertRaisesRegex(TypeError, "momentary_state"):
            BehaviorContext("murr", DynamicTraits(), {})


if __name__ == "__main__":
    unittest.main()