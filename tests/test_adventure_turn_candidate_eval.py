import json
import tempfile
import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_turn_candidate_eval import (
    BENCHMARK_VERSION,
    format_adventure_turn_candidate_result,
    load_adventure_turn_candidate_cases,
    run_adventure_turn_candidate_benchmark,
)


class AdventureTurnCandidateEvaluationTests(unittest.TestCase):
    def test_checked_in_candidate_schema_benchmark_is_repeatable(self):
        first = run_adventure_turn_candidate_benchmark()
        second = run_adventure_turn_candidate_benchmark()
        self.assertEqual(BENCHMARK_VERSION, first["benchmark_version"])
        self.assertEqual(first, second)
        self.assertEqual(first["cases"], first["passed"])
        self.assertEqual(8, first["cases"])
        self.assertEqual(1.0, first["candidate_schema_pass_rate"])
        self.assertEqual(1.0, first["candidate_ordinary_schema_pass_rate"])
        self.assertEqual(1.0, first["candidate_typed_schema_pass_rate"])
        self.assertEqual(1.0, first["candidate_no_change_pass_rate"])
        self.assertIn("Adventure-Turn Candidate Evaluation", format_adventure_turn_candidate_result(first))

    def test_fixture_schema_rejects_invalid_case_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps({"benchmark_version": BENCHMARK_VERSION, "cases": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "1-100"):
                load_adventure_turn_candidate_cases(path)


if __name__ == "__main__":
    unittest.main()
