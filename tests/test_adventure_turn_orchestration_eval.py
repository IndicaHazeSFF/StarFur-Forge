import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_turn_orchestration_eval import (
    BENCHMARK_VERSION,
    format_adventure_turn_orchestration_result,
    run_adventure_turn_orchestration_benchmark,
)


class AdventureTurnOrchestrationEvaluationTests(unittest.TestCase):
    def test_checked_in_c3_orchestration_evaluation_is_repeatable(self):
        first = run_adventure_turn_orchestration_benchmark()
        second = run_adventure_turn_orchestration_benchmark()
        self.assertEqual(BENCHMARK_VERSION, first["benchmark_version"])
        self.assertEqual(first, second)
        self.assertEqual(4, len(first["results"]))
        self.assertTrue(all(item["pass"] for item in first["results"]))
        self.assertEqual(1.0, first["generation_success_rate"])
        self.assertEqual(1.0, first["candidate_validation_success_rate"])
        self.assertEqual(1.0, first["core_use_success_rate"])
        self.assertEqual(1.0, first["canonical_commit_success_rate"])
        self.assertIn("Adventure-Turn Orchestration Evaluation", format_adventure_turn_orchestration_result(first))


if __name__ == "__main__":
    unittest.main()
