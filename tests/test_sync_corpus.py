from pathlib import Path
import sys
import types
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Corpus discovery should be testable without a running Ollama service.
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.sync import ANALYSIS_CORPUS_ROOT, find_manuscripts


class SyncCorpusDiscoveryTests(unittest.TestCase):
    def test_sync_discovers_the_prechunked_chapter_corpus(self):
        expected = sorted(ANALYSIS_CORPUS_ROOT.rglob("*.md"))

        discovered = find_manuscripts()

        self.assertEqual(discovered, expected)
        self.assertGreater(len(discovered), 1)
        self.assertTrue(
            all(path.is_relative_to(ANALYSIS_CORPUS_ROOT) for path in discovered)
        )

    def test_sync_excludes_raw_manuscript_markdown(self):
        raw_prologue = (
            PROJECT_ROOT
            / "canon"
            / "manuscript"
            / "chapter-prologue.md"
        )

        self.assertTrue(raw_prologue.exists())
        self.assertNotIn(raw_prologue, find_manuscripts())


if __name__ == "__main__":
    unittest.main()
