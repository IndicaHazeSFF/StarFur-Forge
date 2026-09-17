"""Provider-free citation-diversity labels for research claim review.

The labels describe only the number of cited packet sources and URL hosts. They
do not establish source independence, truth, corroboration, authority, or a
final-answer eligibility decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from pipeline.research_claims import ResearchClaimSet
from pipeline.research_sources import ResearchSourcePacket


RESEARCH_EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ResearchClaimEvidence:
    schema_version: int
    claim_id: str
    cited_source_count: int
    cited_host_count: int
    citation_diversity: str

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("research evidence schema version is unsupported")
        if not isinstance(self.claim_id, str) or not self.claim_id.startswith("RC-"):
            raise ValueError("research evidence claim ID is invalid")
        if not isinstance(self.cited_source_count, int) or self.cited_source_count < 1:
            raise ValueError("research evidence source count is invalid")
        if not isinstance(self.cited_host_count, int) or not 1 <= self.cited_host_count <= self.cited_source_count:
            raise ValueError("research evidence host count is invalid")
        expected = (
            "single_source" if self.cited_source_count == 1 else
            "multiple_sources_one_host" if self.cited_host_count == 1 else
            "multiple_sources_multiple_hosts"
        )
        if self.citation_diversity != expected:
            raise ValueError("research evidence citation diversity is inconsistent")


@dataclass(frozen=True)
class ResearchEvidenceAssessment:
    schema_version: int
    packet_sha256: str
    claim_evidence: tuple[ResearchClaimEvidence, ...]

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("research evidence assessment schema version is unsupported")
        if not isinstance(self.packet_sha256, str) or len(self.packet_sha256) != 64:
            raise ValueError("research evidence packet digest is invalid")
        entries = tuple(self.claim_evidence)
        if any(not isinstance(item, ResearchClaimEvidence) for item in entries):
            raise TypeError("research evidence entry is invalid")
        if len({item.claim_id for item in entries}) != len(entries):
            raise ValueError("research evidence claim IDs must be unique")
        object.__setattr__(self, "claim_evidence", entries)

    def for_claim(self, claim_id: object) -> ResearchClaimEvidence | None:
        if not isinstance(claim_id, str):
            return None
        return next((item for item in self.claim_evidence if item.claim_id == claim_id), None)


def assess_research_evidence(packet: object, claims: object) -> ResearchEvidenceAssessment:
    """Derive bounded citation-diversity metadata from one exact packet."""
    if not isinstance(packet, ResearchSourcePacket):
        raise TypeError("research evidence packet is invalid")
    if not isinstance(claims, ResearchClaimSet):
        raise TypeError("research evidence claims are invalid")
    if claims.packet_sha256 != packet.packet_sha256:
        raise ValueError("research evidence packet binding is inconsistent")
    hosts = {}
    for source in packet.sources:
        host = urlsplit(source.url).hostname
        if not isinstance(host, str) or not host:
            raise ValueError("research evidence source host is invalid")
        hosts[source.source_id] = host.casefold()
    evidence = []
    for claim in claims.claims:
        cited_hosts = {hosts[source_id] for source_id in claim.source_ids}
        count = len(claim.source_ids)
        host_count = len(cited_hosts)
        diversity = (
            "single_source" if count == 1 else
            "multiple_sources_one_host" if host_count == 1 else
            "multiple_sources_multiple_hosts"
        )
        evidence.append(ResearchClaimEvidence(1, claim.claim_id, count, host_count, diversity))
    return ResearchEvidenceAssessment(1, packet.packet_sha256, tuple(evidence))


__all__ = [
    "RESEARCH_EVIDENCE_SCHEMA_VERSION",
    "ResearchClaimEvidence",
    "ResearchEvidenceAssessment",
    "assess_research_evidence",
]
