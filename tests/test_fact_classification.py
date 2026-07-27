from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import annotator, db


class FactClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "starfur.db"
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            """
            CREATE TABLE entity_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL,
                fact TEXT NOT NULL,
                evidence TEXT,
                source TEXT NOT NULL,
                scene_index INTEGER,
                chunk_index INTEGER,
                status TEXT NOT NULL DEFAULT 'extracted',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO entity_facts (
                entity_id, fact, evidence, source, scene_index, chunk_index
            ) VALUES (1, 'Existing fact', 'Existing evidence', 'source.md', 0, 0);
            """
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_existing_database_gets_fact_type_without_losing_rows(self):
        connection = db.connect()
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(entity_facts)")
        }
        row = connection.execute(
            "SELECT fact, fact_type FROM entity_facts WHERE id = 1"
        ).fetchone()
        connection.close()

        self.assertIn("fact_type", columns)
        self.assertEqual(row["fact"], "Existing fact")
        self.assertEqual(row["fact_type"], "durable_fact")

    def test_fact_type_is_stored_and_unknown_type_defaults_conservatively(self):
        db.add_entity_fact(
            entity_id=1,
            fact="A recurring behavior",
            evidence="Observed repeatedly",
            source="source.md",
            fact_type="behavioral_tendency",
        )
        db.add_entity_fact(
            entity_id=1,
            fact="A temporary state",
            evidence="Observed in scene",
            source="source.md",
            fact_type="not-a-valid-type",
        )

        connection = db.connect()
        rows = connection.execute(
            """
            SELECT fact, fact_type
            FROM entity_facts
            WHERE fact IN ('A recurring behavior', 'A temporary state')
            ORDER BY id
            """
        ).fetchall()
        connection.close()

        self.assertEqual(
            [(row["fact"], row["fact_type"]) for row in rows],
            [
                ("A recurring behavior", "behavioral_tendency"),
                ("A temporary state", "durable_fact"),
            ],
        )

    def test_prompt_documents_all_fact_types(self):
        with patch.object(annotator, "get_entities", return_value=[]):
            prompt = annotator.build_system_prompt()

        for fact_type in db.FACT_TYPES:
            self.assertIn(fact_type, prompt)

        self.assertIn("intrinsic physical characteristic", prompt)
        self.assertIn("recurring/general", prompt)
        self.assertIn("transient actions, conditions, posture, symptoms", prompt)
        self.assertIn("clearly establishes the named entity as the subject or owner", prompt)
        self.assertIn("If the subject is unclear, omit the fact rather than guess", prompt)

    def test_annotation_ceiling_is_4096_tokens(self):
        self.assertEqual(annotator.ANNOTATION_MAX_OUTPUT_TOKENS, 4096)


if __name__ == "__main__":
    unittest.main()
