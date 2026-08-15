import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.emotion import EmotionSignal, derive_emotion_state
from pipeline.persona_state import MomentaryState


class EmotionDerivationTests(unittest.TestCase):
    def test_explicit_signals_derive_explainable_deterministic_state(self):
        signals = (
            EmotionSignal("ES-focus", "focused_work", 0.5, "system_activity"),
            EmotionSignal("ES-fatigue", "fatigue", 0.4, "explicit_user_statement"),
        )
        first = derive_emotion_state(signals, baseline=MomentaryState(activity="idle"), activity="chatting")
        second = derive_emotion_state(reversed(signals), baseline=MomentaryState(activity="idle"), activity="chatting")

        self.assertEqual(first, second)
        self.assertEqual(first.momentary_state.activity, "chatting")
        self.assertEqual(first.momentary_state.energy, 0.32)
        self.assertEqual(first.momentary_state.attention, 0.62)
        self.assertEqual(first.momentary_state.valence, -0.015)
        self.assertEqual([item.signal_id for item in first.contributions], ["ES-fatigue", "ES-focus"])

    def test_no_signals_preserves_baseline_without_mutating_it(self):
        baseline = MomentaryState(energy=0.7, attention=0.2, valence=-0.1, activity="reading")
        result = derive_emotion_state((), baseline=baseline)

        self.assertEqual(result.momentary_state, baseline)
        self.assertEqual(result.contributions, ())

    def test_clamps_and_rejects_implicit_or_unsafe_inputs(self):
        result = derive_emotion_state((
            EmotionSignal("ES-positive", "positive_interaction", 1.0, "approved_relationship_context"),
        ), baseline=MomentaryState(energy=1.0, attention=1.0, valence=0.9))
        self.assertEqual(result.momentary_state.energy, 1.0)
        self.assertEqual(result.momentary_state.attention, 1.0)
        self.assertEqual(result.momentary_state.valence, 1.0)

        with self.assertRaisesRegex(ValueError, "kind"):
            EmotionSignal("ES-unknown", "angry", 0.5, "system_activity")
        with self.assertRaisesRegex(ValueError, "source"):
            EmotionSignal("ES-source", "fatigue", 0.5, "ordinary_chat")
        signal = EmotionSignal("ES-repeat", "fatigue", 0.5, "system_activity")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            derive_emotion_state((signal, signal))


if __name__ == "__main__":
    unittest.main()
