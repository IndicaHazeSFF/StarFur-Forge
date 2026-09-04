import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.task_routing_eval import (
    BENCHMARK_VERSION,
    format_task_routing_result,
    run_task_routing_benchmark,
)


class TaskRoutingEvaluationTests(unittest.TestCase):
    def test_checked_in_route_portability_evaluation_is_repeatable(self):
        first = run_task_routing_benchmark()
        second = run_task_routing_benchmark()

        self.assertEqual(BENCHMARK_VERSION, first["benchmark_version"])
        self.assertEqual(first, second)
        self.assertEqual(4, first["cases"])
        self.assertEqual(1.0, first["pass_rate"])
        self.assertTrue(all(item["pass"] for item in first["results"]))
        self.assertIn("Task Routing Portability Evaluation", format_task_routing_result(first))


if __name__ == "__main__":
    unittest.main()
