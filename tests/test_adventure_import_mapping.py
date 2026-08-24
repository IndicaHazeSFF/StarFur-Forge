import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.adventure_import import AdventureImportLog
from pipeline.adventure_import_mapping import AdventureImportMappingError, AdventureImportMappingLog
from pipeline.adventure_registry import AdventureRegistry
from pipeline.document_intake import extract_document_memory_candidates, prepare_document_text


class AdventureImportMappingTests(unittest.TestCase):
    def _staged(self, root):
        registry = AdventureRegistry(root)
        record = registry.create("Quiet Ember")
        document = prepare_document_text("# Story\n\nVespera guards the brass hatch.", "story.md", domain="personal")
        candidate = extract_document_memory_candidates(document, lambda _chunk: {"proposals": [{
            "store": True, "subject": "Vespera", "memory_type": "project_context",
            "summary": "Vespera guards the brass hatch", "details": "Vespera guards the brass hatch.",
            "importance": 0.8, "confidence": 0.9, "retention": "long_term",
        }]})[0]
        AdventureImportLog(registry, record).stage(review_id="DR-reviewed", document=document, selected=(("C-001", candidate),))
        return registry, record

    def test_mapping_is_explicit_idempotent_and_latest_choice_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record = self._staged(directory)
            log = AdventureImportMappingLog(registry, record)
            first = log.map("AI-000001", "C-001", "premise")
            self.assertEqual("IM-000001", first.mapping_id)
            self.assertEqual(first, log.map("AI-000001", "C-001", "premise"))
            changed = log.map("AI-000001", "C-001", "knowledge")
            self.assertEqual("IM-000002", changed.mapping_id)
            self.assertEqual("knowledge", log.current("AI-000001")["C-001"].destination)

    def test_mapping_rejects_unknown_import_candidate_and_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record = self._staged(directory)
            log = AdventureImportMappingLog(registry, record)
            with self.assertRaisesRegex(AdventureImportMappingError, "staged adventure import not found"):
                log.map("AI-999999", "C-001", "premise")
            with self.assertRaisesRegex(AdventureImportMappingError, "staged import candidate not found"):
                log.map("AI-000001", "C-999", "premise")
            with self.assertRaisesRegex(AdventureImportMappingError, "destination is unsupported"):
                log.map("AI-000001", "C-001", "event")


if __name__ == "__main__":
    unittest.main()
