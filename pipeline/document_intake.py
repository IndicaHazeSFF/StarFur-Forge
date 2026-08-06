"""Safe, deterministic preparation of external text documents for StarFur.

This module intentionally prepares content only. It does not call an
annotation model, write SQLite/Chroma, or alter chat prompts. Later API and
application stages own those effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Iterable, Mapping

from pipeline.chunker import chunk_text
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
    content_hash: str
    byte_count: int
    chunks: tuple[IntakeChunk, ...]


@dataclass(frozen=True)
class DocumentMemoryCandidate:
    """A validated, non-persistent proposal from one document chunk."""

    proposal: Mapping[str, object]
    source_id: str
    source_reference: str
    chunk_id: str
    observation_text: str


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
    max_chars: int,
    overlap_paragraphs: int,
) -> PreparedDocument:
    safe_name = _validate_source_name(source_name)
    text = _validate_document_bytes(data, max_bytes=max_bytes)
    normalized_domain = normalize_domain(domain)
    content_hash = sha256(data).hexdigest()
    source_id = f"external:{content_hash}"
    raw_chunks = chunk_text(
        text,
        max_chars=max_chars,
        overlap_paragraphs=overlap_paragraphs,
    )
    chunks = tuple(
        IntakeChunk(
            source_id=source_id,
            source_name=safe_name,
            source_kind=EXTERNAL_UPLOAD_SOURCE,
            domain=normalized_domain,
            chunk_id=f"{source_id}:scene:{chunk['scene_index']}:chunk:{chunk_index}",
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
        content_hash=content_hash,
        byte_count=len(data),
        chunks=chunks,
    )


def prepare_document(
    path: str | Path,
    *,
    domain: str | None = "personal",
    max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    max_chars: int = 1200,
    overlap_paragraphs: int = 1,
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
    )


def prepare_document_text(
    content: str,
    filename: str,
    *,
    domain: str | None = "personal",
    max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
    max_chars: int = 1200,
    overlap_paragraphs: int = 1,
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


def extract_document_memory_candidates(
    document: PreparedDocument,
    annotator: Callable[[IntakeChunk], object],
) -> tuple[DocumentMemoryCandidate, ...]:
    """Validate document candidates without calling a model or storing anything.

    The injected annotator receives one provenance-carrying chunk and may return
    a proposal list or ``{"proposals": [...]}``. Domain and source are supplied
    by this boundary rather than trusted from annotation output.
    """
    if not callable(annotator):
        raise TypeError("annotator must be callable.")
    candidates: list[DocumentMemoryCandidate] = []
    for chunk in document.chunks:
        for raw in _candidate_records(annotator(chunk), chunk.chunk_id):
            complete = {
                **raw,
                "domain": document.domain,
                "source": DOCUMENT_ANNOTATION_SOURCE,
            }
            try:
                proposal = validate_memory_proposal(complete, document.domain)
            except ValueError as error:
                raise DocumentAnnotationError(
                    f"Invalid document proposal for {chunk.chunk_id}: {error}"
                ) from error
            if not proposal["store"]:
                continue
            candidates.append(
                DocumentMemoryCandidate(
                    proposal=proposal,
                    source_id=document.source_id,
                    source_reference=chunk.chunk_id,
                    chunk_id=chunk.chunk_id,
                    observation_text=chunk.text,
                )
            )
    return tuple(candidates)


__all__ = [
    "DEFAULT_MAX_DOCUMENT_BYTES",
    "DOCUMENT_ANNOTATION_SOURCE",
    "EXTERNAL_UPLOAD_SOURCE",
    "SUPPORTED_DOCUMENT_SUFFIXES",
    "DocumentAnnotationError",
    "DocumentIntakeError",
    "DocumentMemoryCandidate",
    "IntakeChunk",
    "PreparedDocument",
    "extract_document_memory_candidates",
    "prepare_document",
    "prepare_document_text",
]