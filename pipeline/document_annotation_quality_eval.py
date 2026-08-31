"""Deterministic, privacy-bounded scoring for reviewed annotation candidates.

This module scores a supplied normal API annotation payload against a checked-in
benchmark contract. It never invokes a provider, opens source documents, writes
reviews/memories, or puts candidate text into the result.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


DOCUMENT_ANNOTATION_QUALITY_BENCHMARK_VERSION = "document-annotation-quality-v1"
DEFAULT_QUALITY_CASES_PATH = Path("tests/fixtures/document_annotation_quality_cases.json")
_MAX_TARGETS = 32
_MAX_TERMS = 8


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def _validate_case(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("annotation quality case must be an object")
    name = value.get("name")
    targets = value.get("targets")
    if not isinstance(name, str) or not name.strip() or not isinstance(targets, list) or not targets or len(targets) > _MAX_TARGETS:
        raise ValueError("annotation quality case is invalid")
    cleaned_targets: list[dict[str, object]] = []
    target_ids: set[str] = set()
    for target in targets:
        if not isinstance(target, Mapping):
            raise ValueError("annotation quality target is invalid")
        target_id, memory_type, terms = target.get("id"), target.get("memory_type"), target.get("required_terms")
        if (
            not isinstance(target_id, str) or not target_id.strip() or target_id in target_ids
            or not isinstance(memory_type, str) or not memory_type.strip()
            or not isinstance(terms, list) or not terms or len(terms) > _MAX_TERMS
            or not all(isinstance(term, str) and term.strip() and len(term) <= 64 for term in terms)
        ):
            raise ValueError("annotation quality target is invalid")
        target_ids.add(target_id)
        cleaned_targets.append({
            "id": target_id, "memory_type": memory_type.strip(),
            "required_terms": tuple(_normalized_text(term) for term in terms),
        })
    return {"name": name.strip(), "targets": tuple(cleaned_targets)}


def load_document_annotation_quality_cases(path: str | Path = DEFAULT_QUALITY_CASES_PATH) -> tuple[dict[str, object], ...]:
    """Load only checked-in, explicit quality contracts."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("annotation quality fixture is unreadable") from error
    if not isinstance(raw, list) or not raw:
        raise ValueError("annotation quality fixture must contain cases")
    cases = tuple(_validate_case(value) for value in raw)
    if len({case["name"] for case in cases}) != len(cases):
        raise ValueError("annotation quality case names must be unique")
    return cases


def select_document_annotation_quality_case(
    name: str, cases: Sequence[Mapping[str, object]],
) -> Mapping[str, object]:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("annotation quality case name is invalid")
    exact = [case for case in cases if case.get("name") == name.strip()]
    if len(exact) != 1:
        raise ValueError("annotation quality case was not found")
    return exact[0]


