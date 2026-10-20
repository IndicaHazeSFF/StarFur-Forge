import unittest
import json
from pipeline.benchmark import BENCHMARK_SCHEMA_VERSION, BenchmarkModelProfile, BenchmarkRunManifest, build_scaling_plan, parse_benchmark_manifest


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

    def manifest(self, **overrides):
        values = dict(benchmark_id="fixture", workload="fixed-workload",
            model_profile=BenchmarkModelProfile("internal", "fixture"),
            architecture_fingerprint="core-v1", started_at="2026-10-14T00:00:00+00:00")
        values.update(overrides)
        return BenchmarkRunManifest(**values)

    def test_profile_types_and_finite_context_ceiling_are_strict(self):
        for value in (True, 1.5, "4096", 0, -1, 2**31):
            with self.subTest(value=value), self.assertRaises(ValueError):
                BenchmarkModelProfile("internal", "fixture", context_size=value)
        for field in ("provider", "model", "quantization"):
            for value in (123, "", "x" * 513, "label\nprivate", "\ud800"):
                args = dict(provider="internal", model="fixture", quantization="q4")
                args[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    BenchmarkModelProfile(**args)

    def test_manifest_fields_seed_timestamp_and_version_are_strict(self):
        for field in ("benchmark_id", "workload", "architecture_fingerprint", "git_commit", "run_id"):
            for value in (123, "", "x" * 513, "x\x00y", "\ud800"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.manifest(**{field: value})
        for seed in (True, 1.5, "420", 2**63, -(2**63)-1):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                self.manifest(seed=seed)
        for timestamp in ("yesterday", "2026-10-14T00:00:00", "2026-02-30T00:00:00Z", 123):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                self.manifest(started_at=timestamp)
        with self.assertRaises(ValueError):
            self.manifest(schema_version="starfur-benchmark-v99")
        with self.assertRaises(ValueError):
            self.manifest(model_profile={"model": "untrusted"})

    def test_hardware_metadata_rejects_extra_content_and_invalid_values(self):
        for hardware in ({"raw_prompt": "private"}, {"hostname": "private"},
                {"gpu": {"nested": "private"}}, {"gpu": 4070}, {"ram_gb": float("nan")},
                {"ram_gb": float("inf")}, {"ram_gb": -1}, {"logical_cores": True},
                {"logical_cores": 1.5}, {"logical_cores": 0}, {"profile": "a\nb"}, [], None):
            with self.subTest(hardware=hardware), self.assertRaises(ValueError):
                self.manifest(hardware=hardware)

    def test_hardware_snapshot_and_serialization_are_independent(self):
        original = {"gpu": "Synthetic GPU", "ram_gb": 32, "logical_cores": 8}
        manifest = self.manifest(hardware=original)
        original["gpu"] = "changed"
        original["raw_prompt"] = "private"
        with self.assertRaises(TypeError):
            manifest.hardware["gpu"] = "changed"
        serialized = manifest.to_dict()
        serialized["hardware"]["gpu"] = "changed"
        self.assertEqual("Synthetic GPU", manifest.to_dict()["hardware"]["gpu"])
        self.assertNotIn("raw_prompt", manifest.to_dict()["hardware"])
        self.assertEqual(manifest.to_dict(), json.loads(json.dumps(manifest.to_dict(), allow_nan=False)))

    def test_manifest_round_trip_and_unknown_fields_fail_closed(self):
        manifest = self.manifest(hardware={"profile": "synthetic"}, seed=420)
        self.assertEqual(manifest.to_dict(), parse_benchmark_manifest(manifest.to_dict()).to_dict())
        for field in manifest.to_dict():
            data = manifest.to_dict()
            del data[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                parse_benchmark_manifest(data)
        data = manifest.to_dict()
        data["raw_response"] = "private"
        with self.assertRaises(ValueError):
            parse_benchmark_manifest(data)
        data = manifest.to_dict()
        data["model_profile"]["api_key"] = "private"
        with self.assertRaises(ValueError):
            parse_benchmark_manifest(data)
        with self.assertRaises(ValueError):
            parse_benchmark_manifest([])

    def test_scaling_plan_count_and_metadata_are_bounded(self):
        profile = BenchmarkModelProfile("internal", "fixture")
        with self.assertRaises(ValueError):
            build_scaling_plan("fixture", "work", [profile] * 33, architecture_fingerprint="core")
        with self.assertRaises(ValueError):
            build_scaling_plan("fixture", "work", [object()], architecture_fingerprint="core")

    def test_explicit_timestamp_makes_scaling_plan_deterministic(self):
        arguments = dict(benchmark_id=" fixture ", workload=" work ",
            profiles=[BenchmarkModelProfile("internal", "fixture")],
            architecture_fingerprint="core", started_at="2026-10-14T00:00:00Z")
        self.assertEqual(build_scaling_plan(**arguments), build_scaling_plan(**arguments))
        self.assertEqual("fixture", build_scaling_plan(**arguments)["benchmark_id"])
        self.assertEqual("work", build_scaling_plan(**arguments)["workload"])


if __name__ == "__main__":
    unittest.main()
