"""Privacy-bounded, append-only records for reproducible benchmark results."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from pipeline.benchmark import BenchmarkRunManifest


EXPERIMENT_LEDGER_SCHEMA_VERSION = "starfur-experiment-ledger-v1"
_MAX_CASES = 500
_MAX_TEXT_LENGTH = 512
_RECORD_FIELDS = {
    "schema_version", "record_id", "recorded_at", "run_id", "benchmark_version",
    "manifest", "outcome", "metrics", "cases", "raw_content_included",
}
_METRIC_FIELDS = {
    "top1_hit_rate", "top3_hit_rate", "recall_at_k", "precision_at_k",
    "irrelevant_result_count", "latency_ms", "time_to_first_token_ms", "repeatability",
    "candidate_acceptance_rate", "candidate_schema_pass_rate",
    "candidate_ordinary_schema_pass_rate", "candidate_typed_schema_pass_rate",
    "candidate_no_change_pass_rate",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT_LENGTH:
        raise ValueError(f"{field} must be non-empty text no longer than {_MAX_TEXT_LENGTH} characters")
    return value.strip()


def _number(value: Any, field: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    return value


def _sanitize_retrieval_case_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only bounded evaluation identifiers and measurements, never query text."""
    if not isinstance(value, Mapping):
        raise ValueError("case result must be an object")
    name = _bounded_text(value.get("name"), "case name", required=True)
    expected = value.get("expected")
    returned = value.get("returned")
    if not isinstance(expected, list) or not isinstance(returned, list):
        raise ValueError("case expected and returned values must be lists")
    if len(expected) > 100 or len(returned) > 100:
        raise ValueError("case result contains too many memory identifiers")
    if not all(isinstance(item, int) and not isinstance(item, bool) for item in expected + returned):
        raise ValueError("case memory identifiers must be integers")
    passed = value.get("pass")
    if not isinstance(passed, bool):
        raise ValueError("case pass must be boolean")

    sanitized = {"name": name, "expected": expected, "returned": returned, "pass": passed}
    retrieval = value.get("retrieval")
    if retrieval is not None:
        if not isinstance(retrieval, list) or len(retrieval) > 100:
            raise ValueError("case retrieval must be a bounded list")
        sanitized["retrieval"] = []
        for item in retrieval:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), int):
                raise ValueError("retrieval entries require an integer id")
            entry = {"id": item["id"]}
            if "score" in item:
                entry["score"] = _number(item["score"], "retrieval score")
            if "reasons" in item:
                if not isinstance(item["reasons"], list) or not all(isinstance(reason, str) and len(reason) <= _MAX_TEXT_LENGTH for reason in item["reasons"]):
                    raise ValueError("retrieval reasons must be bounded text")
                entry["reasons"] = list(item["reasons"])
            sanitized["retrieval"].append(entry)
    return sanitized


def _sanitize_candidate_case_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only candidate-schema outcomes; never retain model text or payloads."""
    name = _bounded_text(value.get("name"), "case name", required=True)
    kind = _bounded_text(value.get("kind"), "candidate case kind", required=True)
    if kind not in {"ordinary", "typed"}:
        raise ValueError("candidate case kind is unsupported")
    expected_accept = value.get("expected_accept")
    accepted = value.get("accepted")
    passed = value.get("pass")
    expected_ids = value.get("expected_ids")
    returned_ids = value.get("returned_ids")
    if not all(isinstance(item, bool) for item in (expected_accept, accepted, passed)):
        raise ValueError("candidate case acceptance and pass must be boolean")
    if not isinstance(expected_ids, list) or not isinstance(returned_ids, list):
        raise ValueError("candidate case identifiers must be lists")
    if len(expected_ids) > 16 or len(returned_ids) > 16:
        raise ValueError("candidate case contains too many identifiers")
    prefix = "TC-" if kind == "ordinary" else "TM-"
    if not all(isinstance(item, str) and item.startswith(prefix) and len(item) <= 16 for item in expected_ids + returned_ids):
        raise ValueError("candidate identifiers are invalid")
    return {
        "name": name, "kind": kind, "expected_accept": expected_accept,
        "accepted": accepted, "expected_ids": list(expected_ids),
        "returned_ids": list(returned_ids), "pass": passed,
    }


def _sanitize_case_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Select one closed, privacy-bounded result schema by case shape."""
    if not isinstance(value, Mapping):
        raise ValueError("case result must be an object")
    if {"expected", "returned"}.issubset(value):
        return _sanitize_retrieval_case_result(value)
    if {"kind", "expected_accept", "accepted", "expected_ids", "returned_ids"}.issubset(value):
        return _sanitize_candidate_case_result(value)
    raise ValueError("case result schema is unsupported")


