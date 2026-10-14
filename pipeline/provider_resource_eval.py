"""Deterministic provider-free inference-resource admission evaluation.

The fixture proves only that Core's declared admission policy remains stable.
It does not observe a host, invoke a provider, reserve a resource, or claim a
backend enforces any of these controls.
"""

from __future__ import annotations

from typing import Any, Mapping

from pipeline.provider_resource_policy import (
    CONTROL_CONCURRENCY,
    CONTROL_MODEL_RESIDENCY,
    CONTROL_OUTPUT_TOKENS,
    CONTROL_VERIFIED_CANCELLATION,
    CONTROL_WALL_TIME,
    InferenceBackendResourceCapabilities,
    InferenceResourceProfile,
    PROFILE_BACKGROUND,
    PROFILE_BALANCED,
    PROFILE_INTERACTIVE,
    evaluate_inference_resource_admission,
)


BENCHMARK_VERSION = "provider-resource-admission-v1"
_BASE_CONTROLS = frozenset({
    CONTROL_WALL_TIME, CONTROL_OUTPUT_TOKENS, CONTROL_CONCURRENCY,
    CONTROL_VERIFIED_CANCELLATION,
})


def _case(name: str, profile: InferenceResourceProfile, controls: frozenset[str], *, foreground_busy: bool, expected_status: str, expected_reasons: tuple[str, ...]) -> dict[str, object]:
    actual = evaluate_inference_resource_admission(
        profile, InferenceBackendResourceCapabilities("fixture.backend", controls),
        foreground_busy=foreground_busy,
    )
    return {
        "name": name, "kind": "provider_resource_admission",
        "expected_status": expected_status, "actual_status": actual.status,
        "expected_reasons": list(expected_reasons), "actual_reasons": list(actual.reasons),
        "pass": actual.status == expected_status and actual.reasons == expected_reasons,
    }


def run_provider_resource_admission_benchmark() -> dict[str, object]:
    """Evaluate fixed policy cases without live provider or host access."""
    interactive = InferenceResourceProfile(PROFILE_INTERACTIVE, 30, 256)
    balanced = InferenceResourceProfile(PROFILE_BALANCED, 60, 512)
    background = InferenceResourceProfile(
        PROFILE_BACKGROUND, 120, 1024, require_model_residency_control=True,
    )
    results = [
        _case("interactive_minimum_controls_admitted", interactive, _BASE_CONTROLS,
              foreground_busy=True, expected_status="admitted", expected_reasons=()),
        _case("balanced_yields_to_foreground", balanced, _BASE_CONTROLS,
              foreground_busy=True, expected_status="deferred", expected_reasons=("foreground_busy",)),
        _case("background_requires_verified_cancellation", background,
              _BASE_CONTROLS - {CONTROL_VERIFIED_CANCELLATION}, foreground_busy=False,
              expected_status="deferred", expected_reasons=(
                  "control_unavailable:model_residency", "control_unavailable:verified_cancellation",
              )),
        _case("background_requires_residency_control", background, _BASE_CONTROLS,
              foreground_busy=False, expected_status="deferred",
              expected_reasons=("control_unavailable:model_residency",)),
    ]
    total = len(results)
    return {
        "benchmark_version": BENCHMARK_VERSION, "repeatability": True,
        "cases": total,
        "resource_admission_pass_rate": sum(item["pass"] for item in results) / total,
        "results": results,
    }


def format_provider_resource_admission_result(result: Mapping[str, Any]) -> str:
    """Render only aggregate fixture outcomes, never backend configuration."""
    lines = [
        "Provider Resource Admission Evaluation",
        "--------------------------------------",
        f"Benchmark:          {result['benchmark_version']}",
        f"Cases:              {result['cases']}",
        f"Pass rate:          {result['resource_admission_pass_rate']:.1%}",
        f"Repeatability:      {'PASS' if result['repeatability'] else 'FAIL'}",
    ]
    failures = [item for item in result["results"] if not item["pass"]]
    if failures:
        lines.extend(("", "Failures", "--------"))
        lines.extend(f"{item['name']}: {item['actual_status']}" for item in failures)
    return "\n".join(lines)


__all__ = ["BENCHMARK_VERSION", "format_provider_resource_admission_result", "run_provider_resource_admission_benchmark"]
