import sqlite3
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("chromadb", types.ModuleType("chromadb"))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import db, domains, ingest


class MemoryDomainTests(unittest.TestCase):
    def test_legacy_lore_rows_receive_default_project_domain(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            path = Path(temp) / "legacy.db"
            connection = sqlite3.connect(path)
            connection.executescript("""
                CREATE TABLE entities (
                    id INTEGER PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'confirmed'
                );
                CREATE TABLE aliases (id INTEGER PRIMARY KEY, entity_id INTEGER, alias TEXT);
                CREATE TABLE entity_facts (
                    id INTEGER PRIMARY KEY,
                    entity_id INTEGER NOT NULL,
                    fact TEXT NOT NULL,
                    evidence TEXT,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'extracted'
                );
                INSERT INTO entities (id, canonical_name, entity_type) VALUES (1, 'Ceph', 'character');
                INSERT INTO entity_facts (id, entity_id, fact, source) VALUES (1, 1, 'Existing', 'chapter.md');
            """)
            connection.commit()
            connection.close()
            old = db.DB_PATH
            db.DB_PATH = path
            try:
                with db.transaction() as connection:
                    row = connection.execute(
                        "SELECT domain FROM entity_facts WHERE id = 1"
                    ).fetchone()
                self.assertEqual(row["domain"], domains.DEFAULT_PROJECT_DOMAIN)
                self.assertIsNotNone(db.get_entity_by_name("Ceph"))
                self.assertIsNone(db.get_entity_by_name("Ceph", domain="personal"))
            finally:
                db.DB_PATH = old

    def test_domain_validation_and_entity_creation(self):
        self.assertEqual(domains.normalize_domain(" PERSONAL "), "personal")
        with self.assertRaises(ValueError):
            domains.normalize_domain("all-memory")
        
    def test_chroma_metadata_carries_domain(self):
        class Collection:
            def __init__(self):
                self.metadata = None
            def get(self, **kwargs):
                return {"metadatas": []}
            def delete(self, **kwargs):
                pass
            def upsert(self, **kwargs):
                self.metadata = kwargs["metadatas"][0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "chapter.md"
            path.write_text("# Chapter\n\nProse.", encoding="utf-8")
            collection = Collection()
            with patch.object(ingest, "CANON_ROOT", root), patch.object(
                ingest, "embed", return_value=[0.1, 0.2]
            ):
                ingest.ingest_file(collection, path, domain="personal")
            self.assertEqual(collection.metadata["domain"], "personal")


if __name__ == "__main__":
    unittest.main()
