from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from pipeline import sync


class TargetedReanalysisTests(unittest.TestCase):
    def test_reanalysis_requires_authoritative_chapter_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapters = root / "canon" / "chapters"
            chapters.mkdir(parents=True)
            chapter = chapters / "01.md"
            chapter.write_text("# Chapter\nprose", encoding="utf-8")
            with patch.object(sync, "ANALYSIS_CORPUS_ROOT", chapters), patch.object(
                sync, "PROJECT_ROOT", root
            ):
                self.assertEqual(sync.validate_chapter_path("canon/chapters/01.md"), chapter.resolve())
                with self.assertRaises(ValueError):
                    sync.validate_chapter_path("canon/manuscript/raw.md")
                with self.assertRaises(ValueError):
                    sync.validate_chapter_path("canon/chapters/01.txt")

    def test_reanalysis_updates_only_target_manifest_and_skips_ingestion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapters = root / "canon" / "chapters"
            chapters.mkdir(parents=True)
            target = chapters / "01.md"
            other = chapters / "02.md"
            target.write_text("# One\nupdated prose", encoding="utf-8")
            other.write_text("# Two\nprose", encoding="utf-8")
            manifest_path = root / "data" / "sync_manifest.json"
            manifest_path.parent.mkdir()
            manifest_path.write_text(json.dumps({
                "sync_version": 1,
                "annotator_version": 3,
                "chunker_version": 3,
                "files": {
                    "canon/chapters/02.md": {"hash": "old-other"},
                },
            }), encoding="utf-8")
            with patch.object(sync, "PROJECT_ROOT", root), patch.object(
                sync, "ANALYSIS_CORPUS_ROOT", chapters
            ), patch.object(sync, "MANIFEST_PATH", manifest_path), patch.object(
                sync, "DATA_ROOT", manifest_path.parent
            ), patch.object(sync, "analyze_document") as analyze, patch.object(
                sync, "run_ingestion"
            ) as ingestion:
                sync.reanalyze_chapter("canon/chapters/01.md")
            analyze.assert_called_once_with(target.resolve())
            ingestion.assert_not_called()
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("canon/chapters/02.md", saved["files"])
            self.assertEqual(saved["files"]["canon/chapters/02.md"]["hash"], "old-other")
            self.assertEqual(
                saved["files"][next(key for key in saved["files"] if key.endswith("chapters\\01.md"))]["hash"],
                sync.file_hash(target),
            )


if __name__ == "__main__":
    unittest.main()
