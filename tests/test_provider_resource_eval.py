import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.provider_resource_eval import (
    BENCHMARK_VERSION,
    format_provider_resource_admission_result,
    run_provider_resource_admission_benchmark,
)


class ProviderResourceAdmissionEvaluationTests(unittest.TestCase):
    def test_checked_in_fixture_is_deterministic_and_complete(self):
        first = run_provider_resource_admission_benchmark()
        self.assertEqual(first, run_provider_resource_admission_benchmark())
        self.assertEqual(first["benchmark_version"], BENCHMARK_VERSION)
        self.assertEqual(first["cases"], 4)
        self.assertEqual(first["resource_admission_pass_rate"], 1.0)
        self.assertTrue(all(item["pass"] for item in first["results"]))
        self.assertIn("Provider Resource Admission Evaluation", format_provider_resource_admission_result(first))
