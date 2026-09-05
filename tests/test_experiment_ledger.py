import tempfile
import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.benchmark import BenchmarkModelProfile, BenchmarkRunManifest
from pipeline.experiment_ledger import (
    EXPERIMENT_LEDGER_SCHEMA_VERSION,
    append_benchmark_result,
    build_benchmark_result_record,
    load_benchmark_results,
    summarize_benchmark_results,
)


def sample_manifest():
    return BenchmarkRunManifest(
        "retrieval-001", "assistant-memory-recall",
        BenchmarkModelProfile("Ollama", "qwen3:8b", "q4", 8192),
        "architecture-abc", seed=420, git_commit="abc123",
    )


def sample_result():
    return {
        "benchmark_version": "retrieval-v1", "repeatability": True,
        "top1_hit_rate": 1.0, "top3_hit_rate": 1.0, "recall_at_k": 1.0,
        "precision_at_k": 0.75, "irrelevant_result_count": 0,
        "results": [{
            "name": "gpu recall", "expected": [3], "returned": [3], "pass": True,
            "retrieval": [{"id": 3, "score": 0.95, "reasons": ["2 meaningful keyword overlap"]}],
        }],
    }


def sample_candidate_result():
    return {
        "benchmark_version": "adventure-turn-candidates-v1", "repeatability": True,
        "candidate_acceptance_rate": 1.0, "candidate_schema_pass_rate": 1.0,
        "candidate_ordinary_schema_pass_rate": 1.0, "candidate_typed_schema_pass_rate": 1.0,
        "candidate_no_change_pass_rate": 1.0,
        "results": [{
            "name": "typed_flat_state", "kind": "typed", "expected_accept": True,
            "accepted": True, "expected_ids": ["TM-001"], "returned_ids": ["TM-001"], "pass": True,
        }],
    }


def sample_adventure_turn_result():
    return {
        "benchmark_version": "adventure-turn-smoke-v1", "repeatability": True,
        "generation_success_rate": 1.0, "candidate_validation_success_rate": 1.0,
        "core_use_success_rate": 1.0, "canonical_commit_success_rate": 1.0,
        "results": [{
            "name": "ordinary_candidate_commit", "kind": "adventure_turn",
            "expected_generation": "completed", "actual_generation": "completed",
            "expected_candidates": 1, "actual_candidates": 1,
            "expected_staged": 1, "actual_staged": 1,
            "expected_committed": 1, "actual_committed": 1,
            "pass": True, "failure_category": "none",
        }],
    }


def sample_annotation_quality_result():
    return {
        "benchmark_version": "document-annotation-quality-v1",
        "annotation_quality_recall": 1.0, "annotation_quality_precision": 0.75,
        "annotation_false_positive_count": 1, "annotation_missed_target_count": 0,
        "results": [{
            "name": "model-comparison-facts", "kind": "document_annotation_quality",
            "expected_target_count": 3, "matched_target_count": 3,
            "candidate_count": 4, "false_positive_count": 1,
            "missed_target_count": 0, "pass": False,
        }],
    }


def sample_task_routing_result():
    return {
        "benchmark_version": "task-routing-portability-v1", "repeatability": True,
        "routing_pass_rate": 1.0,
        "results": [{
            "name": "primary_available", "kind": "task_routing",
            "expected_status": "routable", "actual_status": "routable",
            "expected_selected_task_id": "assistant_chat",
            "actual_selected_task_id": "assistant_chat",
            "expected_selected_provider": "ollama",
            "actual_selected_provider": "ollama",
            "expected_fallback_used": False, "actual_fallback_used": False,
            "pass": True,
        }],
    }


