import unittest

from pipeline.benchmark import BenchmarkModelProfile, BenchmarkRunManifest
from pipeline.document_annotation_eval import (
    DOCUMENT_ANNOTATION_BENCHMARK_VERSION,
    DocumentAnnotationObservation,
    build_document_annotation_benchmark_result,
    format_document_annotation_benchmark_result,
)
from pipeline.experiment_ledger import build_benchmark_result_record
from pipeline.document_annotation_eval import (
    format_document_annotation_summary,
    summarize_document_annotation_records,
)


class DocumentAnnotationEvaluationTests(unittest.TestCase):
    def test_result_is_raw_content_free_and_ledger_compatible(self):
        observation = DocumentAnnotationObservation(4, 0, 7, 6, 1, 1234.5)
        result = build_document_annotation_benchmark_result(observation, fallback_model="qwen3:8b")
        case = result["results"][0]
        self.assertEqual(DOCUMENT_ANNOTATION_BENCHMARK_VERSION, result["benchmark_version"])
        self.assertEqual(4, case["successful_chunk_count"])
        self.assertTrue(case["fallback_used"])
        self.assertEqual("qwen3:8b", case["fallback_model"])
        self.assertNotIn("document", case)
        manifest = BenchmarkRunManifest(
            "annotation-smoke", "external-document-annotation",
            BenchmarkModelProfile("Ollama", "phi4-mini:latest"), "annotation-v1",
        )
        record = build_benchmark_result_record(manifest, result)
        self.assertEqual("passed", record["outcome"]["status"])
        self.assertEqual(1, record["metrics"]["annotation_fallback_used_count"])

    def test_failed_chunks_create_a_failed_result(self):
        result = build_document_annotation_benchmark_result(
            DocumentAnnotationObservation(3, 1, 2, 2)
        )
        self.assertFalse(result["results"][0]["pass"])
        self.assertIn("Outcome:            FAIL", format_document_annotation_benchmark_result(result))

    def test_observation_rejects_inconsistent_counts(self):
        with self.assertRaises(ValueError):
            DocumentAnnotationObservation(1, 2, 0, 1)

    def test_summary_groups_models_without_source_or_candidate_content(self):
        phi_result = build_document_annotation_benchmark_result(
            DocumentAnnotationObservation(2, 0, 3, 4, 1, 20.0), fallback_model="qwen3:8b",
        )
        qwen_result = build_document_annotation_benchmark_result(
            DocumentAnnotationObservation(1, 1, 0, 3, 0, 60.0),
        )
        phi = build_benchmark_result_record(
            BenchmarkRunManifest("phi", "annotation", BenchmarkModelProfile("Ollama", "phi4-mini:latest"), "v1"),
            phi_result,
        )
        qwen = build_benchmark_result_record(
            BenchmarkRunManifest("qwen", "annotation", BenchmarkModelProfile("Ollama", "qwen3:8b"), "v1"),
            qwen_result,
        )
        summary = summarize_document_annotation_records([phi, qwen])
        self.assertEqual(2, summary["observations"])
        self.assertEqual(["phi4-mini:latest", "qwen3:8b"], [row["primary_model"] for row in summary["models"]])
        report = format_document_annotation_summary(summary)
        self.assertIn("failed chunks: 1", report)
        self.assertNotIn("external-document-annotation", report)


if __name__ == "__main__":
    unittest.main()
