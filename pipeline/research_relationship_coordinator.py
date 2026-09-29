"""Nonpublishing coordinator for one claim-relationship proposal attempt.

The coordinator joins one exact review, local-only disclosure decision, prompt
envelope, injected minimal provider, structured schema, and strict parser.  It
does not fetch, route, retry, fall back, publish an answer, establish truth, or
write any state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pipeline.research_disclosure import ResearchProviderTarget
from pipeline.research_relationship_disclosure import ResearchRelationshipDisclosureDecision
from pipeline.research_relationship_prompt import build_research_relationship_messages
from pipeline.research_relationships import (
    ResearchClaimRelationshipSet,
    parse_research_claim_relationships,
    research_claim_relationship_json_schema,
)
from pipeline.research_review import ResearchReviewRecord


RESEARCH_RELATIONSHIP_COORDINATOR_SCHEMA_VERSION = 1


@runtime_checkable
class ResearchRelationshipProvider(Protocol):
    """Minimal injected adapter; it owns neither policy nor authority."""

    @property
    def available(self) -> bool: ...

    def propose_relationships(
        self,
        messages: tuple[dict[str, str], dict[str, str]],
        *,
        model: str,
        schema: dict[str, object],
    ) -> str: ...


class ResearchRelationshipCoordinatorError(RuntimeError):
    """Bounded operational failure without retaining provider output."""

    def __init__(self, reason: str) -> None:
        if reason not in {
            "disclosure_denied",
            "provider_unavailable",
            "provider_failed",
            "response_invalid",
        }:
            raise ValueError("research relationship coordinator failure reason is invalid")
        super().__init__("research relationship generation failed safely")
        self.reason = reason


@dataclass(frozen=True)
class ResearchRelationshipCoordinationResult:
    schema_version: int
    review_id: str
    packet_sha256: str
    target_sha256: str
    status: str
    relationships: ResearchClaimRelationshipSet

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != RESEARCH_RELATIONSHIP_COORDINATOR_SCHEMA_VERSION
        ):
            raise ValueError("research relationship coordination schema version is unsupported")
        if self.status not in {"relationships_proposed", "no_relationships"}:
            raise ValueError("research relationship coordination status is invalid")
        if not isinstance(self.relationships, ResearchClaimRelationshipSet):
            raise TypeError("research relationship coordination result is invalid")
        if (
            self.review_id != self.relationships.review_id
            or self.packet_sha256 != self.relationships.packet_sha256
        ):
            raise ValueError("research relationship coordination binding is inconsistent")
        if not isinstance(self.target_sha256, str) or len(self.target_sha256) != 64:
            raise ValueError("research relationship coordination target digest is invalid")
        if self.status == "relationships_proposed" and not self.relationships.relationships:
            raise ValueError("research relationship coordination status requires proposals")
        if self.status == "no_relationships" and self.relationships.relationships:
            raise ValueError("research relationship empty status cannot contain proposals")


class ResearchRelationshipCoordinator:
    """Perform one bounded noncanonical relationship-proposal attempt."""

    def __init__(self, provider: object) -> None:
        if not isinstance(provider, ResearchRelationshipProvider):
            raise TypeError("research relationship provider is invalid")
        self._provider = provider

    def propose(
        self,
        review: object,
        target: object,
        decision: object,
    ) -> ResearchRelationshipCoordinationResult:
        if not isinstance(review, ResearchReviewRecord):
            raise TypeError("research relationship review is invalid")
        if not isinstance(target, ResearchProviderTarget):
            raise TypeError("research relationship provider target is invalid")
        if not isinstance(decision, ResearchRelationshipDisclosureDecision):
            raise TypeError("research relationship disclosure decision is invalid")
        try:
            messages = build_research_relationship_messages(review, target, decision)
        except (TypeError, ValueError) as error:
            raise ResearchRelationshipCoordinatorError("disclosure_denied") from error
        try:
            available = self._provider.available
        except Exception as error:
            raise ResearchRelationshipCoordinatorError("provider_unavailable") from error
        if available is not True:
            raise ResearchRelationshipCoordinatorError("provider_unavailable")
        try:
            raw = self._provider.propose_relationships(
                messages,
                model=target.model,
                schema=research_claim_relationship_json_schema(review),
            )
        except Exception as error:
            raise ResearchRelationshipCoordinatorError("provider_failed") from error
        try:
            relationships = parse_research_claim_relationships(raw, review)
        except (TypeError, ValueError) as error:
            raise ResearchRelationshipCoordinatorError("response_invalid") from error
        status = "relationships_proposed" if relationships.relationships else "no_relationships"
        return ResearchRelationshipCoordinationResult(
            RESEARCH_RELATIONSHIP_COORDINATOR_SCHEMA_VERSION,
            review.review_id,
            review.packet_sha256,
            target.target_sha256,
            status,
            relationships,
        )


__all__ = [
    "RESEARCH_RELATIONSHIP_COORDINATOR_SCHEMA_VERSION",
    "ResearchRelationshipCoordinationResult",
    "ResearchRelationshipCoordinator",
    "ResearchRelationshipCoordinatorError",
    "ResearchRelationshipProvider",
]
