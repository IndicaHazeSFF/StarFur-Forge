from pathlib import Path
import tempfile
import unittest

from pipeline import db


class AssistantMemoryAssociationTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_directory.name) / "associations.sqlite"

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        self.temp_directory.cleanup()

    def _memory(self, summary, *, domain="personal", details=None):
        return db.create_assistant_memory(
            "User", "personal_fact", summary, details=details,
            importance=0.8, confidence=0.9, domain=domain,
        )

    def test_associations_are_domain_scoped_and_canonicalized(self):
        first = self._memory("First memory")
        second = self._memory("Second memory")
        association_id = db.create_assistant_memory_association(
            second, first, "related", strength=0.75, source="test",
        )

        association = db.get_assistant_memory_association(association_id)
        self.assertEqual((association["source_memory_id"], association["target_memory_id"]), (first, second))
        self.assertEqual(association["association_type"], "related")
        self.assertEqual(association["status"], "active")
        self.assertEqual(db.list_assistant_memory_associations(memory_id=first), [association])

        other_domain = self._memory("Other domain", domain="project:other")
        with self.assertRaisesRegex(ValueError, "active domain"):
            db.create_assistant_memory_association(first, other_domain, "related")
        with self.assertRaisesRegex(ValueError, "association_type"):
            db.create_assistant_memory_association(first, second, "unknown")

    def test_association_adds_small_explainable_context_boost(self):
        nozzle = self._memory(
            "Nozzle size correction",
            details="The user uses a 0.8 mm printer nozzle.",
        )
        profile = self._memory(
            "Printer slicer profile",
            details="The standard layer-height profile is 0.32 mm.",
        )
        association_id = db.create_assistant_memory_association(
            nozzle, profile, "topic", strength=0.8, source="test",
        )

        first = db.retrieve_assistant_memories("What nozzle size do I use?", limit=5)
        second = db.retrieve_assistant_memories("What nozzle size do I use?", limit=5)
        self.assertEqual(first, second)
        self.assertEqual([item["memory"]["id"] for item in first], [nozzle, profile])
        self.assertTrue(any("association with memory" in reason for reason in first[1]["reasons"]))
        self.assertEqual(first[1]["score"], 0.12)

        explanation = db.explain_assistant_memory_retrieval("What nozzle size do I use?", limit=2)
        self.assertEqual([item["memory"]["id"] for item in explanation["selected"]], [nozzle, profile])
        self.assertTrue(any("topic" in reason for reason in explanation["selected"][1]["reasons"]))

        db.deactivate_assistant_memory_association(association_id)
        after_deactivation = db.retrieve_assistant_memories("What nozzle size do I use?", limit=5)
        self.assertEqual([item["memory"]["id"] for item in after_deactivation], [nozzle])

    def test_association_updates_are_explicit_and_retrieval_is_read_only(self):
        first = self._memory("Coffee preference")
        second = self._memory("Blue mug preference")
        association_id = db.create_assistant_memory_association(first, second, "related", strength=0.4)
        before = db.get_assistant_memory_association(association_id)

        db.retrieve_assistant_memories("coffee", limit=5)
        self.assertEqual(db.get_assistant_memory_association(association_id), before)

        updated = db.update_assistant_memory_association(association_id, strength=0.9, source="reviewed")
        self.assertEqual(updated["strength"], 0.9)
        self.assertEqual(updated["source"], "reviewed")
        with self.assertRaisesRegex(ValueError, "No association changes"):
            db.update_assistant_memory_association(association_id)


if __name__ == "__main__":
    unittest.main()