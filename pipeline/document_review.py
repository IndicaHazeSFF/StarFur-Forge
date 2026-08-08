"""Bounded in-memory review sessions for external document candidates.

Annotation results are intentionally not durable until a user explicitly sends
one selected candidate through the normal pending-proposal writer.  Retaining
the validated candidate server-side prevents a client from supplying altered
summary, domain, or provenance fields during that handoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import threading
from typing import Callable
from uuid import uuid4

from pipeline.document_intake import DocumentMemoryCandidate, PreparedDocument


DEFAULT_REVIEW_TTL_SECONDS = 15 * 60
DEFAULT_MAX_REVIEW_SESSIONS = 32


class DocumentReviewError(ValueError):
    """Raised for missing, expired, or invalid document review selections."""


@dataclass(frozen=True)
class DocumentReviewSession:
    """One short-lived, server-side snapshot of validated candidates."""

    review_id: str
    source_id: str
    source_name: str
    domain: str
    created_at: datetime
    expires_at: datetime
    candidates: tuple[DocumentMemoryCandidate, ...]


class DocumentReviewStore:
    """Thread-safe, bounded, non-durable external-document review storage."""

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_REVIEW_TTL_SECONDS,
        max_sessions: int = DEFAULT_MAX_REVIEW_SESSIONS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive integer.")
        if isinstance(max_sessions, bool) or not isinstance(max_sessions, int) or max_sessions <= 0:
            raise ValueError("max_sessions must be a positive integer.")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_sessions = max_sessions
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sessions: dict[str, DocumentReviewSession] = {}
        self._lock = threading.RLock()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _prune(self, now: datetime) -> None:
        expired = [review_id for review_id, session in self._sessions.items() if session.expires_at <= now]
        for review_id in expired:
            del self._sessions[review_id]
        overflow = len(self._sessions) - self._max_sessions
        if overflow > 0:
            oldest = sorted(self._sessions.values(), key=lambda session: (session.created_at, session.review_id))
            for session in oldest[:overflow]:
                del self._sessions[session.review_id]

    def create(
        self,
        document: PreparedDocument,
        candidates: tuple[DocumentMemoryCandidate, ...],
    ) -> DocumentReviewSession:
        if not isinstance(document, PreparedDocument):
            raise TypeError("document must be a PreparedDocument.")
        if not isinstance(candidates, tuple):
            candidates = tuple(candidates)
        if any(not isinstance(candidate, DocumentMemoryCandidate) for candidate in candidates):
            raise TypeError("candidates must contain DocumentMemoryCandidate records.")
        if any(candidate.source_id != document.source_id or candidate.proposal.get("domain") != document.domain for candidate in candidates):
            raise DocumentReviewError("Candidate provenance does not match the prepared document.")
        now = self._now()
        session = DocumentReviewSession(
            review_id="DR-" + uuid4().hex,
            source_id=document.source_id,
            source_name=document.source_name,
            domain=document.domain,
            created_at=now,
            expires_at=now + self._ttl,
            candidates=candidates,
        )
        with self._lock:
            self._prune(now)
            self._sessions[session.review_id] = session
            self._prune(now)
        return session

    def get_candidate(self, review_id: object, candidate_id: object) -> DocumentMemoryCandidate:
        if not isinstance(review_id, str) or not review_id.strip():
            raise DocumentReviewError("review_id is required.")
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise DocumentReviewError("candidate_id is required.")
        normalized_candidate_id = candidate_id.strip().upper()
        if not normalized_candidate_id.startswith("C-") or not normalized_candidate_id[2:].isdigit():
            raise DocumentReviewError("candidate_id must use C-### format.")
        index = int(normalized_candidate_id[2:]) - 1
        now = self._now()
        with self._lock:
            self._prune(now)
            session = self._sessions.get(review_id.strip())
            if session is None:
                raise DocumentReviewError("Document review not found or expired.")
            if index < 0 or index >= len(session.candidates):
                raise DocumentReviewError("Document review candidate not found.")
            return session.candidates[index]

    def get_candidates(
        self,
        review_id: object,
        candidate_ids: object,
    ) -> tuple[tuple[str, DocumentMemoryCandidate], ...]:
        """Return an ordered, validated batch of original server candidates.

        Validate every identifier before any caller can persist a candidate so
        a malformed batch cannot produce a partial handoff.  Candidate IDs
        remain display ordinals local to one review; their persistence
        provenance is content-derived by document intake.
        """
        if not isinstance(candidate_ids, list) or not candidate_ids:
            raise DocumentReviewError("candidate_ids must be a non-empty list.")
        if len(candidate_ids) > 128:
            raise DocumentReviewError("candidate_ids exceeds the review batch limit.")
        normalized_ids: list[str] = []
        for candidate_id in candidate_ids:
            if not isinstance(candidate_id, str) or not candidate_id.strip():
                raise DocumentReviewError("candidate_ids must contain C-### identifiers.")
            normalized = candidate_id.strip().upper()
            if not normalized.startswith("C-") or not normalized[2:].isdigit():
                raise DocumentReviewError("candidate_ids must contain C-### identifiers.")
            if normalized in normalized_ids:
                raise DocumentReviewError("candidate_ids must not contain duplicates.")
            normalized_ids.append(normalized)
        now = self._now()
        with self._lock:
            self._prune(now)
            session = self._sessions.get(review_id.strip() if isinstance(review_id, str) else "")
            if session is None:
                raise DocumentReviewError("Document review not found or expired.")
            selected: list[tuple[str, DocumentMemoryCandidate]] = []
            for candidate_id in normalized_ids:
                index = int(candidate_id[2:]) - 1
                if index < 0 or index >= len(session.candidates):
                    raise DocumentReviewError("Document review candidate not found.")
                selected.append((candidate_id, session.candidates[index]))
            return tuple(selected)


def candidate_public_id(index: int) -> str:
    """Return the stable display identifier for a candidate within one review."""
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("candidate index must be a non-negative integer.")
    return f"C-{index + 1:03d}"


def review_public_payload(session: DocumentReviewSession) -> dict[str, object]:
    """Return bounded metadata that never includes raw document chunk text."""
    return {
        "id": session.review_id,
        "expires_at": session.expires_at.isoformat(),
        "candidate_count": len(session.candidates),
    }


__all__ = [
    "DEFAULT_MAX_REVIEW_SESSIONS",
    "DEFAULT_REVIEW_TTL_SECONDS",
    "DocumentReviewError",
    "DocumentReviewSession",
    "DocumentReviewStore",
    "candidate_public_id",
    "review_public_payload",
]