def _proposal_from_public_candidate(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("annotation candidate is invalid")
    proposal = value.get("proposal", value)
    if not isinstance(proposal, Mapping):
        raise ValueError("annotation candidate proposal is invalid")
    memory_type, subject, summary, details = (
        proposal.get("memory_type"), proposal.get("subject"),
        proposal.get("summary"), proposal.get("details"),
    )
    if not isinstance(memory_type, str) or not isinstance(subject, str) or not isinstance(summary, str):
        raise ValueError("annotation candidate proposal is incomplete")
    if details is not None and not isinstance(details, str):
        raise ValueError("annotation candidate details are invalid")
    return {"memory_type": memory_type, "text": _normalized_text(f"{subject} {summary} {details or ''}")}


def evaluate_document_annotation_quality(
    payload: Mapping[str, object], case: Mapping[str, object],
) -> dict[str, object]:
    """Score one public annotation payload without retaining its candidate text."""
    if not isinstance(payload, Mapping) or not isinstance(case, Mapping):
        raise TypeError("payload and case must be mappings")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > _MAX_TARGETS:
        raise ValueError("annotation payload candidates are invalid")
    targets = case.get("targets")
    name = case.get("name")
    if not isinstance(name, str) or not isinstance(targets, Sequence):
        raise ValueError("annotation quality case is invalid")
    proposals = tuple(_proposal_from_public_candidate(candidate) for candidate in candidates)
    matched_targets: set[int] = set()
    matched_candidates: set[int] = set()
    for target_index, target in enumerate(targets):
        if not isinstance(target, Mapping):
            raise ValueError("annotation quality target is invalid")
        for candidate_index, proposal in enumerate(proposals):
            if candidate_index in matched_candidates:
                continue
            if proposal["memory_type"] != target["memory_type"]:
                continue
            if all(term in proposal["text"] for term in target["required_terms"]):
                matched_targets.add(target_index)
                matched_candidates.add(candidate_index)
                break
    expected_count = len(targets)
    matched_count = len(matched_targets)
    candidate_count = len(proposals)
    false_positive_count = candidate_count - matched_count
    missed_target_count = expected_count - matched_count
    recall = matched_count / expected_count
    precision = matched_count / candidate_count if candidate_count else 1.0
    return {
        "benchmark_version": DOCUMENT_ANNOTATION_QUALITY_BENCHMARK_VERSION,
        "annotation_quality_recall": recall,
        "annotation_quality_precision": precision,
        "annotation_false_positive_count": false_positive_count,
        "annotation_missed_target_count": missed_target_count,
        "results": [{
            "name": name, "kind": "document_annotation_quality",
            "expected_target_count": expected_count,
            "matched_target_count": matched_count,
            "candidate_count": candidate_count,
            "false_positive_count": false_positive_count,
            "missed_target_count": missed_target_count,
            "pass": missed_target_count == 0 and false_positive_count == 0,
        }],
    }


def format_document_annotation_quality_result(result: Mapping[str, object]) -> str:
    """Render bounded quality metrics with no candidate wording."""
    case = result["results"][0]
    assert isinstance(case, Mapping)
    return "\n".join((
        "Document Annotation Quality",
        "---------------------------",
        f"Benchmark:          {result['benchmark_version']}",
        f"Case:               {case['name']}",
        f"Recall:             {float(result['annotation_quality_recall']):.1%}",
        f"Precision:          {float(result['annotation_quality_precision']):.1%}",
        f"False positives:    {case['false_positive_count']}",
        f"Missed targets:     {case['missed_target_count']}",
        f"Outcome:            {'PASS' if case['pass'] else 'FAIL'}",
    ))


def summarize_document_annotation_quality_records(records: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    """Aggregate quality outcomes by model without retaining candidate text."""
    grouped: dict[str, dict[str, object]] = {}
    observations = 0
    for record in records:
        if record.get("benchmark_version") != DOCUMENT_ANNOTATION_QUALITY_BENCHMARK_VERSION:
            continue
        manifest = record.get("manifest")
        outcome = record.get("outcome")
        if not isinstance(manifest, Mapping) or not isinstance(outcome, Mapping):
            raise ValueError("annotation quality ledger record is incomplete")
        profile = manifest.get("model_profile")
        if not isinstance(profile, Mapping) or not isinstance(profile.get("model"), str):
            raise ValueError("annotation quality ledger record is missing its model")
        if outcome.get("status") not in {"passed", "failed"}:
            raise ValueError("annotation quality ledger record has an invalid outcome")
        for case in record.get("cases", []):
            if not isinstance(case, Mapping) or case.get("kind") != "document_annotation_quality":
                continue
            counts = tuple(case.get(field) for field in (
                "expected_target_count", "matched_target_count", "candidate_count",
                "false_positive_count", "missed_target_count",
            ))
            if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in counts):
                raise ValueError("annotation quality ledger record has invalid count data")
            primary_model = profile["model"]
            bucket = grouped.setdefault(primary_model, {
                "primary_model": primary_model, "runs": 0, "passed": 0, "failed": 0,
                "expected_targets": 0, "matched_targets": 0, "candidates": 0,
                "false_positives": 0, "missed_targets": 0, "latencies_ms": [],
            })
            bucket["runs"] += 1
            bucket["passed" if outcome["status"] == "passed" else "failed"] += 1
            bucket["expected_targets"] += counts[0]
            bucket["matched_targets"] += counts[1]
            bucket["candidates"] += counts[2]
            bucket["false_positives"] += counts[3]
            bucket["missed_targets"] += counts[4]
            metrics = record.get("metrics")
            if isinstance(metrics, Mapping) and isinstance(metrics.get("latency_ms"), (int, float)):
                bucket["latencies_ms"].append(float(metrics["latency_ms"]))
            observations += 1
    models: list[dict[str, object]] = []
    for primary_model in sorted(grouped):
        bucket = grouped[primary_model]
        latencies = bucket.pop("latencies_ms")
        models.append({
            **bucket,
            "recall": bucket["matched_targets"] / bucket["expected_targets"],
            "precision": (bucket["matched_targets"] / bucket["candidates"]) if bucket["candidates"] else None,
            "mean_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
        })
    return {"benchmark_version": DOCUMENT_ANNOTATION_QUALITY_BENCHMARK_VERSION,
            "observations": observations, "models": models}


def format_document_annotation_quality_summary(summary: Mapping[str, object]) -> str:
    """Render a model comparison that cannot reveal saved candidate content."""
    lines = ["Document Annotation Quality Summary", "-----------------------------------"]
    lines.append(f"Observations:       {summary.get('observations', 0)}")
    models = summary.get("models", [])
    if not models:
        lines.append("(No document-annotation quality observations recorded.)")
        return "\n".join(lines)
    for model in models:
        assert isinstance(model, Mapping)
        precision = model["precision"]
        latency = model["mean_latency_ms"]
        lines.extend((
            "",
            str(model["primary_model"]),
            f"  runs: {model['runs']}; quality pass rate: {model['passed'] / model['runs']:.1%}",
            f"  recall: {model['recall']:.1%}; precision: {precision:.1%}" if precision is not None else f"  recall: {model['recall']:.1%}; precision: (no candidates)",
            f"  targets: {model['matched_targets']}/{model['expected_targets']}; false positives: {model['false_positives']}; missed targets: {model['missed_targets']}",
            f"  mean latency: {latency:.2f} ms" if latency is not None else "  mean latency: (not recorded)",
        ))
    return "\n".join(lines)


__all__ = [
    "DEFAULT_QUALITY_CASES_PATH",
    "DOCUMENT_ANNOTATION_QUALITY_BENCHMARK_VERSION",
    "evaluate_document_annotation_quality",
    "format_document_annotation_quality_result",
    "format_document_annotation_quality_summary",
    "load_document_annotation_quality_cases",
    "select_document_annotation_quality_case",
    "summarize_document_annotation_quality_records",
]
