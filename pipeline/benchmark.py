"""Small, provider-neutral benchmark manifests for reproducible evaluation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

BENCHMARK_SCHEMA_VERSION = "starfur-benchmark-v1"


@dataclass(frozen=True)
class BenchmarkModelProfile:
    """One model/provider configuration in a scaling comparison."""

    provider: str
    model: str
    quantization: str | None = None
    context_size: int | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("provider and model are required")
        if self.context_size is not None and (isinstance(self.context_size, bool) or self.context_size <= 0):
            raise ValueError("context_size must be positive")


@dataclass(frozen=True)
class BenchmarkRunManifest:
    """Stable metadata identifying one benchmark run without raw conversation."""

    benchmark_id: str
    workload: str
    model_profile: BenchmarkModelProfile
    architecture_fingerprint: str
    seed: int | None = None
    hardware: Mapping[str, Any] = field(default_factory=dict)
    git_commit: str | None = None
    run_id: str | None = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = BENCHMARK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.benchmark_id.strip() or not self.workload.strip() or not self.architecture_fingerprint.strip():
            raise ValueError("benchmark_id, workload, and architecture_fingerprint are required")
        if self.seed is not None and isinstance(self.seed, bool):
            raise ValueError("seed must be an integer")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["model_profile"] = asdict(self.model_profile)
        value["hardware"] = dict(self.hardware)
        return value


def build_scaling_plan(benchmark_id: str, workload: str, profiles: list[BenchmarkModelProfile], *, architecture_fingerprint: str, seed: int | None = 420) -> dict[str, Any]:
    """Create a serializable same-workload/different-model scaling plan."""
    if not profiles:
        raise ValueError("at least one model profile is required")
    manifest = [BenchmarkRunManifest(benchmark_id, workload, profile, architecture_fingerprint, seed=seed) for profile in profiles]
    return {"schema_version": BENCHMARK_SCHEMA_VERSION, "benchmark_id": benchmark_id, "workload": workload, "runs": [item.to_dict() for item in manifest]}


__all__ = ["BENCHMARK_SCHEMA_VERSION", "BenchmarkModelProfile", "BenchmarkRunManifest", "build_scaling_plan"]