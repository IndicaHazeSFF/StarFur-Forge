"""Privacy-bounded observations for external-document annotation reliability.

This is deliberately a recorder input, not a provider runner. A caller may
transcribe the bounded counts returned by the normal annotation API after an
explicit live-model run, but document text, review IDs, candidates, and raw
provider output never enter the benchmark result or experiment ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


DOCUMENT_ANNOTATION_BENCHMARK_VERSION = "document-annotation-reliability-v1"


@dataclass(frozen=True)
class DocumentAnnotationObservation:
    """One bounded observation from a completed annotation request."""

    chunk_count: int
    failed_chunk_count: int
    candidate_count: int
    primary_attempt_count: int
    fallback_attempt_count: int = 0
    latency_ms: float | None = None

    def __post_init__(self) -> None:
        for field in (
            "chunk_count", "failed_chunk_count", "candidate_count",
            "primary_attempt_count", "fallback_attempt_count",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        if self.chunk_count <= 0:
            raise ValueError("chunk_count must be positive")
        if self.failed_chunk_count > self.chunk_count:
            raise ValueError("failed_chunk_count cannot exceed chunk_count")
        if self.latency_ms is not None and (
            isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, (int, float))
            or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be a non-negative number")

    @property
    def successful_chunk_count(self) -> int:
        return self.chunk_count - self.failed_chunk_count

    @property
    def fallback_used(self) -> bool:
        return self.fallback_attempt_count > 0


def build_document_annotation_benchmark_result(
    observation: DocumentAnnotationObservation,
    *,
    case_name: str = "external-document-annotation",
    fallback_model: str | None = None,
) -> dict[str, object]:
    """Return one ledger-compatible, raw-content-free reliability result."""
    if not isinstance(observation, DocumentAnnotationObservation):
        raise TypeError("observation must be a DocumentAnnotationObservation")
    if not isinstance(case_name, str) or not case_name.strip() or len(case_name) > 512:
        raise ValueError("case_name must be bounded non-empty text")
    passed = observation.failed_chunk_count == 0
    if fallback_model is not None and (
        not isinstance(fallback_model, str) or not fallback_model.strip() or len(fallback_model) > 512
    ):
        raise ValueError("fallback_model must be bounded non-empty text when supplied")
    case: dict[str, object] = {
        "name": case_name.strip(), "kind": "document_annotation",
        "chunk_count": observation.chunk_count,
        "successful_chunk_count": observation.successful_chunk_count,
        "failed_chunk_count": observation.failed_chunk_count,
        "candidate_count": observation.candidate_count,
        "primary_attempt_count": observation.primary_attempt_count,
        "fallback_attempt_count": observation.fallback_attempt_count,
        "fallback_used": observation.fallback_used,
        "pass": passed,
    }
    if fallback_model is not None:
        case["fallback_model"] = fallback_model.strip()
    result: dict[str, object] = {
        "benchmark_version": DOCUMENT_ANNOTATION_BENCHMARK_VERSION,
        "annotation_success_rate": observation.successful_chunk_count / observation.chunk_count,
        "annotation_failed_chunk_count": observation.failed_chunk_count,
        "annotation_candidate_count": observation.candidate_count,
        "annotation_primary_attempt_count": observation.primary_attempt_count,
        "annotation_fallback_attempt_count": observation.fallback_attempt_count,
        "annotation_fallback_used_count": int(observation.fallback_used),
        "results": [case],
    }
    if observation.latency_ms is not None:
        result["latency_ms"] = observation.latency_ms
    return result


def format_document_annotation_benchmark_result(result: dict[str, object]) -> str:
    """Render a compact local-only confirmation without source details."""
    case = result["results"][0]
    assert isinstance(case, dict)
    lines = [
        "Document Annotation Reliability",
        "-------------------------------",
        f"Benchmark:          {result['benchmark_version']}",
        f"Chunks:             {case['chunk_count']}",
        f"Successful chunks:  {case['successful_chunk_count']}",
        f"Failed chunks:      {case['failed_chunk_count']}",
        f"Candidates:         {case['candidate_count']}",
        f"Primary attempts:   {case['primary_attempt_count']}",
        f"Fallback attempts:  {case['fallback_attempt_count']}",
        f"Fallback used:      {'yes' if case['fallback_used'] else 'no'}",
    ]
    if "latency_ms" in result:
        lines.append(f"Latency:            {float(result['latency_ms']):.2f} ms")
    lines.append(f"Outcome:            {'PASS' if case['pass'] else 'FAIL'}")
    return "\n".join(lines)


def summarize_document_annotation_records(records: list[Mapping[str, Any]]) -> dict[str, object]:
    """Aggregate annotation observations by configured primary model.

    The result is intentionally a report over ledger metadata and counts only.
    It does not re-open documents, inspect candidates, or infer fact quality.
    """
    grouped: dict[str, dict[str, object]] = {}
    observations = 0
    for record in records:
        if record.get("benchmark_version") != DOCUMENT_ANNOTATION_BENCHMARK_VERSION:
            continue
        manifest = record.get("manifest")
        if not isinstance(manifest, Mapping):
            raise ValueError("annotation ledger record is missing a manifest")
        profile = manifest.get("model_profile")
        if not isinstance(profile, Mapping) or not isinstance(profile.get("model"), str):
            raise ValueError("annotation ledger record is missing a primary model")
        primary_model = profile["model"]
        outcome = record.get("outcome")
        if not isinstance(outcome, Mapping) or outcome.get("status") not in {"passed", "failed"}:
            raise ValueError("annotation ledger record has an invalid outcome")
        for case in record.get("cases", []):
            if not isinstance(case, Mapping) or case.get("kind") != "document_annotation":
                continue
            counts = tuple(case.get(field) for field in (
                "chunk_count", "failed_chunk_count", "candidate_count",
                "primary_attempt_count", "fallback_attempt_count",
            ))
            if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in counts):
                raise ValueError("annotation ledger record has invalid count data")
            if not isinstance(case.get("fallback_used"), bool):
                raise ValueError("annotation ledger record has invalid fallback data")
            bucket = grouped.setdefault(primary_model, {
                "primary_model": primary_model, "fallback_models": set(), "runs": 0,
                "passed": 0, "failed": 0, "chunks": 0, "failed_chunks": 0,
                "candidates": 0, "primary_attempts": 0, "fallback_attempts": 0,
                "fallback_used_runs": 0, "latencies_ms": [],
            })
            bucket["runs"] += 1
            bucket["passed" if outcome["status"] == "passed" else "failed"] += 1
            bucket["chunks"] += counts[0]
            bucket["failed_chunks"] += counts[1]
            bucket["candidates"] += counts[2]
            bucket["primary_attempts"] += counts[3]
            bucket["fallback_attempts"] += counts[4]
            bucket["fallback_used_runs"] += int(case["fallback_used"])
            fallback_model = case.get("fallback_model")
            if isinstance(fallback_model, str) and fallback_model.strip():
                bucket["fallback_models"].add(fallback_model.strip())
            metrics = record.get("metrics")
            if isinstance(metrics, Mapping) and isinstance(metrics.get("latency_ms"), (int, float)):
                bucket["latencies_ms"].append(float(metrics["latency_ms"]))
            observations += 1

    models: list[dict[str, object]] = []
    for primary_model in sorted(grouped):
        bucket = grouped[primary_model]
        latencies = bucket.pop("latencies_ms")
        fallback_models = sorted(bucket.pop("fallback_models"))
        models.append({
            **bucket,
            "fallback_models": fallback_models,
            "success_rate": (bucket["passed"] / bucket["runs"]) if bucket["runs"] else None,
            "mean_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
        })
    return {"benchmark_version": DOCUMENT_ANNOTATION_BENCHMARK_VERSION,
            "observations": observations, "models": models}


def format_document_annotation_summary(summary: Mapping[str, object]) -> str:
    """Render one human-readable, raw-content-free ledger comparison."""
    lines = ["Document Annotation Reliability Summary", "-------------------------------------"]
    observations = summary.get("observations", 0)
    lines.append(f"Observations:       {observations}")
    models = summary.get("models", [])
    if not models:
        lines.append("(No document-annotation observations recorded.)")
        return "\n".join(lines)
    for model in models:
        assert isinstance(model, Mapping)
        fallback = ", ".join(model["fallback_models"]) or "(not recorded)"
        success_rate = model["success_rate"]
        latency = model["mean_latency_ms"]
        lines.extend((
            "",
            f"{model['primary_model']}",
            f"  runs: {model['runs']}; pass rate: {success_rate:.1%}",
            f"  chunks: {model['chunks']}; failed chunks: {model['failed_chunks']}; candidates: {model['candidates']}",
            f"  attempts: {model['primary_attempts']} primary; {model['fallback_attempts']} fallback; fallback used in {model['fallback_used_runs']} run(s)",
            f"  configured fallback: {fallback}",
            f"  mean latency: {latency:.2f} ms" if latency is not None else "  mean latency: (not recorded)",
        ))
    return "\n".join(lines)


__all__ = [
    "DOCUMENT_ANNOTATION_BENCHMARK_VERSION",
    "DocumentAnnotationObservation",
    "build_document_annotation_benchmark_result",
    "format_document_annotation_benchmark_result",
    "format_document_annotation_summary",
    "summarize_document_annotation_records",
]
