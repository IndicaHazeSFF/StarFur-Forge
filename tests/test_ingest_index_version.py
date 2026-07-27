from pathlib import Path
import os
import sys
import types
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Indexing behavior is tested with an in-memory collection, not services.
sys.modules.setdefault("chromadb", types.ModuleType("chromadb"))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import ingest


class FakeCollection:
    def __init__(self, metadatas):
        self.metadatas = metadatas
        self.deletes = []
        self.upserts = []

    def get(self, where=None, include=None):
        if where:
            source = where["source"]
            return {
                "metadatas": [
                    metadata
                    for metadata in self.metadatas
                    if metadata.get("source") == source
                ]
            }
        return {"metadatas": self.metadatas}

    def delete(self, where):
        self.deletes.append(where)

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)


class SemanticIndexVersionTests(unittest.TestCase):
    def setUp(self):
        self.previous_cwd = Path.cwd()
        os.chdir(PROJECT_ROOT)
        self.path = Path("canon/chapters/01-routine.md")
        self.source = str(self.path.relative_to(ingest.CANON_ROOT))
        self.digest = ingest.file_hash(self.path)

    def tearDown(self):
        os.chdir(self.previous_cwd)

    def test_unchanged_current_index_version_skips_embedding(self):
        collection = FakeCollection([
            {
                "source": self.source,
                "file_hash": self.digest,
                "index_version": ingest.SEMANTIC_INDEX_VERSION,
            }
        ])

        with patch.object(ingest, "embed") as embed:
            chunks, status = ingest.ingest_file(collection, self.path)

        self.assertEqual((chunks, status), (0, "unchanged"))
        self.assertEqual(collection.deletes, [])
        self.assertEqual(collection.upserts, [])
        embed.assert_not_called()

    def test_missing_index_version_reindexes_unchanged_markdown(self):
        collection = FakeCollection([
            {
                "source": self.source,
                "file_hash": self.digest,
            }
        ])

        with patch.object(ingest, "embed", return_value=[0.0]):
            chunks, status = ingest.ingest_file(collection, self.path)

        self.assertEqual(status, "indexed")
        self.assertGreater(chunks, 0)
        self.assertEqual(collection.deletes, [{"source": self.source}])
        self.assertEqual(len(collection.upserts), chunks)
        self.assertTrue(
            all(
                upsert["metadatas"][0]["index_version"]
                == ingest.SEMANTIC_INDEX_VERSION
                for upsert in collection.upserts
            )
        )

    def test_outdated_index_version_reindexes_unchanged_markdown(self):
        collection = FakeCollection([
            {
                "source": self.source,
                "file_hash": self.digest,
                "index_version": ingest.SEMANTIC_INDEX_VERSION - 1,
            }
        ])

        with patch.object(ingest, "embed", return_value=[0.0]):
            chunks, status = ingest.ingest_file(collection, self.path)

        self.assertEqual(status, "indexed")
        self.assertGreater(chunks, 0)
        self.assertEqual(collection.deletes, [{"source": self.source}])


if __name__ == "__main__":
    unittest.main()
