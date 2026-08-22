import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_eval import (
    BENCHMARK_VERSION,
    format_adventure_integrity_result,
    load_adventure_cases,
    run_adventure_integrity_benchmark,
)


class AdventureIntegrityEvalTests(unittest.TestCase):
    def test_checked_in_fixture_is_deterministic_and_passes(self):
        result = run_adventure_integrity_benchmark()

        self.assertEqual(BENCHMARK_VERSION, result["benchmark_version"])
        self.assertEqual(5, result["cases"])
        self.assertTrue(result["passed"])
        self.assertTrue(result["repeatability"])
        self.assertEqual([], result["failures"])
        self.assertIn("Projections/replay/resources:  PASS", format_adventure_integrity_result(result))
        resource_result = next(item for item in result["results"] if item["name"] == "resource_projection_hides_private_values_from_replay_and_context")
        self.assertEqual(2, resource_result["actual_counts"]["resources"])
        branch_result = next(item for item in result["results"] if item["name"] == "checkpoint_child_keeps_only_verified_parent_prefix")
        self.assertTrue(branch_result["checks"]["branch"])

    def test_malformed_or_unknown_fixture_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps({"benchmark_version": BENCHMARK_VERSION, "cases": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "1-100 cases"):
                load_adventure_cases(path)

            path.write_text(json.dumps({
                "benchmark_version": BENCHMARK_VERSION,
                "cases": [{"name": "bad", "events": [{"event_type": "discovery", "summary": "x", "untrusted": True}], "expect": {}}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "event schema"):
                load_adventure_cases(path)


if __name__ == "__main__":
    unittest.main()
