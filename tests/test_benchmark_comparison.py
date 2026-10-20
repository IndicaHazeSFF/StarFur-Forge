"""Synthetic declarations only; no provider, runtime data, host probes or I/O."""
from dataclasses import replace
import json
import unittest

from pipeline.benchmark import BenchmarkModelProfile, BenchmarkRunManifest
from pipeline.benchmark_comparison import (
    ModelComparisonDecision, ModelComparisonEvidence, evaluate_model_scaling_comparison,
)


def evidence(run_id="synthetic-a", model="small-model", model_digest="1" * 64):
    manifest = BenchmarkRunManifest("synthetic-fixture", "fixed-workload",
        BenchmarkModelProfile("internal", model, "q4", 4096), "a" * 64,
        seed=420, hardware={"profile": "synthetic-host", "ram_gb": 32},
        git_commit="b" * 40, run_id=run_id, started_at="2026-10-14T00:00:00Z")
    return ModelComparisonEvidence(manifest, "synthetic-v1", "c" * 64, "d" * 64,
        "e" * 64, "f" * 64, model_digest)


class ModelComparisonTests(unittest.TestCase):
    def setUp(self):
        self.first = evidence()
        self.second = evidence("synthetic-b", "larger-model", "2" * 64)

    def decision(self, second=None):
        return evaluate_model_scaling_comparison([self.first, self.second if second is None else second])

    def test_complete_matched_declarations_are_repeatable(self):
        result = self.decision()
        self.assertEqual("metadata_compatible", result.status)
        self.assertEqual((), result.reasons)
        self.assertEqual(2, result.model_configuration_count)
        self.assertEqual(result, self.decision())

    def test_each_evidence_mismatch_is_incompatible(self):
        for field, value, reason in (
                ("benchmark_version", "synthetic-v2", "benchmark_version_mismatch"),
                ("fixture_fingerprint", "0" * 64, "fixture_mismatch"),
                ("policy_fingerprint", "0" * 64, "policy_mismatch"),
                ("metric_fingerprint", "0" * 64, "metric_contract_mismatch"),
                ("runtime_fingerprint", "0" * 64, "runtime_mismatch")):
            with self.subTest(field=field):
                result = self.decision(replace(self.second, **{field: value}))
                self.assertEqual("incompatible", result.status)
                self.assertEqual((reason,), result.reasons)

    def test_each_manifest_mismatch_is_incompatible(self):
        for field, value, reason in (
                ("benchmark_id", "different-fixture", "benchmark_id_mismatch"),
                ("workload", "different-work", "workload_mismatch"),
                ("architecture_fingerprint", "0" * 64, "architecture_mismatch"),
                ("seed", 421, "seed_mismatch"),
                ("hardware", {"profile": "different-host"}, "hardware_mismatch"),
                ("git_commit", "0" * 40, "git_revision_mismatch")):
            with self.subTest(field=field):
                result = self.decision(replace(self.second,
                    manifest=replace(self.second.manifest, **{field: value})))
                self.assertEqual("incompatible", result.status)
                self.assertEqual((reason,), result.reasons)

    def test_missing_metadata_is_not_assumed_equal_or_measured(self):
        for field, value, reason in (
                ("run_id", None, "run_identity_missing"),
                ("git_commit", "short-label", "git_revision_unresolved"),
                ("git_commit", None, "git_revision_unresolved"),
                ("architecture_fingerprint", "label-only", "architecture_fingerprint_unresolved"),
                ("seed", None, "seed_missing"), ("hardware", {}, "hardware_missing")):
            with self.subTest(field=field):
                incomplete = replace(self.second, manifest=replace(self.second.manifest, **{field: value}))
                result = self.decision(incomplete)
                self.assertEqual("insufficient_metadata", result.status)
                self.assertEqual((reason,), result.reasons)

    def test_context_and_quantization_defaults_are_insufficient(self):
        for field, reason in (("context_size", "context_size_missing"),
                ("quantization", "quantization_missing")):
            profile = replace(self.second.manifest.model_profile, **{field: None})
            result = self.decision(replace(self.second, manifest=replace(self.second.manifest, model_profile=profile)))
            self.assertEqual("insufficient_metadata", result.status)
            self.assertEqual((reason,), result.reasons)

    def test_context_budget_mismatch_rejects_apparent_scaling(self):
        profile = replace(self.second.manifest.model_profile, context_size=8192)
        result = self.decision(replace(self.second, manifest=replace(self.second.manifest, model_profile=profile)))
        self.assertEqual(("context_size_mismatch",), result.reasons)

    def test_distinct_run_identity_and_model_variation_are_required(self):
        result = self.decision(replace(self.second, manifest=replace(self.second.manifest, run_id=self.first.manifest.run_id)))
        self.assertEqual(("duplicate_run_identity",), result.reasons)
        result = self.decision(replace(self.first, manifest=replace(self.first.manifest, run_id="synthetic-b")))
        self.assertEqual(("no_model_variation",), result.reasons)

    def test_replicates_are_allowed_but_cannot_be_counted_twice(self):
        replicate = replace(self.first, manifest=replace(self.first.manifest, run_id="synthetic-c"))
        result = evaluate_model_scaling_comparison([self.first, self.second, replicate])
        self.assertEqual("metadata_compatible", result.status)
        self.assertEqual((3, 2), (result.run_count, result.model_configuration_count))

    def test_timestamp_variation_and_input_order_do_not_change_decision(self):
        second = replace(self.second, manifest=replace(self.second.manifest, started_at="2026-10-15T12:00:00Z"))
        self.assertEqual(self.decision(), self.decision(second))
        self.assertEqual(self.decision(), evaluate_model_scaling_comparison([self.second, self.first]))

    def test_malformed_bindings_and_untyped_input_are_rejected(self):
        for field in ("fixture_fingerprint", "policy_fingerprint", "metric_fingerprint",
                "runtime_fingerprint", "model_fingerprint"):
            for value in (None, "label", "A" * 64, "g" * 64, "0" * 65):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    replace(self.first, **{field: value})
        for items in ([], [self.first], [self.first] * 33, iter([self.first, self.second]),
                [self.first, {}]):
            with self.assertRaises(ValueError):
                evaluate_model_scaling_comparison(items)
        with self.assertRaises(ValueError):
            replace(self.first, manifest={})

    def test_result_exposes_closed_counts_not_identifiers_or_evidence(self):
        result = self.decision().to_dict()
        self.assertEqual({"schema_version", "status", "reasons", "run_count", "model_configuration_count"}, set(result))
        serialized = json.dumps(result, allow_nan=False)
        for secret in ("synthetic-a", "synthetic-host", "small-model", "a" * 64, "b" * 40):
            self.assertNotIn(secret, serialized)
        result["reasons"].append("tampered")
        self.assertEqual([], self.decision().to_dict()["reasons"])

    def test_decision_rejects_forged_status_counts_and_reason_payloads(self):
        for arguments in (("verified", (), 2, 2), ("metadata_compatible", (), True, 2),
                ("metadata_compatible", (), 2, 1), ("incompatible", ("raw secret",), 2, 2),
                ("insufficient_metadata", (), 2, 2), ([], (), 2, 2)):
            with self.assertRaises(ValueError):
                ModelComparisonDecision(*arguments)


if __name__ == "__main__":
    unittest.main()
