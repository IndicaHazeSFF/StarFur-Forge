import json
import unittest
from pathlib import Path

from pipeline.document_annotation_quality_eval import (
    load_document_annotation_quality_cases,
    select_document_annotation_quality_case,
)
from pipeline.document_annotation_quality_runner import run_document_annotation_quality_case


class FakeProvider:
    name = "fake"

    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, messages, *, model=None, options=None, stream=False):
        self.calls.append({"model": model, "options": dict(options or {}), "stream": stream})
        return self.response


class DocumentAnnotationQualityRunnerTests(unittest.TestCase):
    def test_runs_public_fixture_without_returning_document_or_candidates(self):
        payload = {"proposals": [
            {"store": True, "subject": "Roger", "memory_type": "preference", "summary": "Rice preference", "details": "Jasmine rice mixed with basmati rice", "importance": 0.9, "confidence": 0.9, "retention": "long_term"},
            {"store": True, "subject": "Roger", "memory_type": "personal_fact", "summary": "Desktop hardware", "details": "Desktop has RTX 4070 graphics card", "importance": 0.9, "confidence": 0.9, "retention": "long_term"},
            {"store": True, "subject": "Roger", "memory_type": "project_context", "summary": "StarFur Forge project", "details": "Long-term StarFur Forge local-first companion project", "importance": 0.9, "confidence": 0.9, "retention": "long_term"},
        ]}
        case = select_document_annotation_quality_case(
            "model-comparison-facts", load_document_annotation_quality_cases(),
        )
        fixture = Path(__file__).parent / "fixtures" / "document_annotation_quality_note.md"
        provider = FakeProvider({"message": {"content": json.dumps(payload)}})
        run = run_document_annotation_quality_case(str(fixture), case, provider, "fixture-model")
        self.assertEqual("fixture-model", run.primary_model)
        self.assertEqual(1, run.primary_attempts)
        self.assertEqual(0, run.failed_chunk_count)
        self.assertEqual(3, run.candidate_count)
        self.assertTrue(run.result["results"][0]["pass"])
        self.assertNotIn("jasmine", str(run.result))
        self.assertEqual("fixture-model", provider.calls[0]["model"])

    def test_rejects_non_fixture_source_before_calling_provider(self):
        case = select_document_annotation_quality_case(
            "model-comparison-facts", load_document_annotation_quality_cases(),
        )
        provider = FakeProvider({"message": {"content": "{}"}})
        with self.assertRaisesRegex(ValueError, "checked-in public"):
            run_document_annotation_quality_case(__file__, case, provider, "fixture-model")
        self.assertEqual([], provider.calls)


if __name__ == "__main__":
    unittest.main()
