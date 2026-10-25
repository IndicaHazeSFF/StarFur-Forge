"""Pure bounded persistence codec for validated annotation job results.

Stored output stays untrusted, noncanonical candidate data. Observation text,
source identity, and candidate provenance are rederived from the bound prepared
document, never accepted from a durable result as new authority.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import math

from pipeline.document_intake import (
    DOCUMENT_ANNOTATION_SOURCE, DocumentAnnotationExecution,
    DocumentAnnotationFailure, DocumentAnnotationResult, DocumentMemoryCandidate,
    PreparedDocument, document_candidate_identity,
)
from pipeline.memory_proposal_validation import validate_memory_proposal


RESULT_SCHEMA_VERSION = 1
MAX_RESULT_BYTES = 2 * 1024 * 1024
MAX_RESULT_CANDIDATES = 4096


class AnnotationJobResultError(ValueError):
    """Content-free result/provenance validation failure."""


def _bounded(value: object) -> None:
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise AnnotationJobResultError("annotation result is invalid") from None
    if len(raw) > MAX_RESULT_BYTES:
        raise AnnotationJobResultError("annotation result exceeds capacity")


def _integer(value: object, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _execution(value: object) -> DocumentAnnotationExecution | None:
    if value is None:
        return None
    fields = {"primary_model", "primary_attempts", "fallback_model", "fallback_attempts", "elapsed_ms"}
    if type(value) is not dict or set(value) != fields:
        raise AnnotationJobResultError("annotation execution metadata is invalid")
    for key in ("primary_model", "fallback_model"):
        model = value[key]
        if key == "fallback_model" and model is None:
            continue
        if (not isinstance(model, str) or not model.strip() or len(model) > 128
                or any(ord(character) < 32 for character in model)):
            raise AnnotationJobResultError("annotation execution metadata is invalid")
    if (not _integer(value["primary_attempts"], 1_000_000)
            or not _integer(value["fallback_attempts"], 1_000_000)
            or (value["fallback_attempts"] and value["fallback_model"] is None)):
        raise AnnotationJobResultError("annotation execution metadata is invalid")
    elapsed = value["elapsed_ms"]
    if elapsed is not None and (type(elapsed) not in {int, float}
                                or not 0 <= elapsed <= 86_400_000 or not math.isfinite(elapsed)):
        raise AnnotationJobResultError("annotation execution metadata is invalid")
    return DocumentAnnotationExecution(**value)


def decode_annotation_job_result(document: PreparedDocument, value: object) -> DocumentAnnotationResult:
    """Revalidate one exact source-bound result without I/O or providers."""
    _bounded(value)
    try:
        if type(document) is not PreparedDocument or type(value) is not dict or set(value) != {
            "schema_version", "candidates", "failures", "execution",
        } or type(value["schema_version"]) is not int or value["schema_version"] != RESULT_SCHEMA_VERSION:
            raise ValueError
        raw_candidates, raw_failures = value["candidates"], value["failures"]
        if (type(raw_candidates) is not list or len(raw_candidates) > MAX_RESULT_CANDIDATES
                or type(raw_failures) is not list or len(raw_failures) > len(document.chunks)):
            raise ValueError
        chunks = {chunk.chunk_id: chunk for chunk in document.chunks}
        candidates = []
        identities = set()
        candidate_chunks = set()
        for raw in raw_candidates:
            if type(raw) is not dict or set(raw) != {"chunk_id", "proposal"}:
                raise ValueError
            chunk = chunks[raw["chunk_id"]]
            proposal = validate_memory_proposal(raw["proposal"], document.domain)
            if (proposal["store"] is not True or proposal["domain"] != document.domain
                    or proposal["source"] != DOCUMENT_ANNOTATION_SOURCE):
                raise ValueError
            for field, maximum in (("subject", 128), ("summary", 1000), ("details", 8000)):
                text = proposal[field]
                if text is not None and len(text) > maximum:
                    raise ValueError
            identity = document_candidate_identity(document=document, chunk=chunk, proposal=proposal)
            reference = f"{chunk.chunk_id}:candidate:{identity}"
            if reference in identities:
                raise ValueError
            identities.add(reference)
            candidate_chunks.add(chunk.chunk_id)
            candidates.append(DocumentMemoryCandidate(
                proposal=proposal, source_id=document.source_id, source_reference=reference,
                chunk_id=chunk.chunk_id, observation_text=chunk.text,
            ))
        failures = []
        failed_chunks = set()
        for raw in raw_failures:
            if type(raw) is not dict or set(raw) != {"chunk_id", "scene_index", "chunk_index", "attempts", "reason"}:
                raise ValueError
            chunk = chunks[raw["chunk_id"]]
            if (chunk.chunk_id in failed_chunks or chunk.chunk_id in candidate_chunks
                    or type(raw["scene_index"]) is not int or raw["scene_index"] != chunk.scene_index
                    or type(raw["chunk_index"]) is not int or raw["chunk_index"] != chunk.chunk_index
                    or not _integer(raw["attempts"], 3) or raw["attempts"] < 1
                    or raw["reason"] != "invalid_annotation_output"):
                raise ValueError
            failed_chunks.add(chunk.chunk_id)
            failures.append(DocumentAnnotationFailure(**raw))
        return DocumentAnnotationResult(tuple(candidates), tuple(failures), _execution(value["execution"]))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise AnnotationJobResultError("annotation result failed source validation") from None


def encode_annotation_job_result(document: PreparedDocument, result: DocumentAnnotationResult) -> dict:
    """Detach, validate and serialize candidate/failure data; never trust a type alone."""
    try:
        if type(result) is not DocumentAnnotationResult or type(result.candidates) is not tuple or type(result.failures) is not tuple:
            raise ValueError
        if len(result.candidates) > MAX_RESULT_CANDIDATES or len(result.failures) > len(document.chunks):
            raise ValueError
        if result.execution is not None and type(result.execution) is not DocumentAnnotationExecution:
            raise ValueError
        payload = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "candidates": [{"chunk_id": candidate.chunk_id, "proposal": dict(candidate.proposal)}
                           for candidate in result.candidates if type(candidate) is DocumentMemoryCandidate],
            "failures": [asdict(failure) for failure in result.failures
                         if type(failure) is DocumentAnnotationFailure],
            "execution": asdict(result.execution) if result.execution is not None else None,
        }
        if len(payload["candidates"]) != len(result.candidates) or len(payload["failures"]) != len(result.failures):
            raise ValueError
        normalized = decode_annotation_job_result(document, payload)
        for original, checked in zip(result.candidates, normalized.candidates):
            if (original.source_id != checked.source_id or original.source_reference != checked.source_reference
                    or original.observation_text != checked.observation_text):
                raise ValueError
        # JSON round-trip detaches all mappings, preserving no caller-owned containers.
        return json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise AnnotationJobResultError("annotation result failed source validation") from None


def validate_chunk_checkpoint(document: PreparedDocument, chunk_id: str, payload: object) -> DocumentAnnotationResult:
    """Validate one completed chunk, including a valid empty or failed extraction."""
    result = decode_annotation_job_result(document, payload)
    if (not isinstance(chunk_id, str) or chunk_id not in {chunk.chunk_id for chunk in document.chunks}
            or result.execution is not None
            or any(candidate.chunk_id != chunk_id for candidate in result.candidates)
            or any(failure.chunk_id != chunk_id for failure in result.failures)):
        raise AnnotationJobResultError("annotation checkpoint failed source validation")
    return result
