"""Deterministic, fixture-only evaluation for adventure continuity primitives.

This harness deliberately exercises only Core-owned event/projection/replay
logic. It creates no workspace, calls no provider, and never reads runtime
adventure data. Later benchmark slices can add command, restart, corruption,
and provider-assisted cases without changing this fixture boundary.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_knowledge import derive_adventure_knowledge, select_adventure_knowledge_context
from pipeline.adventure_relationship import derive_adventure_relationships, select_adventure_relationship_context
from pipeline.adventure_replay import select_replay_spine
from pipeline.adventure_state import derive_adventure_state, select_adventure_state_context


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
BENCHMARK_VERSION = "adventure-integrity-v1"
_EVENT_FIELDS = {
    "event_type", "summary", "details", "state_key", "state_value",
    "relationship_subject", "relationship_dimension", "relationship_value",
    "knowledge_subject", "knowledge_status", "knowledge_fact",
}
_EXPECTATION_FIELDS = {
    "state", "relationships", "knowledge", "replay_event_ids", "context_counts",
}


def load_adventure_cases(path=FIXTURE_ROOT / "adventure_integrity_cases.json"):
    """Load bounded declarative cases without opening a workspace or provider."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Adventure benchmark fixture is unreadable") from error
    if not isinstance(value, dict) or set(value) != {"benchmark_version", "cases"}:
        raise ValueError("Adventure benchmark fixture has an invalid top-level schema")
    if value["benchmark_version"] != BENCHMARK_VERSION:
        raise ValueError("Adventure benchmark fixture version is unsupported")
    cases = value["cases"]
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise ValueError("Adventure benchmark fixture must contain 1-100 cases")
    names = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"name", "events", "expect"}:
            raise ValueError("Adventure benchmark case schema is invalid")
        if not isinstance(case["name"], str) or not case["name"].strip() or len(case["name"]) > 128:
            raise ValueError("Adventure benchmark case name is invalid")
        if case["name"] in names:
            raise ValueError("Adventure benchmark case names must be unique")
        names.add(case["name"])
        if not isinstance(case["events"], list) or not case["events"] or len(case["events"]) > 64:
            raise ValueError("Adventure benchmark case events must contain 1-64 entries")
        for event in case["events"]:
            if not isinstance(event, dict) or set(event) - _EVENT_FIELDS:
                raise ValueError("Adventure benchmark event schema is invalid")
            if not isinstance(event.get("event_type"), str) or not isinstance(event.get("summary"), str):
                raise ValueError("Adventure benchmark events require event_type and summary")
        expectation = case["expect"]
        if not isinstance(expectation, dict) or set(expectation) - _EXPECTATION_FIELDS:
            raise ValueError("Adventure benchmark expectation schema is invalid")
        for field in ("state", "relationships", "knowledge", "replay_event_ids"):
            if field not in expectation or not isinstance(expectation[field], list):
                raise ValueError(f"Adventure benchmark expectation requires {field}")
        if "context_counts" not in expectation or not isinstance(expectation["context_counts"], dict):
            raise ValueError("Adventure benchmark expectation requires context_counts")
    return cases


def _events_from_case(case):
    events = []
    for sequence, source in enumerate(case["events"], start=1):
        values = {key: source.get(key) for key in _EVENT_FIELDS}
        events.append(AdventureEvent(
            sequence=sequence,
            event_id=f"AE-{sequence:06d}",
            recorded_at="fixture",
            **values,
        ))
    return tuple(events)


def _state_payload(facts):
    return [
        {"key": fact.key, "value": fact.value, "source_event_id": fact.source_event_id}
        for fact in facts
    ]


def _relationship_payload(facts):
    return [
        {
            "subject": fact.subject,
            "dimension": fact.dimension,
            "value": fact.value,
            "source_event_id": fact.source_event_id,
        }
        for fact in facts
    ]


def _knowledge_payload(facts):
    return [
        {
            "subject": fact.subject,
            "status": fact.status,
            "fact": fact.fact,
            "source_event_id": fact.source_event_id,
        }
        for fact in facts
    ]


def _evaluate_case(case):
    events = _events_from_case(case)
    state = derive_adventure_state(events)
    relationships = derive_adventure_relationships(events)
    knowledge = derive_adventure_knowledge(events)
    replay = select_replay_spine(events, limit=min(8, len(events)))
    actual = {
        "state": _state_payload(state),
        "relationships": _relationship_payload(relationships),
        "knowledge": _knowledge_payload(knowledge),
        "replay_event_ids": [event.event_id for event in replay],
        "context_counts": {
            "state": len(select_adventure_state_context(state)),
            "relationships": len(select_adventure_relationship_context(relationships)),
            "knowledge": len(select_adventure_knowledge_context(knowledge)),
        },
    }
    checks = {field: actual[field] == case["expect"][field] for field in _EXPECTATION_FIELDS}
    return {
        "name": case["name"],
        "pass": all(checks.values()),
        "checks": checks,
        "actual_counts": {
            "events": len(events),
            "state": len(state),
            "relationships": len(relationships),
            "knowledge": len(knowledge),
            "replay": len(replay),
        },
    }


def run_adventure_integrity_benchmark(cases=None):
    """Evaluate projections/replay twice to make determinism measurable."""
    cases = load_adventure_cases() if cases is None else cases
    first = [_evaluate_case(case) for case in cases]
    second = [_evaluate_case(case) for case in cases]
    failures = [result["name"] for result in first if not result["pass"]]
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "cases": len(first),
        "passed": not failures,
        "repeatability": first == second,
        "failures": failures,
        "results": first,
    }


def format_adventure_integrity_result(result):
    """Render a concise CLI report without fixture prose or runtime data."""
    lines = [
        "Adventure Integrity Evaluation",
        "------------------------------",
        f"Benchmark:          {result['benchmark_version']}",
        f"Cases:              {result['cases']}",
        f"Projection/replay:  {'PASS' if result['passed'] else 'FAIL'}",
        f"Repeatability:      {'PASS' if result['repeatability'] else 'FAIL'}",
    ]
    if result["failures"]:
        lines.extend(("", "Failures", "--------"))
        lines.extend(result["failures"])
    return "\n".join(lines)


__all__ = [
    "BENCHMARK_VERSION", "FIXTURE_ROOT", "format_adventure_integrity_result",
    "load_adventure_cases", "run_adventure_integrity_benchmark",
]
