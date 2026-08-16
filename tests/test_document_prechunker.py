from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.chunker import chunk_text
from pipeline.document_prechunker import (
    ADVENTURE_STATE_PROFILE,
    ASSISTANT_NOTE_PROFILE,
    DocumentPrechunkError,
    infer_document_profile,
    prechunk_document_text,
    resolve_document_profile,
)


class DocumentPrechunkerTests(unittest.TestCase):
    def test_assistant_note_profile_preserves_legacy_chunker_behavior(self):
        text = "# Notes\n\nFirst paragraph.\n\nSecond paragraph."
        self.assertEqual(
            list(prechunk_document_text(text, profile=ASSISTANT_NOTE_PROFILE)),
            chunk_text(text),
        )

    def test_adventure_profile_preserves_named_state_sections(self):
        text = """# Story State

The player has crossed the ash sea.

CHARACTERS

Mira distrusts the player after the broken promise.

RELATIONSHIPS

Mira's trust is low.

CURRENT SCENE

The party waits beneath the lighthouse.

STORY IS HERE

The storm has just begun.
"""
        self.assertEqual(infer_document_profile(text), ADVENTURE_STATE_PROFILE)
        chunks = prechunk_document_text(text, profile=ADVENTURE_STATE_PROFILE)
        self.assertEqual([chunk["scene_index"] for chunk in chunks], [0, 1, 2, 3, 4])
        self.assertEqual([chunk["heading"] for chunk in chunks], [
            "Story State", "CHARACTERS", "RELATIONSHIPS", "CURRENT SCENE", "STORY IS HERE",
        ])
        self.assertTrue(all(len(chunk["text"]) <= 3000 for chunk in chunks))

    def test_adventure_profile_splits_large_sections_at_bounded_paragraph_boundaries(self):
        paragraphs = "\n\n".join(f"Paragraph {index}: " + "x" * 400 for index in range(12))
        chunks = prechunk_document_text(
            "# Current Scene\n\n" + paragraphs,
            profile=ADVENTURE_STATE_PROFILE,
            max_chars=1000,
            overlap_paragraphs=0,
        )
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk["text"]) <= 1000 for chunk in chunks))
        self.assertTrue(all(chunk["heading"] == "Current Scene" for chunk in chunks))

    def test_profile_validation_is_explicit(self):
        with self.assertRaises(DocumentPrechunkError):
            resolve_document_profile("unknown", "notes")
        self.assertEqual(resolve_document_profile("auto", "# Notes\n\nPlain text"), ASSISTANT_NOTE_PROFILE)

    def test_explicit_story_is_here_marker_selects_adventure_profile(self):
        self.assertEqual(
            resolve_document_profile("auto", "# Details\n\nFacts.\n\nSTORY IS HERE\n\nContinue."),
            ADVENTURE_STATE_PROFILE,
        )


if __name__ == "__main__":
    unittest.main()
