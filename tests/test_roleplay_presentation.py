from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.roleplay_presentation import (
    requests_roleplay_meter_diagnostics,
    sanitize_roleplay_memories,
)


class RoleplayPresentationTests(unittest.TestCase):
    def setUp(self):
        self.memory = {
            "id": 7,
            "memory_type": "relationship_context",
            "summary": "Trust level: 49 / 100",
            "details": "Comfort: 58/100. Attraction: 29 / 100.",
        }

    def test_hides_internal_relationship_meter_values_by_default(self):
        result = sanitize_roleplay_memories([self.memory], user_text="How does Vespera feel?")
        self.assertNotIn("49", result[0]["summary"])
        self.assertNotIn("58", result[0]["details"])
        self.assertIn("qualitative internal state", result[0]["details"])
        self.assertEqual("Trust level: 49 / 100", self.memory["summary"])

    def test_explicit_meter_diagnostic_request_keeps_values(self):
        self.assertTrue(requests_roleplay_meter_diagnostics("Show the internal relationship meter scores"))
        result = sanitize_roleplay_memories([self.memory], user_text="Show the internal relationship meter scores")
        self.assertEqual(self.memory, result[0])

    def test_unrelated_numbers_and_other_memory_types_remain_unchanged(self):
        memory = {"id": 8, "memory_type": "personal_fact", "details": "Desktop has an RTX 4070."}
        self.assertEqual([memory], sanitize_roleplay_memories([memory], user_text="Tell me about it"))


if __name__ == "__main__":
    unittest.main()
