import unittest
from pipeline.benchmark import BENCHMARK_SCHEMA_VERSION, BenchmarkModelProfile, BenchmarkRunManifest, build_scaling_plan


class BenchmarkManifestTests(unittest.TestCase):
    def test_manifest_is_serializable_and_bounded(self):
        manifest = BenchmarkRunManifest("retrieval-001", "memory-recall", BenchmarkModelProfile("Ollama", "qwen3:8b", "q4", 8192), "core-abc", seed=420, hardware={"gpu": "RTX 4070"})
        value = manifest.to_dict()
        self.assertEqual(value["schema_version"], BENCHMARK_SCHEMA_VERSION)
        self.assertEqual(value["model_profile"]["model"], "qwen3:8b")
        self.assertEqual(value["hardware"]["gpu"], "RTX 4070")

    def test_scaling_plan_holds_workload_and_architecture_constant(self):
        plan = build_scaling_plan("scale-001", "assistant-memory-recall", [
            BenchmarkModelProfile("Ollama", "ministral-3:3b"),
            BenchmarkModelProfile("Ollama", "qwen3:8b"),
        ], architecture_fingerprint="core-abc")
        self.assertEqual(len(plan["runs"]), 2)
        self.assertEqual({run["workload"] for run in plan["runs"]}, {"assistant-memory-recall"})
        self.assertEqual({run["architecture_fingerprint"] for run in plan["runs"]}, {"core-abc"})

    def test_invalid_profiles_are_rejected(self):
        with self.assertRaises(ValueError):
            BenchmarkModelProfile("", "qwen3:8b")
        with self.assertRaises(ValueError):
            build_scaling_plan("scale", "workload", [], architecture_fingerprint="core")


if __name__ == "__main__":
    unittest.main()