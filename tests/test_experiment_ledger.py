import tempfile
import unittest
from pathlib import Path
import sys
import types


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

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


def sample_provider_resource_admission_result():
    return {
        "benchmark_version": "provider-resource-admission-v1", "repeatability": True,
        "resource_admission_pass_rate": 1.0,
        "results": [{
            "name": "balanced_yields_to_foreground", "kind": "provider_resource_admission",
            "expected_status": "deferred", "actual_status": "deferred",
            "expected_reasons": ["foreground_busy"],
            "actual_reasons": ["foreground_busy"], "pass": True,
        }],
    }


class ExperimentLedgerTests(unittest.TestCase):
    def test_participant_lifecycle_results_round_trip_as_counts_only(self):
        from pipeline.adventure_participant_eval import run_adventure_participant_benchmark
        result = run_adventure_participant_benchmark()
        record = build_benchmark_result_record(sample_manifest(), result)
        self.assertEqual("passed", record["outcome"]["status"])
        self.assertEqual(1.0, record["metrics"]["participant_lifecycle_pass_rate"])
        self.assertEqual(11, len(record["cases"]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            append_benchmark_result(path, record)
            self.assertEqual(record["cases"], load_benchmark_results(path)[0]["cases"])
            self.assertNotIn("Synthetic", path.read_text())

    def test_participant_lifecycle_rejects_content_invalid_counts_and_forged_pass(self):
        from copy import deepcopy
        from pipeline.adventure_participant_eval import run_adventure_participant_benchmark
        baseline = run_adventure_participant_benchmark()
        for field, value in (("prompt", "private"), ("name", "private fixture text"),
                ("actual_outcome", "private outcome"), ("actual_candidates", True),
                ("actual_provider_calls", 17), ("invariants_preserved", "yes"), ("actual_events", 1),
                ("name", []), ("expected_outcome", {})):
            with self.subTest(field=field):
                result = deepcopy(baseline)
                result["results"][0][field] = value
                with self.assertRaises(ValueError):
                    build_benchmark_result_record(sample_manifest(), result)

        failed = deepcopy(baseline)
        failed["results"][0].update(actual_events=1, **{"pass": False})
        self.assertEqual("failed", build_benchmark_result_record(sample_manifest(), failed)["outcome"]["status"])
        for value in (float("nan"), float("inf"), -1, 2, True):
            with self.subTest(rate=value):
                result = deepcopy(baseline)
                result["participant_lifecycle_pass_rate"] = value
                with self.assertRaises(ValueError):
                    build_benchmark_result_record(sample_manifest(), result)

    def test_participant_record_is_revalidated_before_any_append(self):
        from copy import deepcopy
        from pipeline.adventure_participant_eval import run_adventure_participant_benchmark
        baseline = build_benchmark_result_record(sample_manifest(), run_adventure_participant_benchmark())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "never-created.jsonl"
            for field, value in (("prompt", "private"), ("actual_events", 1)):
                record = deepcopy(baseline)
                record["cases"][0][field] = value
                with self.assertRaises(ValueError):
                    append_benchmark_result(path, record)
                self.assertFalse(path.exists())

    def test_provider_resource_admission_records_closed_policy_outcomes_only(self):
        record = build_benchmark_result_record(sample_manifest(), sample_provider_resource_admission_result())
        self.assertEqual(record["metrics"]["resource_admission_pass_rate"], 1.0)
        self.assertEqual(record["cases"][0]["actual_reasons"], ["foreground_busy"])
        self.assertNotIn("backend", record["cases"][0])

    def test_provider_resource_admission_rejects_unbounded_reason_labels(self):
        result = sample_provider_resource_admission_result()
        result["results"][0]["actual_reasons"] = ["host_gpu_busy"]
        with self.assertRaises(ValueError):
            build_benchmark_result_record(sample_manifest(), result)
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

    def test_manifest_revalidation_rejects_tampering_before_creating_a_file(self):
        variants = (
            ("hardware", {"raw_prompt": "synthetic private marker"}),
            ("hardware", {"ram_gb": float("nan")}),
            ("seed", 1.5), ("started_at", "yesterday"),
            ("schema_version", "starfur-benchmark-v99"),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-created" / "ledger.jsonl"
            for field, value in variants:
                record = build_benchmark_result_record(sample_manifest(), sample_result())
                record["manifest"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    append_benchmark_result(path, record)
                self.assertFalse(path.parent.exists())

    def test_invalid_append_preserves_existing_ledger_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            record = build_benchmark_result_record(sample_manifest(), sample_result())
            append_benchmark_result(path, record)
            original = path.read_bytes()
            record["manifest"]["model_profile"]["api_key"] = "synthetic private marker"
            with self.assertRaises(ValueError):
                append_benchmark_result(path, record)
            self.assertEqual(original, path.read_bytes())

    def test_nonfinite_unbounded_and_mistyped_metrics_fail_before_append(self):
        variants = (("latency_ms", float("nan")), ("latency_ms", float("inf")),
            ("latency_ms", -1), ("latency_ms", 10**16), ("latency_ms", 10**1000),
            ("precision_at_k", 1.1), ("recall_at_k", -0.1), ("top1_hit_rate", float("-inf")),
            ("irrelevant_result_count", 1.5), ("annotation_candidate_count", -1),
            ("latency_ms", True))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-created" / "ledger.jsonl"
            for field, value in variants:
                result = sample_result()
                result[field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    build_benchmark_result_record(sample_manifest(), result)
                record = build_benchmark_result_record(sample_manifest(), sample_result())
                record["metrics"][field] = value
                with self.subTest(field=field), self.assertRaises(ValueError):
                    append_benchmark_result(path, record)
                self.assertFalse(path.parent.exists())

    def test_nested_retrieval_nonfinite_score_is_rejected(self):
        result = sample_result()
        result["results"][0]["retrieval"][0]["score"] = float("nan")
        with self.assertRaises(ValueError):
            build_benchmark_result_record(sample_manifest(), result)

    def test_valid_measurements_keep_original_values(self):
        result = sample_result()
        result.update(latency_ms=12.5, time_to_first_token_ms=0, annotation_candidate_count=3)
        record = build_benchmark_result_record(sample_manifest(), result)
        with tempfile.TemporaryDirectory() as directory:
            saved = append_benchmark_result(Path(directory) / "ledger.jsonl", record)
        self.assertEqual(12.5, saved["metrics"]["latency_ms"])
        self.assertEqual(0, saved["metrics"]["time_to_first_token_ms"])
        self.assertEqual(3, saved["metrics"]["annotation_candidate_count"])


if __name__ == "__main__":
    unittest.main()
