from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.document_context import DocumentContextError, select_document_context
from pipeline.document_intake import prepare_document_text


class DocumentContextTests(unittest.TestCase):
    def setUp(self):
        self.document = prepare_document_text(
            "# Hardware\n\nThe desktop has an RTX 4070 graphics card.\n\n"
            "# Food\n\nRoger prefers jasmine rice mixed with basmati rice.",
            "notes.md",
            max_chars=70,
            overlap_paragraphs=0,
        )
        self.assertGreaterEqual(len(self.document.chunks), 2)

    def test_selects_only_relevant_chunks_in_stable_order(self):
        first = select_document_context(self.document, "What GPU is in the desktop?", limit=2)
        second = select_document_context(self.document, "What GPU is in the desktop?", limit=2)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertIn("RTX 4070", first[0].chunk.text)
        self.assertIn("meaningful keyword overlap", first[0].reasons[0])

    def test_rejects_empty_or_nonmeaningful_queries_without_mutation(self):
        with self.assertRaisesRegex(DocumentContextError, "empty"):
            select_document_context(self.document, "   ")
        with self.assertRaisesRegex(DocumentContextError, "meaningful"):
            select_document_context(self.document, "the and of")
        with self.assertRaisesRegex(DocumentContextError, "between"):
            select_document_context(self.document, "GPU", limit=9)


if __name__ == "__main__":
    unittest.main()
