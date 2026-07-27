from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import proposal_pipeline
from pipeline.annotator import AnnotationParseError


class AnnotationFailureIsolationTests(unittest.TestCase):
    def test_bad_chunk_is_recorded_and_later_chunks_are_still_processed(self):
        chunks = [
            {"text": "bad chunk", "scene_index": 0},
            {"text": "later chunk", "scene_index": 0},
        ]
        annotations = [
            AnnotationParseError(3, "malformed JSON"),
            {},
        ]

        with patch.object(proposal_pipeline, "chunk_markdown", return_value=chunks):
            with patch.object(
                proposal_pipeline,
                "canonical_source",
                return_value="canon/chapters/test.md",
            ):
                with patch.object(
                    proposal_pipeline,
                    "clear_source_derived_memory",
                    return_value={
                        "appearances": 0,
                        "pending_proposals": 0,
                        "entity_facts": 0,
                    },
                ):
                    with patch.object(
                        proposal_pipeline,
                        "annotate",
                        side_effect=annotations,
                    ) as annotate:
                        with self.assertRaises(
                            proposal_pipeline.DocumentAnalysisError
                        ) as raised:
                            proposal_pipeline.analyze_document(
                                Path("canon/chapters/test.md")
                            )

        self.assertEqual(annotate.call_count, 2)
        self.assertEqual(raised.exception.source, "canon/chapters/test.md")
        self.assertEqual(
            raised.exception.failed_chunks,
            [
                {
                    "chunk_index": 0,
                    "scene_index": 0,
                    "error": "Annotation output remained invalid after 3 attempts: malformed JSON",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
