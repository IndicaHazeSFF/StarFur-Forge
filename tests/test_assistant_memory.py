from pathlib import Path
import sqlite3
import tempfile
import unittest

from pipeline import db
from pipeline.domains import DEFAULT_PROJECT_DOMAIN


class AssistantMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "assistant.db"

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.temp.cleanup()

    def test_create_list_search_update_and_forget(self):
        memory_id = db.create_assistant_memory(
            subject="User",
            memory_type="preference",
            summary="Prefers dark interfaces",
            details="Usually chooses dark themes.",
            importance=0.8,
            confidence=0.95,
            retention="long_term",
            source="conversation:test",
        )
        row = db.get_assistant_memory(memory_id)
        self.assertEqual(row["domain"], "personal")
        self.assertEqual(row["retention"], "long_term")
        self.assertEqual(len(db.list_assistant_memories()), 1)
        self.assertEqual(db.search_assistant_memories("dark")[0]["id"], memory_id)
        corrected = db.update_assistant_memory(memory_id, summary="Prefers dark UI themes")
        self.assertEqual(corrected["summary"], "Prefers dark UI themes")
        forgotten = db.forget_assistant_memory(memory_id)
        self.assertEqual(forgotten["status"], "forgotten")
        self.assertEqual(db.list_assistant_memories(), [])
        self.assertEqual(db.list_assistant_memories(status="forgotten")[0]["id"], memory_id)

    def test_domains_and_retention_are_isolated_and_validated(self):
        personal = db.create_assistant_memory("User", "goal", "Finish prototype", retention="short_term")
        project = db.create_assistant_memory("StarFur", "project_context", "Memory engine", domain="project:starfur", retention="session")
        self.assertEqual([r["id"] for r in db.list_assistant_memories(domain="personal")], [personal])
        self.assertEqual([r["id"] for r in db.list_assistant_memories(domain="project:starfur")], [project])
        with self.assertRaises(ValueError):
            db.create_assistant_memory("User", "joke", "Nope")
        with self.assertRaises(ValueError):
            db.create_assistant_memory("User", "goal", "Nope", retention="forever")
        with self.assertRaises(ValueError):
            db.update_assistant_memory(personal, importance=1.5)

    def test_database_stats_separate_assistant_counts(self):
        db.create_assistant_memory("User", "preference", "Likes tea")
        stats = db.database_stats()
        self.assertEqual(stats["assistant_memories"], 1)
        self.assertEqual(stats["assistant_active_memories"], 1)
        self.assertEqual(stats["assistant_pending_proposals"], 0)
        self.assertIn("entities", stats)
        self.assertIn("entity_facts", stats)

    def test_schema_is_additive_and_lore_domain_unchanged(self):
        db.create_assistant_memory("User", "routine", "Works on StarFur", domain="personal")
        self.assertIsNotNone(db.get_assistant_memory(1, domain="personal"))
        with db.connect() as connection:
            tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("assistant_memories", tables)
        self.assertEqual(DEFAULT_PROJECT_DOMAIN, "project:crown-of-claws")


if __name__ == "__main__":
    unittest.main()
