"""Pure content-free read model for disconnected annotation-job progress.

Counts describe saved data, not factual quality, provider readiness, admission,
authentication, or permission to read a document. No storage is accessed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from pipeline.document_jobs import AnnotationJobMetadata


PROGRESS_SCHEMA_VERSION = 1
MAX_PROGRESS_CHUNKS = 100_000
MAX_PROGRESS_CANDIDATES = 4096


class AnnotationJobProgressError(ValueError):
    """Invalid bounded job progress metadata."""


def _count(value: object, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum


@dataclass(frozen=True)
class AnnotationJobProgress:
    job_id: str
    metadata: AnnotationJobMetadata
    total_chunks: int
    checkpointed_chunks: int
    pending_chunks: int
    candidate_count: int
    failed_chunks: int
    result_available: bool
    schema_version: int = PROGRESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (type(self.schema_version) is not int or self.schema_version != PROGRESS_SCHEMA_VERSION
                or not isinstance(self.job_id, str) or re.fullmatch(r"AJ-[0-9a-f]{32}", self.job_id) is None
                or type(self.metadata) is not AnnotationJobMetadata):
            raise AnnotationJobProgressError("annotation progress identity/schema is invalid")
        for value in (self.total_chunks, self.checkpointed_chunks, self.pending_chunks, self.failed_chunks):
            if not _count(value, MAX_PROGRESS_CHUNKS):
                raise AnnotationJobProgressError("annotation progress counts are invalid")
        if (not _count(self.candidate_count, MAX_PROGRESS_CANDIDATES)
                or type(self.result_available) is not bool
                or self.checkpointed_chunks > self.total_chunks
                or self.failed_chunks > self.total_chunks):
            raise AnnotationJobProgressError("annotation progress counts are invalid")
        completed = self.metadata.state == "completed"
        if self.result_available != completed:
            raise AnnotationJobProgressError("annotation result availability conflicts with state")
        if completed:
            if self.pending_chunks != 0 or self.checkpointed_chunks not in {0, self.total_chunks}:
                raise AnnotationJobProgressError("completed annotation progress is inconsistent")
        elif (self.pending_chunks != self.total_chunks - self.checkpointed_chunks
              or self.failed_chunks > self.checkpointed_chunks
              or (self.checkpointed_chunks == 0 and self.candidate_count != 0)):
            raise AnnotationJobProgressError("annotation checkpoint progress is inconsistent")

    def to_public_dict(self) -> dict[str, object]:
        """Fresh allowlisted values for a future authorized presentation adapter."""
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "state": self.metadata.state,
            "submitted_at": self.metadata.submitted_at.isoformat(),
            "expires_at": self.metadata.expires_at.isoformat(),
            "total_chunks": self.total_chunks,
            "checkpointed_chunks": self.checkpointed_chunks,
            "pending_chunks": self.pending_chunks,
            "candidate_count": self.candidate_count,
            "failed_chunks": self.failed_chunks,
            "result_available": self.result_available,
        }
