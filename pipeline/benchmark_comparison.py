"""Pure declared-metadata eligibility for controlled model scaling, not scoring.

No discovery, hashing of files, provider invocation, ledger access or export.
Caller-supplied hashes are commitments, not independently verified evidence.
Architecture ablations and hardware comparisons need separate comparison policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from pipeline.benchmark import (
    MAX_SCALING_PROFILES, BenchmarkRunManifest, benchmark_label, parse_benchmark_manifest,
)

COMPARISON_SCHEMA_VERSION = "starfur-model-comparison-v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_COMMIT = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z", re.ASCII)
_MISSING_REASONS = frozenset({"run_identity_missing", "git_revision_unresolved",
    "seed_missing", "hardware_missing", "context_size_missing", "quantization_missing",
    "architecture_fingerprint_unresolved"})
_MISMATCH_FIELDS = (
    ("benchmark_version", "benchmark_version_mismatch"),
    ("fixture_fingerprint", "fixture_mismatch"),
    ("policy_fingerprint", "policy_mismatch"),
    ("metric_fingerprint", "metric_contract_mismatch"),
    ("runtime_fingerprint", "runtime_mismatch"),
)
_MANIFEST_FIELDS = (
    ("benchmark_id", "benchmark_id_mismatch"), ("workload", "workload_mismatch"),
    ("architecture_fingerprint", "architecture_mismatch"), ("seed", "seed_mismatch"),
    ("hardware", "hardware_mismatch"), ("git_commit", "git_revision_mismatch"),
)
_INCOMPATIBLE_REASONS = frozenset({"duplicate_run_identity", "no_model_variation",
    "context_size_mismatch", *(reason for _, reason in _MISMATCH_FIELDS),
    *(reason for _, reason in _MANIFEST_FIELDS)})


def _digest(value: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ValueError("comparison binding requires an exact SHA-256 digest")
    return value


@dataclass(frozen=True)
class ModelComparisonEvidence:
    """One manifest plus caller-declared fixture/policy/measurement commitments."""

    manifest: BenchmarkRunManifest
    benchmark_version: str
    fixture_fingerprint: str
    policy_fingerprint: str
    metric_fingerprint: str
    runtime_fingerprint: str
    model_fingerprint: str

    def __post_init__(self):
        if not isinstance(self.manifest, BenchmarkRunManifest):
            raise ValueError("comparison requires a validated benchmark manifest")
        # Defensive revalidation; never accept a loose profile/manifest mapping.
        object.__setattr__(self, "manifest", parse_benchmark_manifest(self.manifest.to_dict()))
        object.__setattr__(self, "benchmark_version", benchmark_label(self.benchmark_version))
        for field in ("fixture_fingerprint", "policy_fingerprint", "metric_fingerprint",
                "runtime_fingerprint", "model_fingerprint"):
            _digest(getattr(self, field))


@dataclass(frozen=True)
class ModelComparisonDecision:
    status: str
    reasons: tuple[str, ...]
    run_count: int
    model_configuration_count: int

    def __post_init__(self):
        if any(isinstance(value, bool) or not isinstance(value, int) for value in
                (self.run_count, self.model_configuration_count)) or not (
                2 <= self.run_count <= MAX_SCALING_PROFILES and
                1 <= self.model_configuration_count <= self.run_count):
            raise ValueError("comparison counts are invalid")
        if not isinstance(self.status, str):
            raise ValueError("comparison outcome is invalid")
        allowed = {"metadata_compatible": frozenset(), "insufficient_metadata": _MISSING_REASONS,
            "incompatible": _INCOMPATIBLE_REASONS}.get(self.status)
        if allowed is None or not isinstance(self.reasons, tuple) or any(
                not isinstance(reason, str) or reason not in allowed for reason in self.reasons):
            raise ValueError("comparison outcome is invalid")
        if self.reasons != tuple(sorted(set(self.reasons))) or (
                (self.status == "metadata_compatible") != (not self.reasons)):
            raise ValueError("comparison reasons are inconsistent")
        if self.status == "metadata_compatible" and self.model_configuration_count < 2:
            raise ValueError("comparison requires model variation")

    def to_dict(self) -> dict:
        """Counts and closed labels only; omit run IDs, hashes and environment."""
        return {"schema_version": COMPARISON_SCHEMA_VERSION, "status": self.status,
            "reasons": list(self.reasons), "run_count": self.run_count,
            "model_configuration_count": self.model_configuration_count}


def evaluate_model_scaling_comparison(
    evidence: list[ModelComparisonEvidence] | tuple[ModelComparisonEvidence, ...],
) -> ModelComparisonDecision:
    """Accept only complete, matched declarations; never rank results or run work."""
    if not isinstance(evidence, (list, tuple)) or not 2 <= len(evidence) <= MAX_SCALING_PROFILES:
        raise ValueError("comparison requires two to 32 evidence records")
    if not all(isinstance(item, ModelComparisonEvidence) for item in evidence):
        raise ValueError("comparison evidence is invalid")
    configurations = {(item.manifest.model_profile.provider, item.manifest.model_profile.model,
        item.manifest.model_profile.quantization, item.model_fingerprint) for item in evidence}
    missing = set()
    for item in evidence:
        manifest = item.manifest
        if manifest.run_id is None:
            missing.add("run_identity_missing")
        if manifest.git_commit is None or not _COMMIT.fullmatch(manifest.git_commit):
            missing.add("git_revision_unresolved")
        if not _DIGEST.fullmatch(manifest.architecture_fingerprint):
            missing.add("architecture_fingerprint_unresolved")
        if manifest.seed is None:
            missing.add("seed_missing")
        if not manifest.hardware:
            missing.add("hardware_missing")
        if manifest.model_profile.context_size is None:
            missing.add("context_size_missing")
        if manifest.model_profile.quantization is None:
            missing.add("quantization_missing")
    if missing:
        return ModelComparisonDecision("insufficient_metadata", tuple(sorted(missing)),
            len(evidence), len(configurations))
    incompatible = set()
    if len({item.manifest.run_id for item in evidence}) != len(evidence):
        incompatible.add("duplicate_run_identity")
    if len(configurations) < 2:
        incompatible.add("no_model_variation")
    first = evidence[0]
    for item in evidence[1:]:
        for field, reason in _MISMATCH_FIELDS:
            if getattr(item, field) != getattr(first, field):
                incompatible.add(reason)
        for field, reason in _MANIFEST_FIELDS:
            if getattr(item.manifest, field) != getattr(first.manifest, field):
                incompatible.add(reason)
        if item.manifest.model_profile.context_size != first.manifest.model_profile.context_size:
            incompatible.add("context_size_mismatch")
    return ModelComparisonDecision("incompatible" if incompatible else "metadata_compatible",
        tuple(sorted(incompatible)), len(evidence), len(configurations))


__all__ = ["COMPARISON_SCHEMA_VERSION", "ModelComparisonEvidence",
    "ModelComparisonDecision", "evaluate_model_scaling_comparison"]
