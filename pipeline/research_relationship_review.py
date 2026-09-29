"""Bounded session-local review records for untrusted claim relationships.

These records retain only the structured relationship proposals and their
bindings to an existing claim review.  They neither preserve source prose nor
upgrade a model's proposed relationship into corroboration, truth, or an
answer-publication decision.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import secrets
import time

from pipeline.research_relationship_coordinator import ResearchRelationshipCoordinationResult
from pipeline.research_review import ResearchReviewRecord


RESEARCH_RELATIONSHIP_REVIEW_SCHEMA_VERSION = 1
MAX_SESSION_RESEARCH_RELATIONSHIP_REVIEWS = 20
_RELATIONSHIP_REVIEW_ID_RE = re.compile(r"^RX-[0-9a-f]{24}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ResearchRelationshipReviewRecord:
    """One noncanonical session-ephemeral relationship-review result."""

    schema_version: int
    relationship_review_id: str
    created_at_epoch: float
    claim_review_id: str
    packet_sha256: str
    target_sha256: str
    status: str
    result: ResearchRelationshipCoordinationResult

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_RELATIONSHIP_REVIEW_SCHEMA_VERSION:
            raise ValueError("research relationship review schema version is unsupported")
        if not isinstance(self.relationship_review_id, str) or not _RELATIONSHIP_REVIEW_ID_RE.fullmatch(self.relationship_review_id):
            raise ValueError("research relationship review ID is invalid")
        if (
            not isinstance(self.created_at_epoch, (int, float))
            or isinstance(self.created_at_epoch, bool)
            or not math.isfinite(float(self.created_at_epoch))
            or float(self.created_at_epoch) < 0
        ):
            raise ValueError("research relationship review timestamp is invalid")
        if not isinstance(self.claim_review_id, str) or not re.fullmatch(r"RR-[0-9a-f]{24}", self.claim_review_id):
            raise ValueError("research relationship claim review ID is invalid")
        for label, value in (("packet", self.packet_sha256), ("target", self.target_sha256)):
            if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
                raise ValueError(f"research relationship review {label} digest is invalid")
        if self.status not in {"relationships_proposed", "no_relationships"}:
            raise ValueError("research relationship review status is invalid")
        if not isinstance(self.result, ResearchRelationshipCoordinationResult):
            raise TypeError("research relationship review result is invalid")
        if (
            self.claim_review_id != self.result.review_id
            or self.packet_sha256 != self.result.packet_sha256
            or self.target_sha256 != self.result.target_sha256
            or self.status != self.result.status
        ):
            raise ValueError("research relationship review binding is inconsistent")

    def summary_dict(self) -> dict[str, object]:
        return {
            "relationship_review_id": self.relationship_review_id,
            "claim_review_id": self.claim_review_id,
            "status": self.status,
            "relationship_count": len(self.result.relationships.relationships),
        }


class SessionResearchRelationshipReviewStore:
    """Finite in-memory relationship review storage; restart discards records."""

    def __init__(self, *, clock=time.time, id_factory=None) -> None:
        if not callable(clock):
            raise TypeError("research relationship review clock is invalid")
        self._clock = clock
        self._id_factory = id_factory or (lambda: "RX-" + secrets.token_hex(12))
        if not callable(self._id_factory):
            raise TypeError("research relationship review ID factory is invalid")
        self._records: list[ResearchRelationshipReviewRecord] = []

    def create(self, review: object, result: object) -> ResearchRelationshipReviewRecord:
        if not isinstance(review, ResearchReviewRecord):
            raise TypeError("research relationship claim review is invalid")
        if not isinstance(result, ResearchRelationshipCoordinationResult):
            raise TypeError("research relationship coordination result is invalid")
        if review.review_id != result.review_id or review.packet_sha256 != result.packet_sha256:
            raise ValueError("research relationship review binding is inconsistent")
        record = ResearchRelationshipReviewRecord(
            RESEARCH_RELATIONSHIP_REVIEW_SCHEMA_VERSION,
            self._id_factory(),
            float(self._clock()),
            review.review_id,
            result.packet_sha256,
            result.target_sha256,
            result.status,
            result,
        )
        if any(item.relationship_review_id == record.relationship_review_id for item in self._records):
            raise ValueError("research relationship review ID already exists")
        self._records.append(record)
        if len(self._records) > MAX_SESSION_RESEARCH_RELATIONSHIP_REVIEWS:
            self._records.pop(0)
        return record

    def get(self, relationship_review_id: object) -> ResearchRelationshipReviewRecord | None:
        if not isinstance(relationship_review_id, str) or not _RELATIONSHIP_REVIEW_ID_RE.fullmatch(relationship_review_id):
            return None
        for record in reversed(self._records):
            if record.relationship_review_id == relationship_review_id:
                return record
        return None

    def summaries(self) -> tuple[dict[str, object], ...]:
        return tuple(record.summary_dict() for record in reversed(self._records))


__all__ = [
    "MAX_SESSION_RESEARCH_RELATIONSHIP_REVIEWS",
    "RESEARCH_RELATIONSHIP_REVIEW_SCHEMA_VERSION",
    "ResearchRelationshipReviewRecord",
    "SessionResearchRelationshipReviewStore",
]
