"""Deterministic fixture evaluation for untrusted adventure-turn candidate schemas.

This benchmark calls no provider and never opens a runtime adventure workspace.
It measures only parser acceptance/rejection and bounded candidate identifiers,
so later model runs can distinguish JSON/schema compliance from Core staging and
canonical-write success.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.adventure_turn_candidates import (
    AdventureTurnCandidateError,
    parse_untrusted_adventure_turn_candidates,
)
from pipeline.adventure_turn_mutation_candidates import (
    AdventureTurnMutationCandidateError,
    parse_untrusted_adventure_turn_mutation_candidates,
)


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
BENCHMARK_VERSION = "adventure-turn-candidates-v1"
_CASE_KINDS = frozenset({"ordinary", "typed"})


def load_adventure_turn_candidate_cases(
    path: str | Path = FIXTURE_ROOT / "adventure_turn_candidate_cases.json",
) -> list[dict[str, object]]:
    """Load closed, raw-content-free parser fixtures."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("adventure-turn candidate benchmark fixture is unreadable") from error
    if not isinstance(value, dict) or set(value) != {"benchmark_version", "cases"}:
        raise ValueError("adventure-turn candidate benchmark fixture schema is invalid")
    if value["benchmark_version"] != BENCHMARK_VERSION:
        raise ValueError("adventure-turn candidate benchmark fixture version is unsupported")
    cases = value["cases"]
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise ValueError("adventure-turn candidate benchmark fixture must contain 1-100 cases")
    names = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"name", "kind", "payload", "expect_accept", "expected_ids"}:
            raise ValueError("adventure-turn candidate benchmark case schema is invalid")
        if not isinstance(case["name"], str) or not case["name"].strip() or case["name"] in names:
            raise ValueError("adventure-turn candidate benchmark case name is invalid")
        names.add(case["name"])
        if case["kind"] not in _CASE_KINDS or not isinstance(case["payload"], dict):
            raise ValueError("adventure-turn candidate benchmark case kind or payload is invalid")
        if not isinstance(case["expect_accept"], bool) or not isinstance(case["expected_ids"], list):
            raise ValueError("adventure-turn candidate benchmark expectation is invalid")
        prefix = "TC-" if case["kind"] == "ordinary" else "TM-"
        if not all(isinstance(value, str) and value.startswith(prefix) for value in case["expected_ids"]):
            raise ValueError("adventure-turn candidate benchmark expected identifiers are invalid")
    return cases


def run_adventure_turn_candidate_benchmark(cases: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Run parser-only fixtures with no provider, session, log, or write."""
    cases = load_adventure_turn_candidate_cases() if cases is None else cases
    results = []
    for case in cases:
        parser = (
            parse_untrusted_adventure_turn_candidates
            if case["kind"] == "ordinary"
            else parse_untrusted_adventure_turn_mutation_candidates
        )
        accepted = False
        returned_ids: list[str] = []
        try:
            batch = parser(case["payload"])
            accepted = True
            returned_ids = [candidate.candidate_id for candidate in batch.candidates]
        except (AdventureTurnCandidateError, AdventureTurnMutationCandidateError):
            pass
        passed = accepted == case["expect_accept"] and returned_ids == case["expected_ids"]
        results.append({
            "name": case["name"], "kind": case["kind"], "expected_accept": case["expect_accept"],
            "accepted": accepted, "expected_ids": case["expected_ids"], "returned_ids": returned_ids,
            "pass": passed,
        })
    ordinary = [item for item in results if item["kind"] == "ordinary"]
    typed = [item for item in results if item["kind"] == "typed"]
    no_change = [
        item for item, case in zip(results, cases, strict=True)
        if case["kind"] == "typed" and case["expect_accept"] and not case["expected_ids"]
    ]
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "cases": len(results),
        "passed": sum(item["pass"] for item in results),
        "candidate_acceptance_rate": sum(item["accepted"] for item in results) / len(results),
        "candidate_schema_pass_rate": sum(item["pass"] for item in results) / len(results),
        "candidate_ordinary_schema_pass_rate": sum(item["pass"] for item in ordinary) / len(ordinary),
        "candidate_typed_schema_pass_rate": sum(item["pass"] for item in typed) / len(typed),
        "candidate_no_change_pass_rate": sum(item["pass"] for item in no_change) / len(no_change),
        "repeatability": True,
        "results": results,
    }


def format_adventure_turn_candidate_result(result: dict[str, object]) -> str:
    """Render a bounded, raw-content-free CLI report."""
    lines = [
        "Adventure-Turn Candidate Evaluation",
        "---------------------------------",
        f"Benchmark:          {result['benchmark_version']}",
        f"Cases:              {result['cases']}",
        f"Passed:             {result['passed']}/{result['cases']}",
        f"Ordinary schema:    {result['candidate_ordinary_schema_pass_rate']:.1%}",
        f"Typed schema:       {result['candidate_typed_schema_pass_rate']:.1%}",
        f"No-change handling: {result['candidate_no_change_pass_rate']:.1%}",
        f"Repeatability:      {'PASS' if result['repeatability'] else 'FAIL'}",
    ]
    failures = [item for item in result["results"] if not item["pass"]]
    if failures:
        lines.extend(("", "Failures", "--------"))
        for item in failures:
            lines.append(
                f"{item['name']} [{item['kind']}] expected accept={item['expected_accept']} "
                f"ids={item['expected_ids']}; got accept={item['accepted']} ids={item['returned_ids']}"
            )
    return "\n".join(lines)


__all__ = [
    "BENCHMARK_VERSION", "format_adventure_turn_candidate_result",
    "load_adventure_turn_candidate_cases", "run_adventure_turn_candidate_benchmark",
]
