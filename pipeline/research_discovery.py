"""Provider-free eligibility policy for factual source discovery.

This boundary separates recognizing that research is required from permission
to disclose a query or use a tool.  It retains only a normalized query digest
and bounded metadata.  A decision can mark local discovery eligible or require
an exact broker confirmation for public web search; it never grants authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from pipeline.factual_research_policy import FactualResearchDecision


RESEARCH_DISCOVERY_SCHEMA_VERSION = 1
RESEARCH_DISCOVERY_POLICY_REVISION = "research-discovery-v1"
MAX_RESEARCH_DISCOVERY_QUERY_BYTES = 4096
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_TARGET_KINDS = frozenset({"local_catalog", "public_web_search"})
_CLASSIFICATIONS = frozenset({"public", "private", "secret"})
_STATUSES = frozenset({"eligible", "confirmation_required", "denied"})
_REASONS = frozenset({
    "local_discovery_eligible",
    "public_search_requires_broker_confirmation",
    "private_query_disclosure_unsupported",
    "secret_query_disclosure_forbidden",
    "research_not_required",
    "request_binding_mismatch",
})


def _canonical_query(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("research discovery query must be text")
    query = " ".join(value.strip().split())
    if not query or "\x00" in query:
        raise ValueError("research discovery query is invalid")
    try:
        encoded = query.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("research discovery query is not valid UTF-8") from error
    if len(encoded) > MAX_RESEARCH_DISCOVERY_QUERY_BYTES:
        raise ValueError("research discovery query size limit exceeded")
    return query


def _query_digest(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchDiscoveryIntent:
    schema_version: int
    query_sha256: str
    query_byte_count: int
    trigger_reason: str
    target_kind: str
    data_classification: str
    policy_revision: str

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_DISCOVERY_SCHEMA_VERSION:
            raise ValueError("research discovery schema version is unsupported")
        if not isinstance(self.query_sha256, str) or not _DIGEST_RE.fullmatch(self.query_sha256):
            raise ValueError("research discovery query digest is invalid")
        if (
            isinstance(self.query_byte_count, bool)
            or not isinstance(self.query_byte_count, int)
            or not 1 <= self.query_byte_count <= MAX_RESEARCH_DISCOVERY_QUERY_BYTES
        ):
            raise ValueError("research discovery query size is invalid")
        if self.trigger_reason not in {
            "explicit_research_request",
            "freshness_sensitive_request",
            "high_stakes_request",
            "no_mandatory_research_signal",
            "fictional_context",
        }:
            raise ValueError("research discovery trigger is invalid")
        if self.target_kind not in _TARGET_KINDS:
            raise ValueError("research discovery target is invalid")
        if self.data_classification not in _CLASSIFICATIONS:
            raise ValueError("research discovery classification is invalid")
        if self.policy_revision != RESEARCH_DISCOVERY_POLICY_REVISION:
            raise ValueError("research discovery policy revision is unsupported")

    @classmethod
    def from_request(
        cls,
        query: object,
        decision: object,
        *,
        target_kind: object,
        data_classification: object,
    ) -> "ResearchDiscoveryIntent":
        if not isinstance(decision, FactualResearchDecision):
            raise TypeError("factual research decision is invalid")
        canonical = _canonical_query(query)
        if target_kind not in _TARGET_KINDS:
            raise ValueError("research discovery target is invalid")
        if data_classification not in _CLASSIFICATIONS:
            raise ValueError("research discovery classification is invalid")
        return cls(
            RESEARCH_DISCOVERY_SCHEMA_VERSION,
            _query_digest(canonical),
            len(canonical.encode("utf-8")),
            decision.reason,
            target_kind,
            data_classification,
            RESEARCH_DISCOVERY_POLICY_REVISION,
        )


@dataclass(frozen=True)
class ResearchDiscoveryDecision:
    schema_version: int
    status: str
    reason: str
    query_sha256: str
    target_kind: str
    policy_revision: str

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_DISCOVERY_SCHEMA_VERSION:
            raise ValueError("research discovery decision schema is unsupported")
        if self.status not in _STATUSES or self.reason not in _REASONS:
            raise ValueError("research discovery decision is invalid")
        expected = {
            "eligible": {"local_discovery_eligible"},
            "confirmation_required": {"public_search_requires_broker_confirmation"},
            "denied": {
                "private_query_disclosure_unsupported",
                "secret_query_disclosure_forbidden",
                "research_not_required",
                "request_binding_mismatch",
            },
        }
        if self.reason not in expected[self.status]:
            raise ValueError("research discovery decision is inconsistent")
        if not isinstance(self.query_sha256, str) or not _DIGEST_RE.fullmatch(self.query_sha256):
            raise ValueError("research discovery decision digest is invalid")
        if self.target_kind not in _TARGET_KINDS:
            raise ValueError("research discovery decision target is invalid")
        if self.policy_revision != RESEARCH_DISCOVERY_POLICY_REVISION:
            raise ValueError("research discovery decision policy is unsupported")


def evaluate_research_discovery(
    intent: object,
    query: object,
    factual_decision: object,
) -> ResearchDiscoveryDecision:
    """Return eligibility or a confirmation requirement, never authority."""
    if not isinstance(intent, ResearchDiscoveryIntent):
        raise TypeError("research discovery intent is invalid")
    if not isinstance(factual_decision, FactualResearchDecision):
        raise TypeError("factual research decision is invalid")
    canonical = _canonical_query(query)

    def result(status: str, reason: str) -> ResearchDiscoveryDecision:
        return ResearchDiscoveryDecision(
            RESEARCH_DISCOVERY_SCHEMA_VERSION,
            status,
            reason,
            intent.query_sha256,
            intent.target_kind,
            intent.policy_revision,
        )

    if (
        intent.query_sha256 != _query_digest(canonical)
        or intent.query_byte_count != len(canonical.encode("utf-8"))
        or intent.trigger_reason != factual_decision.reason
    ):
        return result("denied", "request_binding_mismatch")
    if factual_decision.disposition != "research_required":
        return result("denied", "research_not_required")
    if intent.data_classification == "secret":
        return result("denied", "secret_query_disclosure_forbidden")
    if intent.target_kind == "public_web_search" and intent.data_classification == "private":
        return result("denied", "private_query_disclosure_unsupported")
    if intent.target_kind == "public_web_search":
        return result("confirmation_required", "public_search_requires_broker_confirmation")
    return result("eligible", "local_discovery_eligible")


__all__ = [
    "MAX_RESEARCH_DISCOVERY_QUERY_BYTES",
    "RESEARCH_DISCOVERY_POLICY_REVISION",
    "RESEARCH_DISCOVERY_SCHEMA_VERSION",
    "ResearchDiscoveryDecision",
    "ResearchDiscoveryIntent",
    "evaluate_research_discovery",
]
