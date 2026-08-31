"""Explicit live-model runner for checked-in, public annotation benchmarks.

The runner is intentionally narrower than document intake: it accepts an
injected provider and public fixture only, does not create a review, and emits
aggregate quality data rather than candidates or document text.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from pipeline.document_annotation import DocumentProposalAnnotator
from pipeline.document_annotation_quality_eval import evaluate_document_annotation_quality
from pipeline.document_intake import extract_document_memory_candidates_resilient, prepare_document
from pipeline.providers import ChatProvider


PUBLIC_QUALITY_FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


@dataclass(frozen=True)
class DocumentAnnotationQualityRun:
    """Raw-content-free result from one explicitly invoked fixture run."""

    result: Mapping[str, object]
    primary_model: str
    primary_attempts: int
    failed_chunk_count: int
    candidate_count: int
    elapsed_ms: float


def run_document_annotation_quality_case(
    fixture_path: str,
    case: Mapping[str, object],
    provider: ChatProvider,
    model: str,
    *,
    max_output_tokens: int = 1024,
) -> DocumentAnnotationQualityRun:
    """Run one public fixture against one explicitly selected model.

    This creates no document review, proposal, memory, semantic entry, or
    runtime source record. It is not the normal document-upload route.
    """
    if not isinstance(model, str) or not model.strip():
        raise ValueError("annotation benchmark model is invalid")
    try:
        resolved_fixture = Path(fixture_path).resolve(strict=True)
        resolved_root = PUBLIC_QUALITY_FIXTURES_ROOT.resolve(strict=True)
        resolved_fixture.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise ValueError("annotation benchmark fixture must be a checked-in public test fixture") from error
    document = prepare_document(resolved_fixture, domain="personal")
    annotator = DocumentProposalAnnotator(provider, model, max_output_tokens=max_output_tokens)
    started_at = perf_counter()
    annotation = extract_document_memory_candidates_resilient(
        document, annotator, max_attempts=3,
    )
    elapsed_ms = (perf_counter() - started_at) * 1000
    public_payload = {
        "candidates": [{"proposal": dict(candidate.proposal)} for candidate in annotation.candidates],
    }
    result = evaluate_document_annotation_quality(public_payload, case)
    result["latency_ms"] = elapsed_ms
    result["annotation_failed_chunk_count"] = len(annotation.failures)
    result["annotation_candidate_count"] = len(annotation.candidates)
    result["annotation_primary_attempt_count"] = annotation.execution.primary_attempts
    if annotation.failures:
        result["results"][0]["pass"] = False
    return DocumentAnnotationQualityRun(
        result=result,
        primary_model=model,
        primary_attempts=annotation.execution.primary_attempts,
        failed_chunk_count=len(annotation.failures),
        candidate_count=len(annotation.candidates),
        elapsed_ms=elapsed_ms,
    )


__all__ = [
    "DocumentAnnotationQualityRun",
    "PUBLIC_QUALITY_FIXTURES_ROOT",
    "run_document_annotation_quality_case",
]
