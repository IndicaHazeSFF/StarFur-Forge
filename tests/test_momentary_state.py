import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.momentary_state import MomentaryTransitionPolicy, transition_momentary_state
from pipeline.persona_state import MomentaryState


class MomentaryStateTransitionTests(unittest.TestCase):
    def test_half_life_decay_is_deterministic_and_explainable(self):
        previous = MomentaryState(energy=0.1, attention=0.9, valence=0.8, activity="working")
        candidate = MomentaryState(activity="idle")
        result = transition_momentary_state(
            previous, candidate, elapsed_seconds=60,
            policy=MomentaryTransitionPolicy(half_life_seconds=60, min_change=0.0, max_step=1.0),
        )

        self.assertEqual(result.decay_retention, 0.5)
        self.assertEqual(result.state.energy, 0.5)
        self.assertEqual(result.state.attention, 0.5)
        self.assertEqual(result.state.valence, 0.0)
        self.assertEqual(result.state.activity, "idle")
        self.assertEqual(result.applied_fields, ("attention", "energy", "valence"))
        self.assertEqual(previous.activity, "working")

    def test_hysteresis_holds_tiny_candidate_changes_after_decay(self):
        previous = MomentaryState(energy=0.5, attention=0.5, valence=0.0, activity="reading")
        candidate = MomentaryState(energy=0.51, attention=0.49, valence=0.01, activity="chatting")
        result = transition_momentary_state(
            previous, candidate, elapsed_seconds=0,
            policy=MomentaryTransitionPolicy(min_change=0.02, max_step=0.25),
        )

        self.assertEqual(result.state, previous)
        self.assertEqual(result.applied_fields, ())
        self.assertEqual(result.held_fields, ("attention", "energy", "valence"))

    def test_large_changes_are_rate_limited_and_invalid_input_is_rejected(self):
        result = transition_momentary_state(
            MomentaryState(), MomentaryState(energy=0.0, attention=1.0, valence=1.0, activity="chatting"),
            elapsed_seconds=0, policy=MomentaryTransitionPolicy(min_change=0.01, max_step=0.1),
        )
        self.assertEqual(result.state.energy, 0.4)
        self.assertEqual(result.state.attention, 0.6)
        self.assertEqual(result.state.valence, 0.1)

        with self.assertRaisesRegex(ValueError, "half_life_seconds"):
            MomentaryTransitionPolicy(half_life_seconds=0)
        with self.assertRaisesRegex(ValueError, "elapsed_seconds"):
            transition_momentary_state(MomentaryState(), MomentaryState(), elapsed_seconds=-1)


if __name__ == "__main__":
    unittest.main()
