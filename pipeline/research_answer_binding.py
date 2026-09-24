"""Question-to-review binding for future factual-answer presentation.

This provider-free policy confirms only whether a newly supplied canonical
question is exactly the one behind an existing session-local research review.
It does not disclose question text, call a provider, assess truth, choose
claims, or turn a review into an answer.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from pipeline.research_review import ResearchReviewRecord
from pipeline.research_sources import research_question_metadata


RESEARCH_ANSWER_BINDING_SCHEMA_VERSION = 1
_REVIEW_ID_RE = re.compile(r"^RR-[0-9a-f]{24}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ResearchAnswerBindingDecision:
    """A bounded non-authority result for one review/question comparison."""

    schema_version: int
    review_id: str
    packet_sha256: str
    question_sha256: str
    question_byte_count: int
    status: str

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_ANSWER_BINDING_SCHEMA_VERSION:
            raise ValueError("research answer binding schema version is unsupported")
        if not isinstance(self.review_id, str) or not _REVIEW_ID_RE.fullmatch(self.review_id):
            raise ValueError("research answer binding review ID is invalid")
        if not isinstance(self.packet_sha256, str) or not _DIGEST_RE.fullmatch(self.packet_sha256):
            raise ValueError("research answer binding packet digest is invalid")
        if not isinstance(self.question_sha256, str) or not _DIGEST_RE.fullmatch(self.question_sha256):
            raise ValueError("research answer binding question digest is invalid")
        if (
            isinstance(self.question_byte_count, bool)
            or not isinstance(self.question_byte_count, int)
            or not 1 <= self.question_byte_count <= 8_000
        ):
            raise ValueError("research answer binding question size is invalid")
        if self.status not in {"matches_review", "question_mismatch"}:
            raise ValueError("research answer binding status is invalid")


def evaluate_research_answer_binding(
    record: object,
    question: object,
) -> ResearchAnswerBindingDecision:
    """Compare one canonical question to one record without retaining text."""
    if not isinstance(record, ResearchReviewRecord):
        raise TypeError("research answer binding review is invalid")
    _, question_sha256, question_byte_count = research_question_metadata(question)
    matches = (
        question_sha256 == record.question_sha256
        and question_byte_count == record.question_byte_count
    )
    return ResearchAnswerBindingDecision(
        RESEARCH_ANSWER_BINDING_SCHEMA_VERSION,
        record.review_id,
        record.packet_sha256,
        question_sha256,
        question_byte_count,
        "matches_review" if matches else "question_mismatch",
    )


__all__ = [
    "RESEARCH_ANSWER_BINDING_SCHEMA_VERSION",
    "ResearchAnswerBindingDecision",
    "evaluate_research_answer_binding",
]
