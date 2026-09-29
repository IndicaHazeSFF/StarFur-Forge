"""Pure local-only disclosure policy for claim-relationship evaluation.

The policy binds one exact session-local review and one exact provider target.
It permits only bounded claim/source labels already present in the review to a
local provider.  It is not provider availability, relationship truth, answer
authority, persistence permission, or a tool grant.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from pipeline.research_disclosure import ResearchProviderTarget
from pipeline.research_review import ResearchReviewRecord


RESEARCH_RELATIONSHIP_DISCLOSURE_SCHEMA_VERSION = 1
RESEARCH_RELATIONSHIP_DISCLOSURE_POLICY_REVISION = "research-claim-relations-local-v1"
_REVIEW_ID_RE = re.compile(r"^RR-[0-9a-f]{24}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _review_character_count(review: ResearchReviewRecord) -> int:
    return sum(
        len(claim.statement)
        + sum(len(source_id) for source_id in claim.source_ids)
        for claim in review.result.claims.claims
    ) + sum(len(source_id) + len(url) for source_id, url, _ in review.source_labels)


@dataclass(frozen=True)
class ResearchRelationshipDisclosureIntent:
    schema_version: int
    review_id: str
    packet_sha256: str
    claim_count: int
    source_count: int
    review_character_count: int
    data_classification: str
    purpose: str
    target: ResearchProviderTarget
    policy_revision: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != RESEARCH_RELATIONSHIP_DISCLOSURE_SCHEMA_VERSION
        ):
            raise ValueError("research relationship disclosure schema version is unsupported")
        if not isinstance(self.review_id, str) or not _REVIEW_ID_RE.fullmatch(self.review_id):
            raise ValueError("research relationship disclosure review ID is invalid")
        if not isinstance(self.packet_sha256, str) or not _DIGEST_RE.fullmatch(self.packet_sha256):
            raise ValueError("research relationship disclosure packet digest is invalid")
        if isinstance(self.claim_count, bool) or not isinstance(self.claim_count, int) or not 0 <= self.claim_count <= 16:
            raise ValueError("research relationship disclosure claim count is invalid")
        if isinstance(self.source_count, bool) or not isinstance(self.source_count, int) or not 1 <= self.source_count <= 8:
            raise ValueError("research relationship disclosure source count is invalid")
        if (
            isinstance(self.review_character_count, bool)
            or not isinstance(self.review_character_count, int)
            or not 1 <= self.review_character_count <= 32_000
        ):
            raise ValueError("research relationship disclosure character count is invalid")
        if self.data_classification != "local_public_review_metadata":
            raise ValueError("research relationship disclosure classification is unsupported")
        if self.purpose != "claim_relationship_proposal":
            raise ValueError("research relationship disclosure purpose is unsupported")
        if not isinstance(self.target, ResearchProviderTarget):
            raise TypeError("research relationship disclosure target is invalid")
        if self.policy_revision != RESEARCH_RELATIONSHIP_DISCLOSURE_POLICY_REVISION:
            raise ValueError("research relationship disclosure policy revision is unsupported")

    @classmethod
    def from_review(cls, review: object, target: object):
        if not isinstance(review, ResearchReviewRecord):
            raise TypeError("research relationship review is invalid")
        if not isinstance(target, ResearchProviderTarget):
            raise TypeError("research relationship provider target is invalid")
        return cls(
            RESEARCH_RELATIONSHIP_DISCLOSURE_SCHEMA_VERSION,
            review.review_id,
            review.packet_sha256,
            len(review.result.claims.claims),
            len(review.source_labels),
            _review_character_count(review),
            "local_public_review_metadata",
            "claim_relationship_proposal",
            target,
            RESEARCH_RELATIONSHIP_DISCLOSURE_POLICY_REVISION,
        )


@dataclass(frozen=True)
class ResearchRelationshipDisclosureDecision:
    schema_version: int
    status: str
    reason: str
    review_id: str
    packet_sha256: str
    target_sha256: str
    policy_revision: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != RESEARCH_RELATIONSHIP_DISCLOSURE_SCHEMA_VERSION
        ):
            raise ValueError("research relationship disclosure decision schema is unsupported")
        if self.status not in {"permitted", "denied"}:
            raise ValueError("research relationship disclosure decision status is invalid")
        if self.reason not in {
            "permitted_local_review_metadata",
            "review_binding_mismatch",
            "intent_mismatch",
            "insufficient_claims",
            "hosted_disclosure_unsupported",
        }:
            raise ValueError("research relationship disclosure decision reason is invalid")
        if not isinstance(self.review_id, str) or not _REVIEW_ID_RE.fullmatch(self.review_id):
            raise ValueError("research relationship disclosure decision review ID is invalid")
        for label, value in (("packet", self.packet_sha256), ("target", self.target_sha256)):
            if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
                raise ValueError(f"research relationship disclosure decision {label} digest is invalid")
        if self.policy_revision != RESEARCH_RELATIONSHIP_DISCLOSURE_POLICY_REVISION:
            raise ValueError("research relationship disclosure decision policy revision is unsupported")


def evaluate_research_relationship_disclosure(
    intent: object,
    review: object,
) -> ResearchRelationshipDisclosureDecision:
    """Permit exact bounded review metadata to an explicit local target only."""
    if not isinstance(intent, ResearchRelationshipDisclosureIntent):
        raise TypeError("research relationship disclosure intent is invalid")
    if not isinstance(review, ResearchReviewRecord):
        raise TypeError("research relationship review is invalid")

    def decision(status: str, reason: str) -> ResearchRelationshipDisclosureDecision:
        return ResearchRelationshipDisclosureDecision(
            RESEARCH_RELATIONSHIP_DISCLOSURE_SCHEMA_VERSION,
            status,
            reason,
            intent.review_id,
            intent.packet_sha256,
            intent.target.target_sha256,
            intent.policy_revision,
        )

    if intent.review_id != review.review_id or intent.packet_sha256 != review.packet_sha256:
        return decision("denied", "review_binding_mismatch")
    if (
        intent.claim_count != len(review.result.claims.claims)
        or intent.source_count != len(review.source_labels)
        or intent.review_character_count != _review_character_count(review)
        or intent.data_classification != "local_public_review_metadata"
        or intent.purpose != "claim_relationship_proposal"
    ):
        return decision("denied", "intent_mismatch")
    if intent.claim_count < 2:
        return decision("denied", "insufficient_claims")
    if intent.target.deployment != "local":
        return decision("denied", "hosted_disclosure_unsupported")
    return decision("permitted", "permitted_local_review_metadata")


__all__ = [
    "RESEARCH_RELATIONSHIP_DISCLOSURE_POLICY_REVISION",
    "RESEARCH_RELATIONSHIP_DISCLOSURE_SCHEMA_VERSION",
    "ResearchRelationshipDisclosureDecision",
    "ResearchRelationshipDisclosureIntent",
    "evaluate_research_relationship_disclosure",
]
