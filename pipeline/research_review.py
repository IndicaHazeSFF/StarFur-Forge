"""Bounded session-local review records for untrusted research claim proposals.

Records preserve only already-validated claim proposals and public source labels
for an explicit human review surface. They are neither memory nor evidence of
truth, and they never provide final-answer, approval, or persistence behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import secrets
import time

from pipeline.research_coordinator import ResearchCoordinationResult
from pipeline.research_evidence import ResearchEvidenceAssessment, assess_research_evidence
from pipeline.research_sources import ResearchSourcePacket
from pipeline.research_sources import research_question_metadata


RESEARCH_REVIEW_SCHEMA_VERSION = 1
MAX_SESSION_RESEARCH_REVIEWS = 20
_REVIEW_ID_RE = re.compile(r"^RR-[0-9a-f]{24}$")


@dataclass(frozen=True)
class ResearchReviewRecord:
    """One noncanonical, session-ephemeral research claim review result."""

    schema_version: int
    review_id: str
    created_at_epoch: float
    packet_sha256: str
    question_sha256: str
    question_byte_count: int
    status: str
    source_labels: tuple[tuple[str, str, float], ...]
    evidence: ResearchEvidenceAssessment
    result: ResearchCoordinationResult

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_REVIEW_SCHEMA_VERSION:
            raise ValueError("research review schema version is unsupported")
        if not isinstance(self.review_id, str) or not _REVIEW_ID_RE.fullmatch(self.review_id):
            raise ValueError("research review ID is invalid")
        if (
            not isinstance(self.created_at_epoch, (int, float))
            or isinstance(self.created_at_epoch, bool)
            or not math.isfinite(float(self.created_at_epoch))
            or float(self.created_at_epoch) < 0
        ):
            raise ValueError("research review timestamp is invalid")
        if not isinstance(self.packet_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.packet_sha256):
            raise ValueError("research review packet digest is invalid")
        if not isinstance(self.question_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.question_sha256):
            raise ValueError("research review question digest is invalid")
        if (
            isinstance(self.question_byte_count, bool)
            or not isinstance(self.question_byte_count, int)
            or not 1 <= self.question_byte_count <= 8_000
        ):
            raise ValueError("research review question size is invalid")
        if self.status not in {"claims_proposed", "no_supported_claims"}:
            raise ValueError("research review status is invalid")
        if not isinstance(self.evidence, ResearchEvidenceAssessment):
            raise TypeError("research review evidence is invalid")
        if self.evidence.packet_sha256 != self.packet_sha256:
            raise ValueError("research review evidence binding is inconsistent")
        if not isinstance(self.result, ResearchCoordinationResult):
            raise TypeError("research review result is invalid")
        if self.packet_sha256 != self.result.packet_sha256 or self.status != self.result.status:
            raise ValueError("research review result binding is inconsistent")
        labels = tuple(self.source_labels)
        if not labels or len(labels) > 8:
            raise ValueError("research review source labels are invalid")
        source_ids = set()
        for source_id, url, fetched_at_epoch in labels:
            if not isinstance(source_id, str) or not re.fullmatch(r"RS-[0-9a-f]{24}", source_id):
                raise ValueError("research review source ID is invalid")
            if source_id in source_ids:
                raise ValueError("research review source IDs must be unique")
            if not isinstance(url, str) or not url.startswith("https://") or len(url) > 2_048:
                raise ValueError("research review source URL is invalid")
            if (
                isinstance(fetched_at_epoch, bool)
                or not isinstance(fetched_at_epoch, (int, float))
                or not math.isfinite(float(fetched_at_epoch))
                or not 0 <= float(fetched_at_epoch) < 1e12
            ):
                raise ValueError("research review source timestamp is invalid")
            source_ids.add(source_id)
        object.__setattr__(
            self,
            "source_labels",
            tuple((source_id, url, float(fetched_at_epoch)) for source_id, url, fetched_at_epoch in labels),
        )

    def summary_dict(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "status": self.status,
            "source_count": len(self.source_labels),
            "claim_count": len(self.result.claims.claims),
        }


class SessionResearchReviewStore:
    """Finite in-memory review storage; eviction and restart discard records."""

    def __init__(self, *, clock=time.time, id_factory=None) -> None:
        if not callable(clock):
            raise TypeError("research review clock is invalid")
        self._clock = clock
        self._id_factory = id_factory or (lambda: "RR-" + secrets.token_hex(12))
        if not callable(self._id_factory):
            raise TypeError("research review ID factory is invalid")
        self._records: list[ResearchReviewRecord] = []

    def create(self, packet: object, result: object) -> ResearchReviewRecord:
        if not isinstance(packet, ResearchSourcePacket):
            raise TypeError("research review packet is invalid")
        if not isinstance(result, ResearchCoordinationResult):
            raise TypeError("research review result is invalid")
        if packet.packet_sha256 != result.packet_sha256:
            raise ValueError("research review packet binding is inconsistent")
        review_id = self._id_factory()
        _, question_sha256, question_byte_count = research_question_metadata(packet.question)
        record = ResearchReviewRecord(
            RESEARCH_REVIEW_SCHEMA_VERSION,
            review_id,
            float(self._clock()),
            packet.packet_sha256,
            question_sha256,
            question_byte_count,
            result.status,
            tuple((source.source_id, source.url, source.fetched_at_epoch) for source in packet.sources),
            assess_research_evidence(packet, result.claims),
            result,
        )
        if any(item.review_id == record.review_id for item in self._records):
            raise ValueError("research review ID already exists")
        self._records.append(record)
        if len(self._records) > MAX_SESSION_RESEARCH_REVIEWS:
            self._records.pop(0)
        return record

    def get(self, review_id: object) -> ResearchReviewRecord | None:
        if not isinstance(review_id, str) or not _REVIEW_ID_RE.fullmatch(review_id):
            return None
        for record in reversed(self._records):
            if record.review_id == review_id:
                return record
        return None

    def summaries(self) -> tuple[dict[str, object], ...]:
        return tuple(record.summary_dict() for record in reversed(self._records))


__all__ = [
    "MAX_SESSION_RESEARCH_REVIEWS",
    "RESEARCH_REVIEW_SCHEMA_VERSION",
    "ResearchReviewRecord",
    "SessionResearchReviewStore",
]
