import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.persona_development import (
    InterestRecord,
    PersonaDevelopmentRegistry,
    PersonaDevelopmentState,
    SkillRecord,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


class PersonaDevelopmentTests(unittest.TestCase):
    def test_interest_and_skill_state_is_namespaced_and_immutable(self):
        murr = PersonaDevelopmentState.empty("murr")
        murr = murr.record_interest("Rust programming", observed_at=NOW, strength=0.2)
        murr = murr.record_verified_skill("Python", verified_at=NOW, strength=0.3)
        other = PersonaDevelopmentState.empty("other").record_interest(
            "Rust programming", observed_at=NOW, strength=0.2,
        )

        self.assertEqual(murr.persona_id, "murr")
        self.assertEqual(murr.interests[0].concept, "Rust programming")
        self.assertEqual(murr.skills[0].concept, "Python")
        self.assertEqual(other.persona_id, "other")
        self.assertEqual(len(other.skills), 0)
        with self.assertRaises(AttributeError):
            murr.persona_id = "other"

    def test_confidence_decays_deterministically_and_never_reaches_one(self):
        record = InterestRecord(
            "Rust", confidence=0.8, evidence_count=2,
            last_evidence_at=NOW, half_life_days=10,
        )

        self.assertEqual(record.confidence_at(NOW + timedelta(days=10)), 0.4)
        state = PersonaDevelopmentState.empty("murr")
        for _ in range(50):
            state = state.record_interest("Rust", observed_at=NOW, strength=0.5)
        reinforced = state.interests[0]
        self.assertLess(reinforced.confidence, 1.0)
        self.assertEqual(reinforced.evidence_count, 50)

    def test_reinforcement_preserves_concept_and_supports_public_recency_view(self):
        state = PersonaDevelopmentState.empty("murr")
        state = state.record_interest("Rust programming", observed_at=NOW, strength=0.2)
        state = state.record_interest(
            "  rust   programming ", observed_at=NOW + timedelta(days=9), strength=0.2,
        )

        record = state.interests[0]
        public = state.public_dict(as_of=NOW + timedelta(days=19))
        self.assertEqual(record.concept, "Rust programming")
        self.assertEqual(record.evidence_count, 2)
        self.assertLess(public["interests"][0]["effective_confidence"], record.confidence)
        self.assertNotIn("raw_evidence", str(public))

    def test_registry_never_crosses_persona_namespaces(self):
        registry = PersonaDevelopmentRegistry()
        murr = PersonaDevelopmentState.empty("murr").record_interest("Rust", observed_at=NOW)
        registry.replace(murr)

        self.assertEqual(registry.snapshot("murr"), murr)
        self.assertEqual(registry.snapshot("other").interests, ())

    def test_invalid_confidence_timestamps_and_duplicate_records_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "not including, 1.0"):
            InterestRecord("Rust", 1.0, 1, NOW)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            SkillRecord("Python", 0.5, 1, datetime(2026, 8, 14, 12, 0))
        first = InterestRecord("Rust", 0.2, 1, NOW)
        second = InterestRecord(" rust ", 0.3, 1, NOW)
        with self.assertRaisesRegex(ValueError, "duplicate concepts"):
            PersonaDevelopmentState("murr", interests=(first, second))
        with self.assertRaisesRegex(ValueError, "half_life_days"):
            PersonaDevelopmentState.empty("murr").record_interest("Rust", observed_at=NOW, half_life_days=0)


if __name__ == "__main__":
    unittest.main()
