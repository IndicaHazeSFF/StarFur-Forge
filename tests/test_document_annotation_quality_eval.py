import unittest

from pipeline.document_annotation_quality_eval import (
    evaluate_document_annotation_quality,
    format_document_annotation_quality_result,
    format_document_annotation_quality_summary,
    load_document_annotation_quality_cases,
    select_document_annotation_quality_case,
    summarize_document_annotation_quality_records,
)
from pipeline.benchmark import BenchmarkModelProfile, BenchmarkRunManifest
from pipeline.experiment_ledger import build_benchmark_result_record


def candidate(memory_type, subject, summary, details):
    return {"proposal": {
        "memory_type": memory_type, "subject": subject,
        "summary": summary, "details": details,
    }}


class DocumentAnnotationQualityEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.case = select_document_annotation_quality_case(
            "model-comparison-facts", load_document_annotation_quality_cases(),
        )

    def test_scores_complete_expected_candidates_without_retaining_text(self):
        payload = {"candidates": [
            candidate("preference", "user", "Rice preference", "Prefers jasmine rice mixed with basmati rice"),
            candidate("personal_fact", "user", "Desktop hardware", "Desktop has RTX 4070 graphics card"),
            candidate("project_context", "user", "StarFur Forge project", "Long-term StarFur Forge project"),
        ]}
        result = evaluate_document_annotation_quality(payload, self.case)
        self.assertEqual(1.0, result["annotation_quality_recall"])
        self.assertEqual(1.0, result["annotation_quality_precision"])
        self.assertTrue(result["results"][0]["pass"])
        self.assertNotIn("jasmine", str(result))

    def test_counts_extra_or_missed_candidates_as_quality_failures(self):
        payload = {"candidates": [
            candidate("preference", "user", "Rice preference", "Prefers jasmine rice mixed with basmati rice"),
            candidate("relationship_context", "Murr", "Persona traits", "Warm playful persona"),
        ]}
        result = evaluate_document_annotation_quality(payload, self.case)
        self.assertEqual(1, result["annotation_false_positive_count"])
        self.assertEqual(2, result["annotation_missed_target_count"])
        self.assertFalse(result["results"][0]["pass"])
        self.assertIn("False positives:    1", format_document_annotation_quality_result(result))

    def test_rejects_unknown_case_selection(self):
        with self.assertRaises(ValueError):
            select_document_annotation_quality_case("missing", (self.case,))

    def test_summary_groups_quality_runs_without_candidate_wording(self):
        result = evaluate_document_annotation_quality({"candidates": []}, self.case)
        result["latency_ms"] = 12020.0
        record = build_benchmark_result_record(
            BenchmarkRunManifest("phi", "annotation", BenchmarkModelProfile("Ollama", "phi4-mini:latest"), "v1"),
            result,
        )
        summary = summarize_document_annotation_quality_records([record])
        self.assertEqual(1, summary["observations"])
        self.assertEqual(0.0, summary["models"][0]["recall"])
        self.assertIsNone(summary["models"][0]["precision"])
        report = format_document_annotation_quality_summary(summary)
        self.assertIn("precision: (no candidates)", report)
        self.assertNotIn("rice", report)


if __name__ == "__main__":
    unittest.main()
