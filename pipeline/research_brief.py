"""Deterministic, nonauthoritative rendering data for reviewed research claims.

A cited brief is a compact presentation of an existing session-local claim
review. It does not verify claims, call a model, infer an answer, or retain
source prose. Clients must label it source-backed but unverified.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from pipeline.research_review import ResearchReviewRecord


RESEARCH_BRIEF_SCHEMA_VERSION = 1
_REVIEW_ID_RE = re.compile(r"^RR-[0-9a-f]{24}$")


@dataclass(frozen=True)
class ResearchBriefCitation:
    schema_version: int
    source_id: str
    url: str

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_BRIEF_SCHEMA_VERSION:
            raise ValueError("research brief citation schema version is unsupported")
        if not isinstance(self.source_id, str) or not re.fullmatch(r"RS-[0-9a-f]{24}", self.source_id):
            raise ValueError("research brief citation source ID is invalid")
        if not isinstance(self.url, str) or not self.url.startswith("https://") or len(self.url) > 2_048:
            raise ValueError("research brief citation URL is invalid")


@dataclass(frozen=True)
class ResearchBriefClaim:
    schema_version: int
    claim_id: str
    statement: str
    citations: tuple[ResearchBriefCitation, ...]
    citation_diversity: str

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_BRIEF_SCHEMA_VERSION:
            raise ValueError("research brief claim schema version is unsupported")
        if not isinstance(self.claim_id, str) or not re.fullmatch(r"RC-[0-9]{3}", self.claim_id):
            raise ValueError("research brief claim ID is invalid")
        if not isinstance(self.statement, str) or not self.statement.strip() or len(self.statement) > 1_000:
            raise ValueError("research brief claim statement is invalid")
        citations = tuple(self.citations)
        if not citations or len(citations) > 4 or any(not isinstance(item, ResearchBriefCitation) for item in citations):
            raise ValueError("research brief citations are invalid")
        if self.citation_diversity not in {
            "single_source", "multiple_sources_one_host", "multiple_sources_multiple_hosts",
        }:
            raise ValueError("research brief citation diversity is invalid")
        object.__setattr__(self, "citations", citations)


@dataclass(frozen=True)
class ResearchCitedBrief:
    schema_version: int
    review_id: str
    status: str
    claims: tuple[ResearchBriefClaim, ...]

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_BRIEF_SCHEMA_VERSION:
            raise ValueError("research brief schema version is unsupported")
        if not isinstance(self.review_id, str) or not _REVIEW_ID_RE.fullmatch(self.review_id):
            raise ValueError("research brief review ID is invalid")
        if self.status not in {"claims_available", "no_supported_claims"}:
            raise ValueError("research brief status is invalid")
        claims = tuple(self.claims)
        if any(not isinstance(item, ResearchBriefClaim) for item in claims):
            raise TypeError("research brief claims are invalid")
        if len({item.claim_id for item in claims}) != len(claims):
            raise ValueError("research brief claim IDs must be unique")
        if (self.status == "claims_available") != bool(claims):
            raise ValueError("research brief status is inconsistent")
        object.__setattr__(self, "claims", claims)


def build_research_cited_brief(record: object) -> ResearchCitedBrief:
    """Project one existing review into a source-backed, unverified brief."""
    if not isinstance(record, ResearchReviewRecord):
        raise TypeError("research brief review record is invalid")
    labels = dict(record.source_labels)
    claims = []
    for claim in record.result.claims.claims:
        evidence = record.evidence.for_claim(claim.claim_id)
        if evidence is None:
            raise ValueError("research brief evidence is missing")
        citations = []
        for source_id in claim.source_ids:
            url = labels.get(source_id)
            if url is None:
                raise ValueError("research brief citation is outside the review")
            citations.append(ResearchBriefCitation(1, source_id, url))
        claims.append(ResearchBriefClaim(
            1, claim.claim_id, claim.statement, tuple(citations), evidence.citation_diversity,
        ))
    return ResearchCitedBrief(
        1,
        record.review_id,
        "claims_available" if claims else "no_supported_claims",
        tuple(claims),
    )


__all__ = [
    "RESEARCH_BRIEF_SCHEMA_VERSION",
    "ResearchBriefCitation",
    "ResearchBriefClaim",
    "ResearchCitedBrief",
    "build_research_cited_brief",
]
