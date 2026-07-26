from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.chunker import chunk_markdown


class ChunkerRegressionTests(unittest.TestCase):
    def test_heading_and_prose_remain_in_one_chunk_when_under_limit(self):
        """Paragraphs must accumulate instead of replacing prior content."""
        markdown = """---
chapter: 1
---

# Chapter 1 — Routine

## Routine

The operations floor was quiet and methodical.

Elias checked the telemetry before the morning briefing.

Maeve watched the display without speaking.
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "chapter.md"
            path.write_text(markdown, encoding="utf-8")

            chunks = chunk_markdown(path, max_chars=1200)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["heading"], "Routine")
        self.assertIn("# Chapter 1 — Routine", chunks[0]["text"])
        self.assertIn("Elias checked the telemetry", chunks[0]["text"])
        self.assertIn("Maeve watched the display", chunks[0]["text"])

    def test_generated_chapter_contains_substantial_prose_chunks(self):
        """Guard the real prechunker output against heading-only analysis."""
        project_root = Path(__file__).resolve().parents[1]
        chapter = project_root / "canon" / "chapters" / "01-routine.md"

        chunks = chunk_markdown(chapter)

        self.assertGreaterEqual(len(chunks), 3)
        self.assertGreater(max(len(chunk["text"]) for chunk in chunks), 500)
        self.assertTrue(
            any(
                "The operations floor did not resemble command."
                in chunk["text"]
                for chunk in chunks
            )
        )


if __name__ == "__main__":
    unittest.main()
