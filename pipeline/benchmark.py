"""Small, provider-neutral benchmark manifests for reproducible evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from types import MappingProxyType
from typing import Any, Mapping
import unicodedata

BENCHMARK_SCHEMA_VERSION = "starfur-benchmark-v1"
MAX_SCALING_PROFILES = 32
_MAX_LABEL_CHARS = 512
_MANIFEST_FIELDS = frozenset({"schema_version", "benchmark_id", "workload", "model_profile",
    "architecture_fingerprint", "seed", "hardware", "git_commit", "run_id", "started_at"})
_PROFILE_FIELDS = frozenset({"provider", "model", "quantization", "context_size"})
_HARDWARE_LABELS = frozenset({"profile", "os", "architecture", "cpu", "gpu", "runtime", "python_version"})
_HARDWARE_NUMBERS = frozenset({"ram_gb", "vram_gb", "logical_cores"})


def benchmark_label(value: Any) -> str:
    """Bound supplied public labels; not a secret/content classifier."""
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_LABEL_CHARS:
        raise ValueError("benchmark metadata label is invalid")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise ValueError("benchmark metadata label is invalid") from None
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError("benchmark metadata label is invalid")
    return value.strip()


def _optional_label(value: Any) -> str | None:
    return None if value is None else benchmark_label(value)


def _hardware_snapshot(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) - (_HARDWARE_LABELS | _HARDWARE_NUMBERS):
        raise ValueError("benchmark hardware metadata fields are unsupported")
    snapshot = {}
    for key, item in value.items():
        if key in _HARDWARE_LABELS:
            snapshot[key] = benchmark_label(item)
        elif key == "logical_cores":
            if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 1_000_000:
                raise ValueError("benchmark hardware count is invalid")
            snapshot[key] = item
        else:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not 0 <= item <= 1_000_000_000 or not math.isfinite(item):
                raise ValueError("benchmark hardware measurement is invalid")
            snapshot[key] = item
    return MappingProxyType(snapshot)


@dataclass(frozen=True)
class BenchmarkModelProfile:
    """One model/provider configuration in a scaling comparison."""

    provider: str
    model: str
    quantization: str | None = None
    context_size: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", benchmark_label(self.provider))
        object.__setattr__(self, "model", benchmark_label(self.model))
        object.__setattr__(self, "quantization", _optional_label(self.quantization))
        if self.context_size is not None and (isinstance(self.context_size, bool)
                or not isinstance(self.context_size, int) or not 1 <= self.context_size < 2**31):
            raise ValueError("benchmark context size is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model,
            "quantization": self.quantization, "context_size": self.context_size}


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
        if self.schema_version != BENCHMARK_SCHEMA_VERSION:
            raise ValueError("benchmark manifest version is unsupported")
        if not isinstance(self.model_profile, BenchmarkModelProfile):
            raise ValueError("benchmark manifest requires a validated model profile")
        for name in ("benchmark_id", "workload", "architecture_fingerprint"):
            object.__setattr__(self, name, benchmark_label(getattr(self, name)))
        for name in ("git_commit", "run_id"):
            object.__setattr__(self, name, _optional_label(getattr(self, name)))
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int)
                or not -(2**63) <= self.seed < 2**63):
            raise ValueError("benchmark seed is invalid")
        timestamp = benchmark_label(self.started_at)
        try:
            parsed = datetime.fromisoformat(timestamp)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError
        except ValueError:
            raise ValueError("benchmark timestamp requires an aware ISO date/time") from None
        object.__setattr__(self, "started_at", timestamp)
        object.__setattr__(self, "hardware", _hardware_snapshot(self.hardware))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "benchmark_id": self.benchmark_id,
            "workload": self.workload, "model_profile": self.model_profile.to_dict(),
            "architecture_fingerprint": self.architecture_fingerprint, "seed": self.seed,
            "hardware": dict(self.hardware), "git_commit": self.git_commit,
            "run_id": self.run_id, "started_at": self.started_at}


def parse_benchmark_manifest(value: Mapping[str, Any]) -> BenchmarkRunManifest:
    """Revalidate one exact serialized v1 shape without reading a ledger."""
    if not isinstance(value, Mapping) or set(value) != _MANIFEST_FIELDS:
        raise ValueError("benchmark manifest must use the exact bounded schema")
    profile = value["model_profile"]
    if not isinstance(profile, Mapping) or set(profile) != _PROFILE_FIELDS:
        raise ValueError("benchmark manifest profile must use the exact bounded schema")
    arguments = dict(value)
    arguments["model_profile"] = BenchmarkModelProfile(**profile)
    return BenchmarkRunManifest(**arguments)


def build_scaling_plan(benchmark_id: str, workload: str, profiles: list[BenchmarkModelProfile], *, architecture_fingerprint: str, seed: int | None = 420, started_at: str | None = None) -> dict[str, Any]:
    """Create a serializable same-workload/different-model scaling plan."""
    if not isinstance(profiles, (list, tuple)) or not 1 <= len(profiles) <= MAX_SCALING_PROFILES:
        raise ValueError("scaling plan requires one to 32 model profiles")
    timestamp = datetime.now(timezone.utc).isoformat() if started_at is None else started_at
    manifest = [BenchmarkRunManifest(benchmark_id, workload, profile, architecture_fingerprint,
        seed=seed, started_at=timestamp) for profile in profiles]
    return {"schema_version": BENCHMARK_SCHEMA_VERSION, "benchmark_id": manifest[0].benchmark_id,
        "workload": manifest[0].workload, "runs": [item.to_dict() for item in manifest]}


__all__ = ["BENCHMARK_SCHEMA_VERSION", "MAX_SCALING_PROFILES", "BenchmarkModelProfile",
    "BenchmarkRunManifest", "benchmark_label", "parse_benchmark_manifest", "build_scaling_plan"]
