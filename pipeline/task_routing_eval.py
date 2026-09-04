"""Deterministic provider-route portability evaluation with no live adapters.

The fixture suite checks only declarative profiles and caller-supplied provider
status records.  It never constructs or probes a provider, retains no prompt,
and does not read runtime state or the experiment ledger.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from pipeline.task_profiles import load_task_profiles
from pipeline.task_routing import (
    ProviderRouteRegistry,
    ProviderRouteStatus,
    TaskRoutePlanner,
)


BENCHMARK_VERSION = "task-routing-portability-v1"
DEFAULT_CASES_PATH = Path("tests/fixtures/task_routing_cases.json")
_EXPECTED_FIELDS = frozenset({
    "status", "selected_task_id", "selected_provider", "fallback_used",
})


def load_task_routing_cases(path: str | Path = DEFAULT_CASES_PATH) -> tuple[dict[str, object], ...]:
    """Load the checked-in, metadata-only route portability fixture."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Task routing benchmark fixture is unreadable") from error
    if not isinstance(payload, Mapping) or payload.get("benchmark_version") != BENCHMARK_VERSION:
        raise ValueError("Task routing benchmark fixture is invalid")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Task routing benchmark cases are invalid")
    normalized = tuple(_validate_case(case) for case in cases)
    if len({case["name"] for case in normalized}) != len(normalized):
        raise ValueError("Task routing benchmark case names must be unique")
    return normalized


def _validate_case(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("Task routing benchmark case is invalid")
    required = {"name", "task_id", "default_model", "default_provider_id", "profiles", "providers", "expected"}
    if set(value) != required:
        raise ValueError("Task routing benchmark case fields are invalid")
    name = value["name"]
    task_id = value["task_id"]
    default_model = value["default_model"]
    default_provider_id = value["default_provider_id"]
    if not all(isinstance(item, str) and item.strip() for item in (name, task_id, default_model, default_provider_id)):
        raise ValueError("Task routing benchmark identifiers are invalid")
    if not isinstance(value["profiles"], Mapping) or not isinstance(value["providers"], Mapping):
        raise ValueError("Task routing benchmark configuration is invalid")
    expected = value["expected"]
    if not isinstance(expected, Mapping) or set(expected) != _EXPECTED_FIELDS:
        raise ValueError("Task routing benchmark expectation is invalid")
    if expected["status"] not in {"routable", "unavailable"} or not isinstance(expected["fallback_used"], bool):
        raise ValueError("Task routing benchmark expectation is invalid")
    for key in ("selected_task_id", "selected_provider"):
        if expected[key] is not None and (not isinstance(expected[key], str) or not expected[key].strip()):
            raise ValueError("Task routing benchmark expectation is invalid")
    return {
        "name": name.strip(),
        "task_id": task_id.strip(),
        "default_model": default_model.strip(),
        "default_provider_id": default_provider_id.strip(),
        "profiles": dict(value["profiles"]),
        "providers": dict(value["providers"]),
        "expected": dict(expected),
    }


def _provider_registry(value: Mapping[str, object]) -> ProviderRouteRegistry:
    providers: dict[str, ProviderRouteStatus] = {}
    for provider_id, raw_status in value.items():
        if not isinstance(raw_status, Mapping) or set(raw_status) != {"status", "capabilities"}:
            raise ValueError("Task routing benchmark provider status is invalid")
        capabilities = raw_status["capabilities"]
        if not isinstance(capabilities, list) or not capabilities:
            raise ValueError("Task routing benchmark provider capabilities are invalid")
        providers[provider_id] = ProviderRouteStatus(
            provider_id,
            raw_status["status"],
            frozenset(capabilities),
        )
    return ProviderRouteRegistry(providers)


def run_task_routing_benchmark(
    cases: tuple[dict[str, object], ...] | None = None,
) -> dict[str, object]:
    """Evaluate route decisions using fixtures only and retain bounded results."""
    cases = load_task_routing_cases() if cases is None else cases
    results: list[dict[str, object]] = []
    for case in cases:
        profiles = load_task_profiles(case["profiles"])
        planner = TaskRoutePlanner(profiles, _provider_registry(case["providers"]))
        decision = planner.plan(
            case["task_id"],
            default_model=case["default_model"],
            default_provider_id=case["default_provider_id"],
        ).public_dict()
        actual = {
            "status": decision["status"],
            "selected_task_id": decision["selected_task_id"],
            "selected_provider": decision["selected_provider"],
            "fallback_used": decision["fallback_used"],
        }
        expected = case["expected"]
        results.append({
            "name": case["name"],
            "kind": "task_routing",
            "expected_status": expected["status"],
            "actual_status": actual["status"],
            "expected_selected_task_id": expected["selected_task_id"],
            "actual_selected_task_id": actual["selected_task_id"],
            "expected_selected_provider": expected["selected_provider"],
            "actual_selected_provider": actual["selected_provider"],
            "expected_fallback_used": expected["fallback_used"],
            "actual_fallback_used": actual["fallback_used"],
            "pass": actual == expected,
        })
    total = len(results)
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "repeatability": True,
        "cases": total,
        "pass_rate": sum(item["pass"] for item in results) / total if total else 0.0,
        "routing_pass_rate": sum(item["pass"] for item in results) / total if total else 0.0,
        "results": results,
    }


def format_task_routing_result(result: Mapping[str, Any]) -> str:
    """Render only route outcome metadata, never fixture configuration."""
    lines = [
        "Task Routing Portability Evaluation",
        "----------------------------------",
        f"Benchmark:          {result['benchmark_version']}",
        f"Cases:              {result['cases']}",
        f"Pass rate:          {result['pass_rate']:.1%}",
        f"Repeatability:      {'PASS' if result['repeatability'] else 'FAIL'}",
    ]
    failures = [item for item in result["results"] if not item["pass"]]
    if failures:
        lines.extend(("", "Failures", "--------"))
        for item in failures:
            lines.append(
                f"{item['name']}: expected={item['expected_status']} / "
                f"{item['expected_selected_provider']}; actual={item['actual_status']} / "
                f"{item['actual_selected_provider']}"
            )
    return "\n".join(lines)


__all__ = [
    "BENCHMARK_VERSION", "DEFAULT_CASES_PATH", "format_task_routing_result",
    "load_task_routing_cases", "run_task_routing_benchmark",
]
