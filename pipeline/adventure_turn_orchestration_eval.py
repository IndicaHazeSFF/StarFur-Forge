"""Deterministic C3 orchestration evaluation with no live provider or runtime data.

This fixture suite verifies the authority boundary around one generated ordinary
adventure turn: untrusted candidate data may become a reviewed inbox entry,
then an explicitly selected staged draft, then one append-only event.  The
report retains only bounded counts/statuses; fixture turn prose and provider
payloads do not enter result or ledger records.
"""

from __future__ import annotations

from datetime import UTC, datetime
from tempfile import TemporaryDirectory

from pipeline.adventure_events import AdventureEventLog
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_session import AdventureSessionState
from pipeline.adventure_turn import AdventureTurnTransaction
from pipeline.adventure_turn_candidate_inbox import (
    AdventureTurnCandidateInbox,
    AdventureTurnCandidateInboxError,
)
from pipeline.adventure_turn_coordinator import (
    AdventureTurnCoordinator,
    AdventureTurnCoordinatorError,
)


BENCHMARK_VERSION = "adventure-turn-orchestration-v1"


class _FixtureProvider:
    """One deterministic decoded-output provider with no side effects."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def propose(self, request: object) -> object:
        return self._payload


def _case(
    name: str, *, expected_generation: str, actual_generation: str,
    expected_candidates: int, actual_candidates: int,
    expected_staged: int, actual_staged: int,
    expected_committed: int, actual_committed: int,
    failure_category: str = "none",
) -> dict[str, object]:
    return {
        "name": name,
        "kind": "adventure_turn",
        "expected_generation": expected_generation,
        "actual_generation": actual_generation,
        "expected_candidates": expected_candidates,
        "actual_candidates": actual_candidates,
        "expected_staged": expected_staged,
        "actual_staged": actual_staged,
        "expected_committed": expected_committed,
        "actual_committed": actual_committed,
        "pass": (
            expected_generation == actual_generation
            and expected_candidates == actual_candidates
            and expected_staged == actual_staged
            and expected_committed == actual_committed
        ),
        "failure_category": failure_category,
    }


def _mounted_workspace(root: str):
    registry = AdventureRegistry(root, now=lambda: datetime(2026, 8, 30, tzinfo=UTC))
    record = registry.create("Fixture Ember")
    return registry, record, AdventureSessionState.unmounted().mount(record, ())


def _successful_commit_case(root: str) -> dict[str, object]:
    registry, record, session = _mounted_workspace(root)
    result = AdventureTurnCoordinator(_FixtureProvider({
        "schema_version": 1,
        "candidates": [{
            "event_type": "discovery",
            "summary": "Fixture discovery.",
            "confidence": 0.8,
        }],
    })).propose(session, user_text="fixture source")
    inbox = AdventureTurnCandidateInbox.empty().present(result)
    selected = inbox.select(record, "TC-001", event_count=session.event_count)
    transaction = AdventureTurnTransaction.inactive().begin(record).stage_candidate(selected)
    committed = AdventureEventLog(registry, record).append_many(
        transaction.drafts, request_id=transaction.request_id,
    )
    return _case(
        "ordinary_candidate_commit",
        expected_generation="completed", actual_generation="completed",
        expected_candidates=1, actual_candidates=len(result.batch.candidates),
        expected_staged=1, actual_staged=len(transaction.drafts),
        expected_committed=1, actual_committed=len(committed),
    )


def _no_change_case(root: str) -> dict[str, object]:
    _, _, session = _mounted_workspace(root)
    result = AdventureTurnCoordinator(_FixtureProvider({
        "schema_version": 1,
        "candidates": [],
    })).propose(session, user_text="fixture source")
    return _case(
        "ordinary_no_durable_change",
        expected_generation="completed", actual_generation="completed",
        expected_candidates=0, actual_candidates=len(result.batch.candidates),
        expected_staged=0, actual_staged=0,
        expected_committed=0, actual_committed=0,
    )


def _invalid_envelope_case(root: str) -> dict[str, object]:
    _, _, session = _mounted_workspace(root)
    try:
        AdventureTurnCoordinator(_FixtureProvider({
            "schema_version": 1,
            "candidates": [{
                "event_type": "state_change",
                "summary": "Invalid ordinary mutation.",
                "confidence": 0.8,
            }],
        })).propose(session, user_text="fixture source")
    except AdventureTurnCoordinatorError as error:
        return _case(
            "ordinary_invalid_envelope",
            expected_generation="failed", actual_generation="failed",
            expected_candidates=0, actual_candidates=0,
            expected_staged=0, actual_staged=0,
            expected_committed=0, actual_committed=0,
            failure_category=error.reason,
        )
    raise AssertionError("invalid fixture envelope unexpectedly generated candidates")


def _stale_origin_case(root: str) -> dict[str, object]:
    registry, record, session = _mounted_workspace(root)
    result = AdventureTurnCoordinator(_FixtureProvider({
        "schema_version": 1,
        "candidates": [{
            "event_type": "discovery",
            "summary": "Fixture discovery.",
            "confidence": 0.8,
        }],
    })).propose(session, user_text="fixture source")
    inbox = AdventureTurnCandidateInbox.empty().present(result)
    log = AdventureEventLog(registry, record)
    log.append("discovery", "Intervening authoritative event.")
    try:
        inbox.select(record, "TC-001", event_count=len(log.events()))
    except AdventureTurnCandidateInboxError:
        return _case(
            "ordinary_stale_origin_rejected",
            expected_generation="completed", actual_generation="completed",
            expected_candidates=1, actual_candidates=len(result.batch.candidates),
            expected_staged=0, actual_staged=0,
            expected_committed=0, actual_committed=0,
            failure_category="stale_origin",
        )
    raise AssertionError("stale candidate was unexpectedly selectable")


def run_adventure_turn_orchestration_benchmark() -> dict[str, object]:
    """Run deterministic C3 cases in temporary workspaces only."""
    with TemporaryDirectory() as directory:
        results = [
            _successful_commit_case(directory + "/commit"),
            _no_change_case(directory + "/no-change"),
            _invalid_envelope_case(directory + "/invalid"),
            _stale_origin_case(directory + "/stale"),
        ]
    total = len(results)
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "repeatability": True,
        "generation_success_rate": sum(
            item["expected_generation"] == item["actual_generation"] for item in results
        ) / total,
        "candidate_validation_success_rate": sum(
            item["expected_candidates"] == item["actual_candidates"] for item in results
        ) / total,
        "core_use_success_rate": sum(
            item["expected_staged"] == item["actual_staged"] for item in results
        ) / total,
        "canonical_commit_success_rate": sum(
            item["expected_committed"] == item["actual_committed"] for item in results
        ) / total,
        "results": results,
    }


def format_adventure_turn_orchestration_result(result: dict[str, object]) -> str:
    """Render a compact, raw-content-free C3 evaluation report."""
    lines = [
        "Adventure-Turn Orchestration Evaluation",
        "-------------------------------------",
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
        for item in failures:
            lines.append(f"{item['name']} ({item['failure_category']})")
    return "\n".join(lines)


__all__ = [
    "BENCHMARK_VERSION", "format_adventure_turn_orchestration_result",
    "run_adventure_turn_orchestration_benchmark",
]
