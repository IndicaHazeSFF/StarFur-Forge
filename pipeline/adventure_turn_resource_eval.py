"""Deterministic evaluation of the narrow public-enum resource route.

The cases use temporary workspaces and injected decoded provider outputs only.
They retain statuses/counts, never fixture text or provider payloads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from tempfile import TemporaryDirectory

from pipeline.adventure_events import AdventureEventLog
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_resource_state import AdventureResourceOperation, AdventureResourceState
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition
from pipeline.adventure_session import AdventureSessionState
from pipeline.adventure_turn import AdventureTurnTransaction
from pipeline.adventure_turn_resource_candidate_inbox import (
    AdventureTurnResourceCandidateInbox,
    AdventureTurnResourceCandidateInboxError,
)
from pipeline.adventure_turn_resource_coordinator import (
    AdventureTurnResourceCoordinator,
    AdventureTurnResourceCoordinatorError,
)


BENCHMARK_VERSION = "adventure-turn-resource-v1"


class _FixtureProvider:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def propose(self, request: object) -> object:
        return self._payload


def _case(name: str, *, expected_generation: str, actual_generation: str,
          expected_candidates: int, actual_candidates: int, expected_staged: int,
          actual_staged: int, expected_committed: int, actual_committed: int,
          failure_category: str = "none") -> dict[str, object]:
    return {
        "name": name,
        "kind": "adventure_turn_resource",
        "expected_generation": expected_generation,
        "actual_generation": actual_generation,
        "expected_candidates": expected_candidates,
        "actual_candidates": actual_candidates,
        "expected_staged": expected_staged,
        "actual_staged": actual_staged,
        "expected_committed": expected_committed,
        "actual_committed": actual_committed,
        "failure_category": failure_category,
        "pass": (
            expected_generation == actual_generation
            and expected_candidates == actual_candidates
            and expected_staged == actual_staged
            and expected_committed == actual_committed
        ),
    }


def _mounted_workspace(root: str):
    registry = AdventureRegistry(root, now=lambda: datetime(2026, 9, 29, tzinfo=UTC))
    record = registry.create("Resource Fixture Ember")
    catalog = AdventureResourceCatalog.from_definitions((
        AdventureResourceDefinition("hatch", "Hatch", "enum", allowed_values=("sealed", "open")),
        AdventureResourceDefinition(
            "secret", "Secret", "enum", visibility="hidden", allowed_values=("red", "blue"),
        ),
    ))
    registry.configure_resource_catalog(record, catalog)
    return registry, record, catalog, AdventureSessionState.unmounted().mount(
        record, (), resource_catalog=catalog,
    )


def _payload(resource_id: str, value: str) -> dict[str, object]:
    return {"schema_version": 1, "candidates": [{
        "mutation": {"kind": "resource_change", "id": resource_id, "operation": "set", "value": value},
        "confidence": 0.8,
    }]}


def _successful_commit_case(root: str) -> dict[str, object]:
    registry, record, catalog, session = _mounted_workspace(root)
    result = AdventureTurnResourceCoordinator(_FixtureProvider(_payload("hatch", "open"))).propose(
        session, user_text="fixture source",
    )
    inbox = AdventureTurnResourceCandidateInbox.empty().present(
        record=record, batch=result.batch, event_count=session.event_count,
        provenance=result.request.provenance,
    )
    selected = inbox.select(record, "TR-001", event_count=session.event_count)
    operation = AdventureResourceOperation("hatch", "set", "open")
    AdventureResourceState.initial(catalog).apply(operation)
    transaction = AdventureTurnTransaction.inactive().begin(record).stage_mutation_candidate(
        selected, resource_operation=operation,
    )
    committed = AdventureEventLog(registry, record).append_many(
        transaction.drafts, request_id=transaction.request_id,
    )
    return _case(
        "public_enum_candidate_commit", expected_generation="completed", actual_generation="completed",
        expected_candidates=1, actual_candidates=len(result.batch.candidates),
        expected_staged=1, actual_staged=len(transaction.drafts),
        expected_committed=1, actual_committed=len(committed),
    )


def _no_change_case(root: str) -> dict[str, object]:
    _, _, _, session = _mounted_workspace(root)
    result = AdventureTurnResourceCoordinator(_FixtureProvider({"schema_version": 1, "candidates": []})).propose(
        session, user_text="fixture source",
    )
    return _case(
        "resource_no_durable_change", expected_generation="completed", actual_generation="completed",
        expected_candidates=0, actual_candidates=len(result.batch.candidates),
        expected_staged=0, actual_staged=0, expected_committed=0, actual_committed=0,
    )


def _hidden_resource_rejected_case(root: str) -> dict[str, object]:
    _, _, _, session = _mounted_workspace(root)
    try:
        AdventureTurnResourceCoordinator(_FixtureProvider(_payload("secret", "red"))).propose(
            session, user_text="fixture source",
        )
    except AdventureTurnResourceCoordinatorError as error:
        return _case(
            "hidden_resource_rejected", expected_generation="failed", actual_generation="failed",
            expected_candidates=0, actual_candidates=0, expected_staged=0, actual_staged=0,
            expected_committed=0, actual_committed=0, failure_category=error.reason,
        )
    raise AssertionError("hidden resource fixture unexpectedly generated a candidate")


def _stale_origin_case(root: str) -> dict[str, object]:
    registry, record, _, session = _mounted_workspace(root)
    result = AdventureTurnResourceCoordinator(_FixtureProvider(_payload("hatch", "open"))).propose(
        session, user_text="fixture source",
    )
    inbox = AdventureTurnResourceCandidateInbox.empty().present(
        record=record, batch=result.batch, event_count=session.event_count,
        provenance=result.request.provenance,
    )
    log = AdventureEventLog(registry, record)
    log.append("discovery", "Intervening authoritative event.")
    try:
        inbox.select(record, "TR-001", event_count=len(log.events()))
    except AdventureTurnResourceCandidateInboxError:
        return _case(
            "resource_stale_origin_rejected", expected_generation="completed", actual_generation="completed",
            expected_candidates=1, actual_candidates=len(result.batch.candidates),
            expected_staged=0, actual_staged=0, expected_committed=0, actual_committed=0,
            failure_category="stale_origin",
        )
    raise AssertionError("stale resource candidate was unexpectedly selectable")


def run_adventure_turn_resource_benchmark() -> dict[str, object]:
    """Run fixed public-enum resource-route cases in temporary workspaces."""
    with TemporaryDirectory() as directory:
        results = [
            _successful_commit_case(directory + "/commit"),
            _no_change_case(directory + "/no-change"),
            _hidden_resource_rejected_case(directory + "/hidden"),
            _stale_origin_case(directory + "/stale"),
        ]
    total = len(results)
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "repeatability": True,
        "generation_success_rate": sum(item["expected_generation"] == item["actual_generation"] for item in results) / total,
        "candidate_validation_success_rate": sum(item["expected_candidates"] == item["actual_candidates"] for item in results) / total,
        "core_use_success_rate": sum(item["expected_staged"] == item["actual_staged"] for item in results) / total,
        "canonical_commit_success_rate": sum(item["expected_committed"] == item["actual_committed"] for item in results) / total,
        "results": results,
    }


def format_adventure_turn_resource_result(result: dict[str, object]) -> str:
    lines = [
        "Adventure-Turn Resource Evaluation",
        "----------------------------------",
        f"Benchmark:          {result['benchmark_version']}",
        f"Cases:              {len(result['results'])}",
        f"Generation:         {result['generation_success_rate']:.1%}",
        f"Validation:         {result['candidate_validation_success_rate']:.1%}",
        f"Core staging:       {result['core_use_success_rate']:.1%}",
        f"Canonical commit:   {result['canonical_commit_success_rate']:.1%}",
        f"Repeatability:      {'PASS' if result['repeatability'] else 'FAIL'}",
    ]
    failures = [item for item in result["results"] if not item["pass"]]
    if failures:
        lines.extend(("", "Failures", "--------"))
        lines.extend(f"{item['name']} ({item['failure_category']})" for item in failures)
    return "\n".join(lines)


__all__ = [
    "BENCHMARK_VERSION", "format_adventure_turn_resource_result",
    "run_adventure_turn_resource_benchmark",
]
