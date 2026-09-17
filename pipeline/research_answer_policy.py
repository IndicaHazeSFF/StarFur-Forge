"""Conservative presentation policy for reviewed research claims.

This policy makes no truth judgment. It distinguishes only an explicit local
review that contains cited claims from one that contains no supported claims.
Even an eligible result remains source-backed and unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from pipeline.research_review import ResearchReviewRecord


RESEARCH_ANSWER_POLICY_SCHEMA_VERSION = 1
_REVIEW_ID_RE = re.compile(r"^RR-[0-9a-f]{24}$")


@dataclass(frozen=True)
class ResearchAnswerDecision:
    schema_version: int
    review_id: str
    status: str
    reason: str
    claim_count: int

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_ANSWER_POLICY_SCHEMA_VERSION:
            raise ValueError("research answer policy schema version is unsupported")
        if not isinstance(self.review_id, str) or not _REVIEW_ID_RE.fullmatch(self.review_id):
            raise ValueError("research answer policy review ID is invalid")
        if self.status not in {"source_backed_unverified", "insufficient_support"}:
            raise ValueError("research answer policy status is invalid")
        expected_reason = (
            "explicit_local_review_claims" if self.status == "source_backed_unverified"
            else "no_supported_claims"
        )
        if self.reason != expected_reason:
            raise ValueError("research answer policy reason is invalid")
        if not isinstance(self.claim_count, int) or self.claim_count < 0:
            raise ValueError("research answer policy claim count is invalid")
        if (self.status == "source_backed_unverified") != bool(self.claim_count):
            raise ValueError("research answer policy claim count is inconsistent")


def evaluate_research_answer_policy(record: object) -> ResearchAnswerDecision:
    """Permit only an explicitly invoked unverified local presentation."""
    if not isinstance(record, ResearchReviewRecord):
        raise TypeError("research answer policy review record is invalid")
    count = len(record.result.claims.claims)
    return ResearchAnswerDecision(
        RESEARCH_ANSWER_POLICY_SCHEMA_VERSION,
        record.review_id,
        "source_backed_unverified" if count else "insufficient_support",
        "explicit_local_review_claims" if count else "no_supported_claims",
        count,
    )


__all__ = [
    "RESEARCH_ANSWER_POLICY_SCHEMA_VERSION",
    "ResearchAnswerDecision",
    "evaluate_research_answer_policy",
]
