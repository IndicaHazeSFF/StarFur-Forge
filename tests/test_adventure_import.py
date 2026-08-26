import sys
import tempfile
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.adventure_import import AdventureImportError, AdventureImportLog
from pipeline.adventure_registry import AdventureRegistry
from pipeline.document_intake import extract_document_memory_candidates, prepare_document_text


class AdventureImportTests(unittest.TestCase):
    def _candidate(self):
        document = prepare_document_text(
            "# Story\n\nVespera guards the brass hatch.", "story.md", domain="personal",
        )
        candidates = extract_document_memory_candidates(document, lambda _chunk: {"proposals": [{
            "store": True, "subject": "Vespera", "memory_type": "project_context",
            "summary": "Vespera guards the brass hatch", "details": "Vespera guards the brass hatch.",
            "importance": 0.8, "confidence": 0.9, "retention": "long_term",
        }]})
        return document, candidates[0]

    def _workspace(self, root):
        registry = AdventureRegistry(root, now=lambda: datetime(2026, 8, 23, tzinfo=UTC))
        record = registry.create("Quiet Ember")
        return registry, record

    def test_stage_preserves_selected_reviewed_candidate_without_creating_an_event(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record = self._workspace(directory)
            document, candidate = self._candidate()
            log = AdventureImportLog(registry, record, now=lambda: datetime(2026, 8, 23, tzinfo=UTC))

            staged = log.stage(
                review_id="DR-reviewed", document=document, selected=(("C-001", candidate),),
            )

            self.assertEqual("AI-000001", staged.import_id)
            self.assertEqual("C-001", staged.candidates[0]["candidate_id"])
            self.assertEqual(document.content_hash, staged.source_hash)
            self.assertTrue(log.path.exists())
            self.assertFalse((registry.workspace_path(record.adventure_id) / "events.jsonl").exists())
            self.assertEqual([staged], log.records())

    def test_rejects_invalid_or_corrupt_import_records_without_partial_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record = self._workspace(directory)
            document, candidate = self._candidate()
            log = AdventureImportLog(registry, record)

            with self.assertRaisesRegex(AdventureImportError, "candidate identifier"):
                log.stage(review_id="DR-reviewed", document=document, selected=(("not-a-candidate", candidate),))
            self.assertFalse(log.path.exists())

            log.path.write_text('{"not":"a valid import"}\n', encoding="utf-8")
            with self.assertRaisesRegex(AdventureImportError, "log is invalid"):
                log.records()


if __name__ == "__main__":
    unittest.main()
