"""Deterministic presentation of one untrusted relationship review.

This module joins an existing claim review and its exact session-local
relationship review for human inspection.  It does not assess truth, infer
corroboration, call a provider, or create any writable state.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.research_relationship_review import ResearchRelationshipReviewRecord
from pipeline.research_review import ResearchReviewRecord


RESEARCH_RELATIONSHIP_BRIEF_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ResearchRelationshipBriefItem:
    relationship_id: str
    left_claim_id: str
    left_statement: str
    right_claim_id: str
    right_statement: str
    relation: str
    confidence: float


@dataclass(frozen=True)
class ResearchRelationshipBrief:
    schema_version: int
    relationship_review_id: str
    claim_review_id: str
    status: str
    items: tuple[ResearchRelationshipBriefItem, ...]

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_RELATIONSHIP_BRIEF_SCHEMA_VERSION:
            raise ValueError("research relationship brief schema version is unsupported")
        if not isinstance(self.relationship_review_id, str) or not self.relationship_review_id.startswith("RX-"):
            raise ValueError("research relationship brief ID is invalid")
        if not isinstance(self.claim_review_id, str) or not self.claim_review_id.startswith("RR-"):
            raise ValueError("research relationship brief claim review ID is invalid")
        if self.status not in {"relationships_proposed", "no_relationships"}:
            raise ValueError("research relationship brief status is invalid")
        items = tuple(self.items)
        if any(not isinstance(item, ResearchRelationshipBriefItem) for item in items):
            raise TypeError("research relationship brief items are invalid")
        if self.status == "relationships_proposed" and not items:
            raise ValueError("research relationship brief proposal status requires items")
        if self.status == "no_relationships" and items:
            raise ValueError("research relationship brief empty status cannot contain items")
        object.__setattr__(self, "items", items)


def build_research_relationship_brief(
    review: object,
    relationship_review: object,
) -> ResearchRelationshipBrief:
    """Project only exact already-reviewed relationship proposals for display."""
    if not isinstance(review, ResearchReviewRecord):
        raise TypeError("research relationship claim review is invalid")
    if not isinstance(relationship_review, ResearchRelationshipReviewRecord):
        raise TypeError("research relationship review is invalid")
    if (
        relationship_review.claim_review_id != review.review_id
        or relationship_review.packet_sha256 != review.packet_sha256
    ):
        raise ValueError("research relationship brief review binding is inconsistent")
    claims = {item.claim_id: item.statement for item in review.result.claims.claims}
    items = []
    for relationship in relationship_review.result.relationships.relationships:
        try:
            left_statement = claims[relationship.left_claim_id]
            right_statement = claims[relationship.right_claim_id]
        except KeyError as error:
            raise ValueError("research relationship references a missing reviewed claim") from error
        items.append(ResearchRelationshipBriefItem(
            relationship.relationship_id,
            relationship.left_claim_id,
            left_statement,
            relationship.right_claim_id,
            right_statement,
            relationship.relation,
            relationship.confidence,
        ))
    return ResearchRelationshipBrief(
        RESEARCH_RELATIONSHIP_BRIEF_SCHEMA_VERSION,
        relationship_review.relationship_review_id,
        review.review_id,
        relationship_review.status,
        tuple(items),
    )


__all__ = [
    "RESEARCH_RELATIONSHIP_BRIEF_SCHEMA_VERSION",
    "ResearchRelationshipBrief",
    "ResearchRelationshipBriefItem",
    "build_research_relationship_brief",
]
