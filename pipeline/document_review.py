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


DEFAULT_REVIEW_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MAX_REVIEW_SESSIONS = 32


class DocumentReviewError(ValueError):
    """Raised for missing, expired, or invalid document review selections."""


def _normalize_candidate_selection_id(value: object, *, field: str) -> str:
    """Accept one bounded canonical ordinal, preserving case/space compatibility."""
    if not isinstance(value, str) or not value.strip():
        raise DocumentReviewError(f"{field} is required.")
    normalized = value.strip().upper()
    digits = normalized[2:]
    if (
        not normalized.startswith("C-") or not digits or len(digits) > 64
        or not digits.isascii() or not digits.isdigit()
    ):
        raise DocumentReviewError(f"{field} must use canonical C-### format.")
    index = int(digits) - 1
    if index < 0 or normalized != candidate_public_id(index):
        raise DocumentReviewError(f"{field} must use canonical C-### format.")
    return normalized


@dataclass(frozen=True)
class DocumentReviewSession:
    """One short-lived, server-side snapshot of validated candidates."""

    review_id: str
    source_id: str
    source_name: str
    domain: str
    created_at: datetime
    expires_at: datetime
    document: PreparedDocument
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
        # Candidate decisions are deliberately ephemeral just like the review
        # itself.  They make an OpenWebUI review readable without creating a
        # second durable proposal lifecycle.
        self._candidate_statuses: dict[str, dict[str, str]] = {}
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
            self._candidate_statuses.pop(review_id, None)
        overflow = len(self._sessions) - self._max_sessions
        if overflow > 0:
            oldest = sorted(self._sessions.values(), key=lambda session: (session.created_at, session.review_id))
            for session in oldest[:overflow]:
                del self._sessions[session.review_id]
                self._candidate_statuses.pop(session.review_id, None)

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
            document=document,
            candidates=candidates,
        )
        with self._lock:
            self._prune(now)
            self._sessions[session.review_id] = session
            self._candidate_statuses[session.review_id] = {
                candidate_public_id(index): "pending"
                for index in range(len(session.candidates))
            }
            self._prune(now)
        return session

    def get_review(self, review_id: object) -> tuple[DocumentReviewSession, tuple[tuple[str, str, DocumentMemoryCandidate], ...]]:
        """Return bounded candidate display data, never raw source text."""
        now = self._now()
        with self._lock:
            self._prune(now)
            normalized_review_id = review_id.strip() if isinstance(review_id, str) else ""
            session = self._sessions.get(normalized_review_id)
            if session is None:
                raise DocumentReviewError("Document review not found or expired.")
            statuses = self._candidate_statuses.get(session.review_id, {})
            candidates = tuple(
                (candidate_public_id(index), statuses.get(candidate_public_id(index), "pending"), candidate)
                for index, candidate in enumerate(session.candidates)
            )
            return session, candidates

    def list_reviews(self) -> tuple[DocumentReviewSession, ...]:
        """Return active review metadata in stable newest-first order.

        This deliberately returns sessions rather than documents/candidates.
        Callers must render only the bounded public review metadata, so a
        recovery/listing control never becomes a raw-source browsing API.
        """
        now = self._now()
        with self._lock:
            self._prune(now)
            return tuple(sorted(
                self._sessions.values(),
                key=lambda session: (session.created_at, session.review_id),
                reverse=True,
            ))

    def mark_handed_off(self, review_id: object, candidate_ids: object) -> None:
        """Record that selected candidates entered the pending-proposal flow."""
        selected = self.get_candidates(review_id, candidate_ids)
        normalized_review_id = review_id.strip()
        with self._lock:
            statuses = self._candidate_statuses[normalized_review_id]
            for candidate_id, _ in selected:
                statuses[candidate_id] = "handed_off"

    def reject_candidates(self, review_id: object, candidate_ids: object) -> tuple[str, ...]:
        """Dismiss selected review candidates without writing a proposal.

        Rejection is a short-lived review decision, not a deletion of any
        canonical memory or durable proposal.  The original review still
        expires normally and is never persisted.
        """
        selected = self.get_candidates(review_id, candidate_ids)
        normalized_review_id = review_id.strip()
        with self._lock:
            statuses = self._candidate_statuses[normalized_review_id]
            for candidate_id, _ in selected:
                statuses[candidate_id] = "rejected"
        return tuple(candidate_id for candidate_id, _ in selected)

    def get_candidate(self, review_id: object, candidate_id: object) -> DocumentMemoryCandidate:
        if not isinstance(review_id, str) or not review_id.strip():
            raise DocumentReviewError("review_id is required.")
        normalized_candidate_id = _normalize_candidate_selection_id(candidate_id, field="candidate_id")
        index = int(normalized_candidate_id[2:]) - 1
        now = self._now()
        with self._lock:
            self._prune(now)
            session = self._sessions.get(review_id.strip())
            if session is None:
                raise DocumentReviewError("Document review not found or expired.")
            if index < 0 or index >= len(session.candidates):
                raise DocumentReviewError("Document review candidate not found.")
            if self._candidate_statuses.get(session.review_id, {}).get(normalized_candidate_id) == "rejected":
                raise DocumentReviewError("Document review candidate was dismissed.")
            return session.candidates[index]

    def get_document(self, review_id: object) -> PreparedDocument:
        """Return the original bounded source only while its review is alive.

        The source is intentionally server-side and is not included in normal
        review metadata.  A later source-context request explicitly selects
        small relevant chunks from this object.
        """
        now = self._now()
        with self._lock:
            self._prune(now)
            session = self._sessions.get(review_id.strip() if isinstance(review_id, str) else "")
            if session is None:
                raise DocumentReviewError("Document review not found or expired.")
            return session.document

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
            normalized = _normalize_candidate_selection_id(candidate_id, field="candidate_ids")
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
            statuses = self._candidate_statuses.get(session.review_id, {})
            for candidate_id in normalized_ids:
                index = int(candidate_id[2:]) - 1
                if index < 0 or index >= len(session.candidates):
                    raise DocumentReviewError("Document review candidate not found.")
                if statuses.get(candidate_id) == "rejected":
                    raise DocumentReviewError("Document review candidate was dismissed.")
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
        "created_at": session.created_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
        "candidate_count": len(session.candidates),
    }


def review_candidate_public_payload(candidate_id: str, status: str, candidate: DocumentMemoryCandidate) -> dict[str, object]:
    """Return reviewable candidate facts without raw source observation text."""
    proposal = dict(candidate.proposal)
    return {
        "id": candidate_id,
        "status": status,
        "identity": candidate.source_reference.rsplit(":candidate:", 1)[-1],
        "proposal": proposal,
        "provenance": {
            "source": proposal["source"],
            "source_id": candidate.source_id,
            "source_reference": candidate.source_reference,
            "chunk_id": candidate.chunk_id,
            "observation_characters": len(candidate.observation_text),
        },
    }


__all__ = [
    "DEFAULT_MAX_REVIEW_SESSIONS",
    "DEFAULT_REVIEW_TTL_SECONDS",
    "DocumentReviewError",
    "DocumentReviewSession",
    "DocumentReviewStore",
    "candidate_public_id",
    "review_candidate_public_payload",
    "review_public_payload",
]