class ExperimentLedgerTests(unittest.TestCase):
    def test_record_is_append_only_and_omits_query_content(self):
        record = build_benchmark_result_record(sample_manifest(), sample_result(), run_id="smoke-1")
        self.assertEqual(record["schema_version"], EXPERIMENT_LEDGER_SCHEMA_VERSION)
        self.assertEqual(record["outcome"]["status"], "passed")
        self.assertFalse(record["raw_content_included"])
        self.assertNotIn("query", record["cases"][0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            append_benchmark_result(path, record)
            append_benchmark_result(path, record)
            rows = load_benchmark_results(path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["record_id"], record["record_id"])

    def test_failed_case_sets_outcome_and_aggregate_report(self):
        result = sample_result()
        result["results"][0]["pass"] = False
        record = build_benchmark_result_record(sample_manifest(), result, recorded_at="2026-08-08T00:00:00+00:00")
        self.assertEqual(record["outcome"], {"status": "failed", "failure_category": "benchmark_assertion_failed"})
        summary = summarize_benchmark_results([record])
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["pass_rate"], 0.0)

    def test_rejects_raw_content_and_corrupt_ledger(self):
        record = build_benchmark_result_record(sample_manifest(), sample_result())
        record["raw_content_included"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            with self.assertRaises(ValueError):
                append_benchmark_result(path, record)
            path.write_text("not json\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_benchmark_results(path)

    def test_candidate_schema_results_record_without_model_payloads(self):
        record = build_benchmark_result_record(sample_manifest(), sample_candidate_result())
        case = record["cases"][0]
        self.assertEqual("typed", case["kind"])
        self.assertEqual(["TM-001"], case["returned_ids"])
        self.assertEqual(1.0, record["metrics"]["candidate_schema_pass_rate"])
        self.assertEqual(1.0, record["metrics"]["candidate_no_change_pass_rate"])
        self.assertFalse(record["raw_content_included"])

    def test_rejects_unbounded_extra_content_fields(self):
        record = build_benchmark_result_record(sample_manifest(), sample_result())
        record["raw_prompt"] = "private conversation should never enter the ledger"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                append_benchmark_result(Path(directory) / "ledger.jsonl", record)

    def test_append_reconstructs_cases_and_rejects_nested_manifest_content(self):
        record = build_benchmark_result_record(sample_manifest(), sample_result())
        record["cases"][0]["provider_response"] = "private model output"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            append_benchmark_result(path, record)
            saved = load_benchmark_results(path)[0]
            self.assertNotIn("provider_response", saved["cases"][0])
            record["manifest"]["raw_prompt"] = "private prompt"
            with self.assertRaisesRegex(ValueError, "manifest"):
                append_benchmark_result(path, record)

    def test_adventure_turn_results_separate_core_outcomes_without_turn_text(self):
        record = build_benchmark_result_record(sample_manifest(), sample_adventure_turn_result())
        case = record["cases"][0]
        self.assertEqual("adventure_turn", case["kind"])
        self.assertEqual(1, case["actual_committed"])
        self.assertEqual(1.0, record["metrics"]["canonical_commit_success_rate"])
        self.assertNotIn("prompt", case)
        self.assertNotIn("response", case)

    def test_adventure_turn_failure_categories_remain_bounded_and_operational(self):
        result = sample_adventure_turn_result()
        result["results"][0].update({
            "expected_generation": "failed",
            "actual_generation": "failed",
            "expected_candidates": 0,
            "actual_candidates": 0,
            "expected_staged": 0,
            "actual_staged": 0,
            "expected_committed": 0,
            "actual_committed": 0,
            "failure_category": "response_too_large",
        })
        record = build_benchmark_result_record(sample_manifest(), result)
        self.assertEqual("response_too_large", record["cases"][0]["failure_category"])

    def test_annotation_quality_results_record_counts_without_candidate_content(self):
        record = build_benchmark_result_record(sample_manifest(), sample_annotation_quality_result())
        case = record["cases"][0]
        self.assertEqual("document_annotation_quality", case["kind"])
        self.assertEqual(1, case["false_positive_count"])
        self.assertEqual(0.75, record["metrics"]["annotation_quality_precision"])
        self.assertNotIn("details", case)

    def test_task_routing_results_record_outcomes_without_route_configuration(self):
        record = build_benchmark_result_record(sample_manifest(), sample_task_routing_result())
        case = record["cases"][0]
        self.assertEqual("task_routing", case["kind"])
        self.assertEqual("routable", case["actual_status"])
        self.assertEqual(1.0, record["metrics"]["routing_pass_rate"])
        self.assertNotIn("profiles", case)
        self.assertNotIn("providers", case)


if __name__ == "__main__":
    unittest.main()