def build_benchmark_result_record(
    manifest: BenchmarkRunManifest,
    result: Mapping[str, Any],
    *,
    run_id: str | None = None,
    failure_category: str | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Create one durable, raw-content-free benchmark result record."""
    if not isinstance(manifest, BenchmarkRunManifest):
        raise TypeError("manifest must be a BenchmarkRunManifest")
    if not isinstance(result, Mapping):
        raise TypeError("result must be a mapping")
    benchmark_version = _bounded_text(result.get("benchmark_version"), "benchmark_version", required=True)
    cases = result.get("results")
    if not isinstance(cases, list) or not cases or len(cases) > _MAX_CASES:
        raise ValueError("result must contain between 1 and 500 case results")
    case_results = [_sanitize_case_result(case) for case in cases]
    passed = all(case["pass"] for case in case_results) and bool(result.get("repeatability", True))
    metrics: dict[str, Any] = {}
    for field in (
        "top1_hit_rate", "top3_hit_rate", "recall_at_k", "precision_at_k",
        "irrelevant_result_count", "latency_ms", "time_to_first_token_ms",
        "candidate_acceptance_rate", "candidate_schema_pass_rate",
        "candidate_ordinary_schema_pass_rate", "candidate_typed_schema_pass_rate",
        "candidate_no_change_pass_rate",
    ):
        if field in result and result[field] is not None:
            metrics[field] = _number(result[field], field)
    if "repeatability" in result:
        if not isinstance(result["repeatability"], bool):
            raise ValueError("repeatability must be boolean")
        metrics["repeatability"] = result["repeatability"]

    record_run_id = _bounded_text(run_id or manifest.run_id, "run_id") or uuid.uuid4().hex
    category = _bounded_text(failure_category, "failure_category")
    if category is None and not passed:
        category = "benchmark_assertion_failed"
    return {
        "schema_version": EXPERIMENT_LEDGER_SCHEMA_VERSION,
        "record_id": f"ER-{uuid.uuid4().hex}",
        "recorded_at": recorded_at or _utc_now(),
        "run_id": record_run_id,
        "benchmark_version": benchmark_version,
        "manifest": manifest.to_dict(),
        "outcome": {"status": "passed" if passed else "failed", "failure_category": category},
        "metrics": metrics,
        "cases": case_results,
        "raw_content_included": False,
    }


def append_benchmark_result(path: str | Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """Append one validated JSONL record. Callers must opt in to this write."""
    target = Path(path)
    if not target.name:
        raise ValueError("ledger path must name a file")
    if not isinstance(record, Mapping) or record.get("schema_version") != EXPERIMENT_LEDGER_SCHEMA_VERSION:
        raise ValueError("invalid experiment ledger record")
    required = {"record_id", "recorded_at", "run_id", "benchmark_version", "manifest", "outcome", "metrics", "cases", "raw_content_included"}
    if not required.issubset(record):
        raise ValueError("incomplete experiment ledger record")
    if set(record) - _RECORD_FIELDS:
        raise ValueError("experiment ledger records may not contain unrestricted extra fields")
    if record["raw_content_included"] is not False:
        raise ValueError("raw prompts and responses are not permitted in this ledger")
    if not isinstance(record["metrics"], Mapping) or set(record["metrics"]) - _METRIC_FIELDS:
        raise ValueError("ledger metrics must use the bounded metric schema")
    if not isinstance(record["outcome"], Mapping) or set(record["outcome"]) - {"status", "failure_category"}:
        raise ValueError("ledger outcome must use the bounded outcome schema")
    if not isinstance(record["cases"], list):
        raise ValueError("ledger cases must be a list")
    for case in record["cases"]:
        _sanitize_case_result(case)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(record), sort_keys=True, separators=(",", ":")) + "\n"
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return dict(record)


def load_benchmark_results(path: str | Path) -> list[dict[str, Any]]:
    """Read valid JSONL records in append order; absent ledgers are simply empty."""
    target = Path(path)
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid ledger JSON on line {line_number}") from error
        if not isinstance(value, dict) or value.get("schema_version") != EXPERIMENT_LEDGER_SCHEMA_VERSION:
            raise ValueError(f"invalid ledger record on line {line_number}")
        records.append(value)
    return records


def summarize_benchmark_results(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Produce a compact aggregate suitable for later reports without raw content."""
    total = len(records)
    passed = sum(record.get("outcome", {}).get("status") == "passed" for record in records)
    return {
        "records": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else None,
        "benchmark_versions": sorted({str(record.get("benchmark_version")) for record in records}),
    }


__all__ = [
    "EXPERIMENT_LEDGER_SCHEMA_VERSION",
    "append_benchmark_result",
    "build_benchmark_result_record",
    "load_benchmark_results",
    "summarize_benchmark_results",
]
