from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline import db


SOURCE = "canon/chapters/01-routine.md"
OTHER_SOURCE = "canon/chapters/02-approach.md"


class SourceCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "starfur.db"
        self.original_db_path = db.DB_PATH
        self.addCleanup(setattr, db, "DB_PATH", self.original_db_path)
        db.DB_PATH = self.db_path

        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE entities (
                    id INTEGER PRIMARY KEY,
                    canonical_name TEXT NOT NULL
                );
                CREATE TABLE aliases (
                    id INTEGER PRIMARY KEY,
                    entity_id INTEGER NOT NULL,
                    alias TEXT NOT NULL
                );
                CREATE TABLE appearances (
                    id INTEGER PRIMARY KEY,
                    entity_id INTEGER NOT NULL,
                    source TEXT NOT NULL
                );
                CREATE TABLE proposals (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE entity_facts (
                    id INTEGER PRIMARY KEY,
                    entity_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL
                );

                INSERT INTO entities VALUES (1, 'Elias Voss');
                INSERT INTO aliases VALUES (1, 1, 'Elias');

                INSERT INTO appearances VALUES (1, 1, 'canon/chapters/01-routine.md');
                INSERT INTO appearances VALUES (2, 1, 'canon/chapters/02-approach.md');

                INSERT INTO proposals VALUES (1, 'canon/chapters/01-routine.md', 'pending');
                INSERT INTO proposals VALUES (2, 'canon/chapters/01-routine.md', 'approved');
                INSERT INTO proposals VALUES (3, 'canon/chapters/01-routine.md', 'rejected');
                INSERT INTO proposals VALUES (4, 'canon/chapters/02-approach.md', 'pending');

                INSERT INTO entity_facts VALUES (1, 1, 'canon/chapters/01-routine.md', 'extracted');
                INSERT INTO entity_facts VALUES (2, 1, 'canon/chapters/01-routine.md', 'confirmed');
                INSERT INTO entity_facts VALUES (3, 1, 'canon/chapters/02-approach.md', 'extracted');
                """
            )

    def test_cleanup_removes_only_rebuildable_source_records(self):
        result = db.clear_source_derived_memory(SOURCE)

        self.assertEqual(
            result,
            {
                "appearances": 1,
                "pending_proposals": 1,
                "entity_facts": 1,
            },
        )

        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM appearances WHERE source = ?",
                    (SOURCE,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM proposals WHERE source = ? AND status = 'pending'",
                    (SOURCE,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM proposals WHERE source = ? AND status = 'approved'",
                    (SOURCE,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM proposals WHERE source = ? AND status = 'rejected'",
                    (SOURCE,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM entity_facts WHERE source = ? AND status = 'extracted'",
                    (SOURCE,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM entity_facts WHERE source = ? AND status = 'confirmed'",
                    (SOURCE,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM appearances WHERE source = ?",
                    (OTHER_SOURCE,),
                ).fetchone()[0],
                1,
            )

        connection.close()


if __name__ == "__main__":
    unittest.main()
