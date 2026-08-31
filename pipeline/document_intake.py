"""Safe, deterministic preparation of external text documents for StarFur.

This module intentionally prepares content only. It does not call an
annotation model, write SQLite/Chroma, or alter chat prompts. Later API and
application stages own those effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, Iterable, Mapping

from pipeline.document_prechunker import (
    ASSISTANT_NOTE_PROFILE,
    DocumentPrechunkError,
    prechunk_document_text,
    resolve_document_profile,
)
from pipeline.domains import normalize_domain
from pipeline.memory_proposal_validation import validate_memory_proposal


DEFAULT_MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
SUPPORTED_DOCUMENT_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
EXTERNAL_UPLOAD_SOURCE = "external_upload"
DOCUMENT_ANNOTATION_SOURCE = "external_document_annotation"
_DOCUMENT_CANDIDATE_FIELDS = {
    "store", "subject", "memory_type", "summary", "details",
    "importance", "confidence", "retention",
}


class DocumentIntakeError(ValueError):
    """Raised when an external document is not safe to prepare."""


class DocumentAnnotationError(ValueError):
    """Raised when an injected document annotator returns an invalid shape."""


@dataclass(frozen=True)
class IntakeChunk:
    """One deterministic, provenance-carrying prepared document chunk."""

    source_id: str
    source_name: str
    source_kind: str
    domain: str
    profile: str
    chunk_id: str
    scene_index: int
    chunk_index: int
    heading: str | None
    text: str
    frontmatter: Mapping[str, str]


@dataclass(frozen=True)
class PreparedDocument:
    """Validated external text plus chunks ready for later intake stages."""

    source_id: str
    source_name: str
    source_kind: str
    domain: str
    profile: str
    content_hash: str
    byte_count: int
    chunks: tuple[IntakeChunk, ...]


@dataclass(frozen=True)
class DocumentAnnotationFailure:
    """Bounded record of one chunk that remained invalid after retries."""

    chunk_id: str
    scene_index: int
    chunk_index: int
    attempts: int
    reason: str = "invalid_annotation_output"


@dataclass(frozen=True)
class DocumentAnnotationResult:
    """Non-persistent candidates plus bounded per-chunk annotation failures."""

    candidates: tuple["DocumentMemoryCandidate", ...]
    failures: tuple[DocumentAnnotationFailure, ...]
    execution: "DocumentAnnotationExecution | None" = None


@dataclass(frozen=True)
class DocumentAnnotationExecution:
    """Bounded model-attempt accounting for one non-persistent annotation run."""

    primary_model: str
    primary_attempts: int
    fallback_model: str | None = None
    fallback_attempts: int = 0
    elapsed_ms: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.primary_model, str) or not self.primary_model.strip():
            raise ValueError("document annotation primary model is invalid")
        if self.fallback_model is not None and (
            not isinstance(self.fallback_model, str) or not self.fallback_model.strip()
        ):
            raise ValueError("document annotation fallback model is invalid")
        for value in (self.primary_attempts, self.fallback_attempts):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("document annotation attempt count is invalid")
        if self.elapsed_ms is not None and (
            isinstance(self.elapsed_ms, bool)
            or not isinstance(self.elapsed_ms, (int, float))
            or self.elapsed_ms < 0
        ):
            raise ValueError("document annotation elapsed time is invalid")

    @property
    def fallback_used(self) -> bool:
        return self.fallback_attempts > 0

@dataclass(frozen=True)
class DocumentMemoryCandidate:
    """A validated, non-persistent proposal from one document chunk."""

    proposal: Mapping[str, object]
    source_id: str
    source_reference: str
    chunk_id: str
    observation_text: str


def _normalized_candidate_identity_text(value: object) -> str:
    """Return a compact stable representation for candidate identity fields."""
    if value is None:
        return ""
    return " ".join(str(value).split()).casefold()


def document_candidate_identity(
    *,
    document: PreparedDocument,
    chunk: IntakeChunk,
    proposal: Mapping[str, object],
) -> str:
    """Return a content-derived identity for one external-document candidate.

    The extraction model may reorder candidates inside a chunk.  Proposal
    persistence therefore cannot use an extraction ordinal as the source
    reference.  This fingerprint scopes the normalized asserted content to the
    already content-addressed document and chunk while deliberately excluding
    presentation labels and scores that may vary between equivalent
    extractions. ``memory_type`` plus the normalized summary distinguish
    separate facts from one source chunk without treating a changed subject
    label or details wording as a new fact.
    """
    identity_payload = {
        "source_id": document.source_id,
        "chunk_id": chunk.chunk_id,
        "domain": proposal["domain"],
        "memory_type": proposal["memory_type"],
        "summary": _normalized_candidate_identity_text(proposal["summary"]),
    }
    serialized = json.dumps(identity_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _validate_source_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DocumentIntakeError("Document filename must be a non-empty string.")
    source_name = value.strip()
    if "/" in source_name or "\\" in source_name or source_name in {".", ".."}:
        raise DocumentIntakeError("Document filename must not contain a path.")
    if Path(source_name).suffix.casefold() not in SUPPORTED_DOCUMENT_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        raise DocumentIntakeError(f"Unsupported document type; allowed: {allowed}.")
    return source_name


def _validate_document_bytes(data: bytes, *, max_bytes: int) -> str:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer.")
    if len(data) > max_bytes:
        raise DocumentIntakeError(
            f"Document exceeds the {max_bytes}-byte intake limit."
        )
    if b"\x00" in data:
        raise DocumentIntakeError("Document contains NUL bytes and is not plain text.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DocumentIntakeError("Document must be UTF-8 text.") from error


def _prepare_document_bytes(
    data: bytes,
    *,
    source_name: object,
    domain: str | None,
    max_bytes: int,
    max_chars: int | None,
    overlap_paragraphs: int,
    profile: object,
) -> PreparedDocument:
    safe_name = _validate_source_name(source_name)
    text = _validate_document_bytes(data, max_bytes=max_bytes)
    normalized_domain = normalize_domain(domain)
    try:
        selected_profile = resolve_document_profile(profile, text)
        raw_chunks = prechunk_document_text(
            text,
            profile=selected_profile,
            max_chars=max_chars,
            overlap_paragraphs=overlap_paragraphs,
        )
    except DocumentPrechunkError as error:
        raise DocumentIntakeError(str(error)) from error
    content_hash = sha256(data).hexdigest()
    source_id = f"external:{content_hash}"
    chunk_prefix = (
        f"{source_id}:scene"
        if selected_profile == ASSISTANT_NOTE_PROFILE
        else f"{source_id}:profile:{selected_profile}:scene"
    )
    chunks = tuple(
        IntakeChunk(
            source_id=source_id,
            source_name=safe_name,
            source_kind=EXTERNAL_UPLOAD_SOURCE,
            domain=normalized_domain,
            profile=selected_profile,
            chunk_id=f"{chunk_prefix}:{chunk['scene_index']}:chunk:{chunk_index}",
            scene_index=chunk["scene_index"],
            chunk_index=chunk_index,
            heading=chunk.get("heading"),
            text=chunk["text"],
            frontmatter=dict(chunk.get("frontmatter", {})),
        )
        for chunk_index, chunk in enumerate(raw_chunks)
    )
    return PreparedDocument(
        source_id=source_id,
        source_name=safe_name,
        source_kind=EXTERNAL_UPLOAD_SOURCE,
        domain=normalized_domain,
        profile=selected_profile,
        content_hash=content_hash,
        byte_count=len(data),
        chunks=chunks,
    )


def prepare_document(
    path: str | Path,
    *,
    domain: str | None = "personal",
    max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    max_chars: int | None = None,
    overlap_paragraphs: int = 1,
    profile: str = ASSISTANT_NOTE_PROFILE,
) -> PreparedDocument:
    """Validate and chunk one external Markdown/plain-text file."""
    document_path = Path(path)
    if not document_path.is_file():
        raise DocumentIntakeError("Document must be a regular file.")
    return _prepare_document_bytes(
        document_path.read_bytes(),
        source_name=document_path.name,
        domain=domain,
        max_bytes=max_bytes,
        max_chars=max_chars,
        overlap_paragraphs=overlap_paragraphs,
        profile=profile,
    )


def prepare_document_text(
    content: str,
    filename: str,
    *,
    domain: str | None = "personal",
    max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    max_chars: int | None = None,
    overlap_paragraphs: int = 1,
    profile: str = ASSISTANT_NOTE_PROFILE,
) -> PreparedDocument:
    """Prepare extracted external text without writing it to the host filesystem."""
    if not isinstance(content, str):
        raise DocumentIntakeError("Document content must be a UTF-8 text string.")
    return _prepare_document_bytes(
        content.encode("utf-8"),
        source_name=filename,
        domain=domain,
        max_bytes=max_bytes,
        max_chars=max_chars,
        overlap_paragraphs=overlap_paragraphs,
        profile=profile,
    )


def _candidate_records(value: object, chunk_id: str) -> Iterable[Mapping[str, object]]:
    if isinstance(value, Mapping):
        value = value.get("proposals", [])
    if not isinstance(value, list):
        raise DocumentAnnotationError(
            f"Document annotator must return a proposal list for {chunk_id}."
        )
    for candidate in value:
        if not isinstance(candidate, Mapping):
            raise DocumentAnnotationError(
                f"Document proposal must be an object for {chunk_id}."
            )
        unknown = set(candidate) - _DOCUMENT_CANDIDATE_FIELDS
        if unknown:
            raise DocumentAnnotationError(
                f"Document proposal has unknown fields for {chunk_id}: {sorted(unknown)}."
            )
        yield candidate


def _extract_chunk_candidates(
    document: PreparedDocument,
    chunk: IntakeChunk,
    annotator: Callable[[IntakeChunk], object],
    *,
    attempt: int = 1,
) -> tuple[DocumentMemoryCandidate, ...]:
    retryable = getattr(annotator, "annotate_with_retry", None)
    output = retryable(chunk, attempt=attempt) if callable(retryable) else annotator(chunk)
    candidates: list[DocumentMemoryCandidate] = []
    for raw in _candidate_records(output, chunk.chunk_id):
        complete = {**raw, "domain": document.domain, "source": DOCUMENT_ANNOTATION_SOURCE}
        try:
            proposal = validate_memory_proposal(complete, document.domain)
        except ValueError as error:
            raise DocumentAnnotationError(f"Invalid document proposal for {chunk.chunk_id}: {error}") from error
        if proposal["store"]:
            identity = document_candidate_identity(document=document, chunk=chunk, proposal=proposal)
            candidates.append(DocumentMemoryCandidate(
                proposal=proposal, source_id=document.source_id,
                source_reference=f"{chunk.chunk_id}:candidate:{identity}", chunk_id=chunk.chunk_id,
                observation_text=chunk.text,
            ))
    return tuple(candidates)


def extract_document_memory_candidates(
    document: PreparedDocument,
    annotator: Callable[[IntakeChunk], object],
) -> tuple[DocumentMemoryCandidate, ...]:
    """Strict candidate extraction retained for callers needing fail-fast behavior."""
    if not callable(annotator):
        raise TypeError("annotator must be callable.")
    candidates: list[DocumentMemoryCandidate] = []
    for chunk in document.chunks:
        candidates.extend(_extract_chunk_candidates(document, chunk, annotator))
    return tuple(candidates)


def extract_document_memory_candidates_resilient(
    document: PreparedDocument,
    annotator: Callable[[IntakeChunk], object],
    *,
    max_attempts: int = 3,
    progress: Callable[[int, int], None] | None = None,
) -> DocumentAnnotationResult:
    """Retry invalid chunks without allowing one failure to abort a document."""
    if not callable(annotator):
        raise TypeError("annotator must be callable.")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer.")
    candidates: list[DocumentMemoryCandidate] = []
    failures: list[DocumentAnnotationFailure] = []
    total_chunks = len(document.chunks)
    for chunk_number, chunk in enumerate(document.chunks, 1):
        for attempt in range(1, max_attempts + 1):
            try:
                candidates.extend(_extract_chunk_candidates(document, chunk, annotator, attempt=attempt))
                if progress is not None:
                    progress(chunk_number, total_chunks)
                break
            except DocumentAnnotationError:
                if attempt == max_attempts:
                    failures.append(DocumentAnnotationFailure(
                        chunk_id=chunk.chunk_id, scene_index=chunk.scene_index,
                        chunk_index=chunk.chunk_index, attempts=attempt,
                    ))
                    if progress is not None:
                        progress(chunk_number, total_chunks)
    summary = getattr(annotator, "execution_summary", None)
    execution = summary() if callable(summary) else None
    if execution is not None and not isinstance(execution, DocumentAnnotationExecution):
        raise TypeError("document annotator execution summary is invalid")
    return DocumentAnnotationResult(tuple(candidates), tuple(failures), execution)

__all__ = [
    "DEFAULT_MAX_DOCUMENT_BYTES",
    "DOCUMENT_ANNOTATION_SOURCE",
    "EXTERNAL_UPLOAD_SOURCE",
    "SUPPORTED_DOCUMENT_SUFFIXES",
    "DocumentAnnotationError",
    "DocumentAnnotationExecution",
    "DocumentAnnotationFailure",
    "DocumentAnnotationResult",
    "DocumentIntakeError",
    "DocumentMemoryCandidate",
    "document_candidate_identity",
    "IntakeChunk",
    "PreparedDocument",
    "extract_document_memory_candidates",
    "extract_document_memory_candidates_resilient",
    "prepare_document",
    "prepare_document_text",
]
