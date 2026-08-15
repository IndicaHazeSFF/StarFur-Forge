import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.behavior import derive_behavior_guidance
from pipeline.persona_state import BehaviorContext, DynamicTraits, MomentaryState, PersonaState


class BehaviorGuidanceTests(unittest.TestCase):
    def _context(self, *, energy=0.5, attention=0.5, valence=0.0):
        return BehaviorContext.from_persona_state(PersonaState(
            "murr", "Murr", "Identity",
            DynamicTraits(warmth=0.8, directness=0.4, humor=0.6, initiative=0.5, patience=0.7, verbosity=0.5),
            MomentaryState(energy=energy, attention=attention, valence=valence, activity="chatting"),
        ))

    def test_guidance_is_deterministic_bounded_and_presentation_only(self):
        context = self._context(energy=0.2, attention=0.25, valence=-0.5)
        first = derive_behavior_guidance(context)
        second = derive_behavior_guidance(context)

        self.assertEqual(first, second)
        self.assertEqual(first.activity, "chatting")
        self.assertLess(first.warmth, 0.8)
        self.assertGreater(first.patience, 0.7)
        self.assertGreater(first.clarification_threshold, 0.25)
        self.assertEqual(context.momentary_state.energy, 0.2)

    def test_positive_and_high_energy_state_nudges_but_never_reaches_one(self):
        guidance = derive_behavior_guidance(self._context(energy=1.0, attention=1.0, valence=1.0))

        self.assertGreater(guidance.warmth, 0.8)
        self.assertGreater(guidance.humor, 0.6)
        self.assertGreater(guidance.verbosity, 0.5)
        self.assertTrue(all(value < 1.0 for value in guidance.public_dict().values() if isinstance(value, float)))

    def test_invalid_context_is_rejected(self):
        with self.assertRaisesRegex(TypeError, "BehaviorContext"):
            derive_behavior_guidance({})


if __name__ == "__main__":
    unittest.main()
