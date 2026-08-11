"""Read-only, source-scoped retrieval over one prepared external document.

This is intentionally an ephemeral document-review primitive, not assistant
memory retrieval.  It lets a trusted presentation connector ask for a small,
explainable context packet from the exact source it supplied without adding
raw document text to a user chat message or storing a new SQLite/Chroma index.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from pipeline.document_intake import IntakeChunk, PreparedDocument


DEFAULT_DOCUMENT_CONTEXT_LIMIT = 3
MAX_DOCUMENT_CONTEXT_LIMIT = 8
MAX_DOCUMENT_CONTEXT_QUERY_CHARACTERS = 2_000

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset({
    "a", "about", "an", "and", "are", "be", "does", "do", "for", "from",
    "how", "i", "in", "is", "it", "me", "of", "on", "or", "say", "that",
    "the", "this", "to", "was", "what", "when", "where", "which", "who", "with",
    "you", "your",
})


class DocumentContextError(ValueError):
    """Raised when a source-scoped document-context request is invalid."""


@dataclass(frozen=True)
class DocumentContextChunk:
    """One selected source chunk plus bounded, deterministic diagnostics."""

    chunk: IntakeChunk
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DocumentContextPacket:
    """A bounded, source-scoped packet ready for a trusted context renderer."""

    source_id: str
    source_name: str
    domain: str
    query: str
    chunks: tuple[DocumentContextChunk, ...]


def _meaningful_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in _TOKEN_RE.findall(value.casefold()) if token not in _STOP_WORDS)


def _validate_query(query: object) -> str:
    if not isinstance(query, str):
        raise DocumentContextError("Document context query must be text.")
    normalized = " ".join(query.split())
    if not normalized:
        raise DocumentContextError("Document context query must not be empty.")
    if len(normalized) > MAX_DOCUMENT_CONTEXT_QUERY_CHARACTERS:
        raise DocumentContextError("Document context query exceeds the character limit.")
    if not _meaningful_tokens(normalized):
        raise DocumentContextError("Document context query has no meaningful terms.")
    return normalized


def _validate_limit(limit: object) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise DocumentContextError("Document context limit must be an integer.")
    if not 1 <= limit <= MAX_DOCUMENT_CONTEXT_LIMIT:
        raise DocumentContextError(
            f"Document context limit must be between 1 and {MAX_DOCUMENT_CONTEXT_LIMIT}."
        )
    return limit


def select_document_context(
    document: PreparedDocument,
    query: object,
    *,
    limit: object = DEFAULT_DOCUMENT_CONTEXT_LIMIT,
) -> tuple[DocumentContextChunk, ...]:
    """Return only matching chunks from one prepared source, oldest tie first.

    The deliberately lexical first slice keeps source selection inspectable and
    deterministic.  It does not call models, embeddings, SQLite, or Chroma.
    """
    if not isinstance(document, PreparedDocument):
        raise TypeError("document must be a PreparedDocument.")
    normalized_query = _validate_query(query)
    normalized_limit = _validate_limit(limit)
    query_tokens = set(_meaningful_tokens(normalized_query))
    selected: list[DocumentContextChunk] = []
    for chunk in document.chunks:
        searchable = " ".join(part for part in (chunk.heading or "", chunk.text) if part)
        chunk_tokens = set(_meaningful_tokens(searchable))
        overlap = sorted(query_tokens & chunk_tokens)
        if not overlap:
            continue
        score = len(overlap) / len(query_tokens)
        reasons = (f"{len(overlap)} meaningful keyword overlap",)
        selected.append(DocumentContextChunk(
            chunk=chunk,
            score=round(score, 6),
            reasons=reasons,
        ))
    selected.sort(key=lambda item: (-item.score, item.chunk.scene_index, item.chunk.chunk_index))
    return tuple(selected[:normalized_limit])


def build_document_context_packet(
    document: PreparedDocument,
    query: object,
    *,
    limit: object = DEFAULT_DOCUMENT_CONTEXT_LIMIT,
) -> DocumentContextPacket:
    """Build one validated source-context packet without mutating its source."""
    normalized_query = _validate_query(query)
    return DocumentContextPacket(
        source_id=document.source_id,
        source_name=document.source_name,
        domain=document.domain,
        query=normalized_query,
        chunks=select_document_context(document, normalized_query, limit=limit),
    )


def document_context_payload(
    packet: DocumentContextPacket,
) -> list[dict[str, object]]:
    """Serialize explicitly selected source text for a trusted connector only."""
    return [
        {
            "id": record.chunk.chunk_id,
            "heading": record.chunk.heading,
            "score": record.score,
            "reasons": list(record.reasons),
            "character_count": len(record.chunk.text),
            "text": record.chunk.text,
        }
        for record in packet.chunks
    ]


__all__ = [
    "DEFAULT_DOCUMENT_CONTEXT_LIMIT",
    "DocumentContextChunk",
    "DocumentContextError",
    "DocumentContextPacket",
    "build_document_context_packet",
    "document_context_payload",
    "select_document_context",
]
