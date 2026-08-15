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

    def test_compact_public_ids_resolve_and_preserve_numeric_compatibility(self):
        memory_id = db.create_assistant_memory("User", "preference", "Likes tea")
        proposal = {"subject": "User", "memory_type": "goal", "summary": "Finish tests", "details": "", "importance": 0.5, "confidence": 0.5, "retention": "short_term"}
        proposal_id = db.create_assistant_memory_proposal(proposal)
        self.assertEqual(db.assistant_public_id("memory", memory_id), "M-001")
        self.assertEqual(db.assistant_public_id("proposal", proposal_id), "P-001")
        self.assertEqual(db.resolve_assistant_id("M-001", "memory"), memory_id)
        self.assertEqual(db.resolve_assistant_id("P-001", "proposal"), proposal_id)
        self.assertEqual(db.resolve_assistant_id(str(memory_id), "memory"), memory_id)
        self.assertIsNone(db.resolve_assistant_id("P-999", "proposal"))

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

    def test_explicit_visibility_scope_is_optional_validated_and_persists(self):
        legacy_id = db.create_assistant_memory("User", "preference", "Legacy preference")
        roleplay_id = db.create_assistant_memory(
            "User", "preference", "Story-only preference", visibility_scope="roleplay",
        )
        self.assertIsNone(db.get_assistant_memory(legacy_id)["visibility_scope"])
        self.assertEqual("roleplay", db.get_assistant_memory(roleplay_id)["visibility_scope"])
        self.assertEqual("project", db.update_assistant_memory(roleplay_id, visibility_scope="PROJECT")["visibility_scope"])
        self.assertIsNone(db.update_assistant_memory(roleplay_id, visibility_scope="")["visibility_scope"])
        with self.assertRaises(ValueError):
            db.create_assistant_memory("User", "preference", "Bad scope", visibility_scope="sensitive")

    def test_visibility_scope_migrates_additively_from_legacy_assistant_tables(self):
        legacy_path = Path(self.temp.name) / "legacy.sqlite"
        with sqlite3.connect(legacy_path) as connection:
            connection.execute("""CREATE TABLE assistant_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT NOT NULL,
                subject TEXT NOT NULL, memory_type TEXT NOT NULL, summary TEXT NOT NULL,
                details TEXT, importance REAL NOT NULL DEFAULT 0.5,
                confidence REAL NOT NULL DEFAULT 0.5, retention TEXT NOT NULL DEFAULT 'long_term',
                status TEXT NOT NULL DEFAULT 'active', source TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_accessed_at TEXT
            )""")
            connection.execute("""CREATE TABLE assistant_memory_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT NOT NULL,
                subject TEXT NOT NULL, memory_type TEXT NOT NULL, summary TEXT NOT NULL,
                details TEXT, importance REAL NOT NULL, confidence REAL NOT NULL,
                retention TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT,
                reviewed_by TEXT, review_note TEXT, approved_memory_id INTEGER
            )""")
        db.DB_PATH = legacy_path
        with db.connect() as connection:
            memory_columns = {row["name"] for row in connection.execute("PRAGMA table_info(assistant_memories)")}
            proposal_columns = {row["name"] for row in connection.execute("PRAGMA table_info(assistant_memory_proposals)")}
        self.assertIn("visibility_scope", memory_columns)
        self.assertIn("visibility_scope", proposal_columns)


if __name__ == "__main__":
    unittest.main()
