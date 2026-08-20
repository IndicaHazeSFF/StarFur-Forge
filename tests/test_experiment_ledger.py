import tempfile
import unittest
from pathlib import Path

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

    def test_rejects_unbounded_extra_content_fields(self):
        record = build_benchmark_result_record(sample_manifest(), sample_result())
        record["raw_prompt"] = "private conversation should never enter the ledger"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                append_benchmark_result(Path(directory) / "ledger.jsonl", record)


if __name__ == "__main__":
    unittest.main()
