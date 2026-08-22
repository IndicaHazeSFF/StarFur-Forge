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
from pipeline.adventure_resources import AdventureResourceCatalog
from pipeline.adventure_resource_state import (
    AdventureResourceStateError,
    derive_adventure_resource_facts,
    select_adventure_resource_context,
)
from pipeline.adventure_state import derive_adventure_state, select_adventure_state_context


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
BENCHMARK_VERSION = "adventure-integrity-v3"
_EVENT_FIELDS = {
    "event_type", "summary", "details", "state_key", "state_value",
    "relationship_subject", "relationship_dimension", "relationship_value",
    "knowledge_subject", "knowledge_status", "knowledge_fact",
    "resource_id", "resource_operation", "resource_value",
}
_EXPECTATION_FIELDS = {
    "state", "relationships", "knowledge", "resources", "resource_context",
    "resource_error", "replay_event_ids", "context_counts",
}
_OPTIONAL_EXPECTATION_FIELDS = {"branch"}
_CASE_FIELDS = {"name", "events", "expect", "resource_catalog", "branch_prefix_event_count"}


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
        if not isinstance(case, dict) or set(case) - _CASE_FIELDS:
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
        branch_prefix_event_count = case.get("branch_prefix_event_count")
        if branch_prefix_event_count is not None and (
            not isinstance(branch_prefix_event_count, int)
            or isinstance(branch_prefix_event_count, bool)
            or not 1 <= branch_prefix_event_count < len(case["events"])
        ):
            raise ValueError("Adventure benchmark branch prefix count is invalid")
        if "resource_catalog" in case:
            try:
                AdventureResourceCatalog.from_dict(case["resource_catalog"])
            except (TypeError, ValueError) as error:
                raise ValueError("Adventure benchmark resource catalog is invalid") from error
        expectation = case["expect"]
        if not isinstance(expectation, dict) or set(expectation) - (_EXPECTATION_FIELDS | _OPTIONAL_EXPECTATION_FIELDS):
            raise ValueError("Adventure benchmark expectation schema is invalid")
        for field in ("state", "relationships", "knowledge", "resources", "resource_context", "replay_event_ids"):
            if field not in expectation or not isinstance(expectation[field], list):
                raise ValueError(f"Adventure benchmark expectation requires {field}")
        if "resource_error" not in expectation or not isinstance(expectation["resource_error"], (str, type(None))):
            raise ValueError("Adventure benchmark expectation requires resource_error")
        if "context_counts" not in expectation or not isinstance(expectation["context_counts"], dict):
            raise ValueError("Adventure benchmark expectation requires context_counts")
        branch_expectation = expectation.get("branch")
        if branch_prefix_event_count is not None:
            if not isinstance(branch_expectation, dict):
                raise ValueError("Adventure benchmark branch expectation is invalid")
            if set(branch_expectation) != _EXPECTATION_FIELDS:
                raise ValueError("Adventure benchmark branch expectation schema is invalid")
        elif branch_expectation is not None:
            raise ValueError("Adventure benchmark branch expectation is invalid")
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


def _resource_payload(facts):
    return [
        {
            "resource_id": fact.resource_id,
            "label": fact.label,
            "kind": fact.kind,
            "value": fact.value,
            "visibility": fact.visibility,
            "source_event_id": fact.source_event_id,
        }
        for fact in facts
    ]


def _projection_actual(events, catalog):
    state = derive_adventure_state(events)
    relationships = derive_adventure_relationships(events)
    knowledge = derive_adventure_knowledge(events)
    # Resource values reach a separate public/hidden projection. Never put a
    # resource event's free-form summary into replay/prompt benchmark context.
    replay = select_replay_spine(
        tuple(event for event in events if event.event_type != "resource_change"),
        limit=min(8, len(events)),
    )
    resource_error = None
    try:
        resources = derive_adventure_resource_facts(catalog, events)
        resource_context = select_adventure_resource_context(resources)
    except AdventureResourceStateError as error:
        resources = ()
        resource_context = ()
        resource_error = str(error)
    return {
        "state": _state_payload(state),
        "relationships": _relationship_payload(relationships),
        "knowledge": _knowledge_payload(knowledge),
        "resources": _resource_payload(resources),
        "resource_context": _resource_payload(resource_context),
        "resource_error": resource_error,
        "replay_event_ids": [event.event_id for event in replay],
        "context_counts": {
            "state": len(select_adventure_state_context(state)),
            "relationships": len(select_adventure_relationship_context(relationships)),
            "knowledge": len(select_adventure_knowledge_context(knowledge)),
            "resources": len(resources),
            "resource_context": len(resource_context),
        },
    }
    

def _evaluate_case(case):
    events = _events_from_case(case)
    catalog = AdventureResourceCatalog.from_dict(case["resource_catalog"]) if "resource_catalog" in case else AdventureResourceCatalog(())
    actual = _projection_actual(events, catalog)
    checks = {
        field: actual[field] == case["expect"][field]
        for field in _EXPECTATION_FIELDS
    }
    branch_prefix_event_count = case.get("branch_prefix_event_count")
    if branch_prefix_event_count is not None:
        branch_actual = _projection_actual(events[:branch_prefix_event_count], catalog)
        checks["branch"] = branch_actual == case["expect"]["branch"]
    return {
        "name": case["name"],
        "pass": all(checks.values()),
        "checks": checks,
        "actual_counts": {
            "events": len(events),
            "state": len(derive_adventure_state(events)),
            "relationships": len(derive_adventure_relationships(events)),
            "knowledge": len(derive_adventure_knowledge(events)),
            "resources": len(actual["resources"]),
            "replay": len(actual["replay_event_ids"]),
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
        f"Projections/replay/resources:  {'PASS' if result['passed'] else 'FAIL'}",
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
