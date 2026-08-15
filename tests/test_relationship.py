import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.relationship import RelationshipSignal, RelationshipState, derive_relationship_state


class RelationshipStateTests(unittest.TestCase):
    def _baseline(self):
        return RelationshipState("murr", "user", familiarity=0.2, trust=0.5, confidence=0.1)

    def test_explicit_signals_are_deterministic_explainable_and_non_mutating(self):
        signals = (
            RelationshipSignal("RS-boundary", "boundary_respected", 0.5, "explicit_user_statement"),
            RelationshipSignal("RS-familiar", "familiar_interaction", 0.5, "approved_relationship_context"),
        )
        baseline = self._baseline()
        first = derive_relationship_state(signals, baseline=baseline)
        second = derive_relationship_state(reversed(signals), baseline=baseline)

        self.assertEqual(first, second)
        self.assertEqual(baseline, self._baseline())
        self.assertEqual(first.state.familiarity, 0.2829)
        self.assertEqual(first.state.trust, 0.5492)
        self.assertEqual(first.state.confidence, 0.1707)
        self.assertEqual([item.signal_id for item in first.contributions], ["RS-boundary", "RS-familiar"])

    def test_state_asymptotes_and_trust_breach_is_bounded(self):
        near_max = RelationshipState("murr", "user", familiarity=0.9998, trust=0.9998, confidence=0.9998)
        raised = derive_relationship_state((
            RelationshipSignal("RS-positive", "positive_interaction", 0.9999, "approved_memory_context"),
        ), baseline=near_max)
        self.assertLess(raised.state.familiarity, 1.0)
        self.assertLess(raised.state.trust, 1.0)
        self.assertLess(raised.state.confidence, 1.0)

        harmed = derive_relationship_state((
            RelationshipSignal("RS-breach", "trust_breach", 0.9, "explicit_user_correction"),
        ), baseline=self._baseline())
        self.assertGreaterEqual(harmed.state.trust, 0.0)
        self.assertLess(harmed.state.trust, self._baseline().trust)

    def test_invalid_or_duplicate_signals_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "up to but not including"):
            RelationshipState("murr", "user", trust=1.0)
        with self.assertRaisesRegex(ValueError, "kind"):
            RelationshipSignal("RS-kind", "resentment", 0.5, "explicit_user_statement")
        with self.assertRaisesRegex(ValueError, "source"):
            RelationshipSignal("RS-source", "positive_interaction", 0.5, "ordinary_chat")
        signal = RelationshipSignal("RS-repeat", "positive_interaction", 0.5, "explicit_user_statement")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            derive_relationship_state((signal, signal), baseline=self._baseline())


if __name__ == "__main__":
    unittest.main()
