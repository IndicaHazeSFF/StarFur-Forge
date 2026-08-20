import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.persona_development import (
    InterestRecord,
    LearningRecord,
    PersonaDevelopmentRegistry,
    PersonaDevelopmentState,
    ReferenceIntakeRecord,
    SkillRecord,
)


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


class PersonaDevelopmentTests(unittest.TestCase):
    def _reference_record(self, *, reference_id="RI-rust-001", persona_id="murr"):
        return ReferenceIntakeRecord(
            reference_id, persona_id, "rss", "Rust design notes", "https://example.test/rust-notes",
            "A short bounded reference summary.", ("Rust", "Compiler design"), NOW,
        )

    def _learning_record(self, *, learning_id="LR-rust-001", outcome="verified_success", skill_concept="Rust"):
        evidence = ("The sandbox test suite compiled and passed.",) if outcome == "verified_success" else ()
        return LearningRecord(
            learning_id, "murr", "sandbox", "Rust ownership can be applied to this example.",
            "Implemented the example in an isolated workspace.", outcome,
            "The test suite passed." if outcome == "verified_success" else "The result was inconclusive.",
            evidence, NOW, skill_concept,
        )

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

    def test_learning_record_is_explicit_inspectable_and_does_not_change_skills(self):
        state = PersonaDevelopmentState.empty("murr")
        state = state.record_learning(self._learning_record())

        self.assertEqual(state.skills, ())
        self.assertEqual(state.learning_records[0].learning_id, "LR-rust-001")
        public = state.public_dict()
        self.assertEqual(public["learning_records"][0]["source"], "sandbox")
        self.assertIn("compiled and passed", public["learning_records"][0]["verification_evidence"][0])

    def test_only_verified_success_with_evidence_can_reinforce_a_skill(self):
        state = PersonaDevelopmentState.empty("murr")
        updated = state.apply_verified_learning(self._learning_record(), strength=0.3)

        self.assertEqual(updated.skills[0].concept, "Rust")
        self.assertEqual(updated.skills[0].evidence_count, 1)
        self.assertEqual(updated.learning_records[0].outcome, "verified_success")
        self.assertLess(updated.skills[0].confidence, 1.0)

        failed = self._learning_record(learning_id="LR-rust-002", outcome="verified_failure", skill_concept=None)
        with self.assertRaisesRegex(ValueError, "only verified_success"):
            state.apply_verified_learning(failed)
        preserved_failure = state.record_learning(failed)
        self.assertEqual(preserved_failure.learning_records[0].outcome, "verified_failure")
        self.assertEqual(preserved_failure.skills, ())
        self.assertEqual(state.skills, ())

    def test_learning_records_reject_cross_persona_duplicate_or_unverified_claims(self):
        with self.assertRaisesRegex(ValueError, "verification evidence"):
            LearningRecord(
                "LR-invalid", "murr", "sandbox", "h", "a", "verified_success", "r", (), NOW, "Rust",
            )
        cross_persona = LearningRecord(
            "LR-other-001", "other", "manual", "h", "a", "inconclusive", "r", (), NOW,
        )
        state = PersonaDevelopmentState.empty("murr")
        with self.assertRaisesRegex(ValueError, "persona_id"):
            state.record_learning(cross_persona)
        state = state.record_learning(self._learning_record())
        with self.assertRaisesRegex(ValueError, "already exists"):
            state.record_learning(self._learning_record())

    def test_reference_intake_can_raise_only_a_declared_interest(self):
        state = PersonaDevelopmentState.empty("murr")
        updated = state.record_reference_interest(self._reference_record(), "Rust", strength=0.2)

        self.assertEqual(updated.reference_records[0].source, "rss")
        self.assertEqual(updated.interests[0].concept, "Rust")
        self.assertEqual(updated.skills, ())
        self.assertEqual(updated.public_dict()["reference_records"][0]["title"], "Rust design notes")

    def test_reference_intake_rejects_cross_persona_duplicate_and_undeclared_topic(self):
        state = PersonaDevelopmentState.empty("murr")
        record = self._reference_record()
        with self.assertRaisesRegex(ValueError, "one of the reference record topics"):
            state.record_reference_interest(record, "Python")
        with self.assertRaisesRegex(ValueError, "persona_id"):
            state.record_reference_interest(self._reference_record(reference_id="RI-other", persona_id="other"), "Rust")
        updated = state.record_reference_interest(record, "Rust")
        with self.assertRaisesRegex(ValueError, "already exists"):
            updated.record_reference_interest(record, "Rust")

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
