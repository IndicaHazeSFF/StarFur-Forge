"""Exact provider-free preflight for a future authorized ``web.search`` launch.

The gate rejoins a broker launch with one Core-configured search service and the
content-free research-discovery disclosure decision.  It performs no search,
network, provider, DNS, storage, approval, grant, or prerequisite issuance.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

from pipeline.research_discovery import (
    ResearchDiscoveryDecision,
    ResearchDiscoveryIntent,
)
from pipeline.sandbox_supervisor import SupervisorLaunchRequest
from pipeline.tool_contracts import ToolProposal, validate_web_search_arguments
from pipeline.tool_grants import RESOURCE_REF_RE
from pipeline.tool_web_search import MAX_WEB_SEARCH_RESULTS


WEB_SEARCH_PREFLIGHT_SCHEMA_VERSION = 1
WEB_SEARCH_PREFLIGHT_POLICY_REVISION = "web-search-preflight-v1"
MAX_WEB_SEARCH_SERVICE_EVIDENCE_SECONDS = 300.0
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_REASONS = frozenset({
    "permitted",
    "launch_binding_invalid",
    "query_binding_invalid",
    "service_binding_invalid",
    "service_unavailable",
    "service_evidence_stale",
    "disclosure_binding_invalid",
    "disclosure_denied",
})


def _canonical_digest(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _epoch(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} is invalid")
    result = float(value)
    if not math.isfinite(result) or not 0 <= result < 1e12:
        raise ValueError(f"{label} is invalid")
    return result


@dataclass(frozen=True)
class WebSearchServicePrerequisite:
    schema_version: int
    resource_ref: str
    service_id: str
    deployment: str
    maximum_results: int
    available: bool
    observed_at_epoch: float
    expires_at_epoch: float
    policy_revision: str

    def __post_init__(self) -> None:
        if self.schema_version != WEB_SEARCH_PREFLIGHT_SCHEMA_VERSION:
            raise ValueError("web search service schema version is unsupported")
        if not isinstance(self.resource_ref, str) or not RESOURCE_REF_RE.fullmatch(self.resource_ref):
            raise ValueError("web search service resource is invalid")
        if not isinstance(self.service_id, str) or not _SERVICE_RE.fullmatch(self.service_id):
            raise ValueError("web search service ID is invalid")
        if self.deployment not in {"local", "hosted"}:
            raise ValueError("web search service deployment is invalid")
        if (
            isinstance(self.maximum_results, bool)
            or not isinstance(self.maximum_results, int)
            or not 1 <= self.maximum_results <= MAX_WEB_SEARCH_RESULTS
        ):
            raise ValueError("web search service result limit is invalid")
        if not isinstance(self.available, bool):
            raise TypeError("web search service availability is invalid")
        observed = _epoch(self.observed_at_epoch, "web search service observation time")
        expires = _epoch(self.expires_at_epoch, "web search service expiry time")
        if not observed < expires or expires - observed > MAX_WEB_SEARCH_SERVICE_EVIDENCE_SECONDS:
            raise ValueError("web search service evidence lifetime is invalid")
        if self.policy_revision != WEB_SEARCH_PREFLIGHT_POLICY_REVISION:
            raise ValueError("web search service policy is unsupported")
        object.__setattr__(self, "observed_at_epoch", observed)
        object.__setattr__(self, "expires_at_epoch", expires)

    @property
    def evidence_sha256(self) -> str:
        return _canonical_digest({
            "schema_version": self.schema_version,
            "resource_ref": self.resource_ref,
            "service_id": self.service_id,
            "deployment": self.deployment,
            "maximum_results": self.maximum_results,
            "available": self.available,
            "observed_at_epoch": self.observed_at_epoch,
            "expires_at_epoch": self.expires_at_epoch,
            "policy_revision": self.policy_revision,
        })


@dataclass(frozen=True)
class WebSearchDisclosurePrerequisite:
    schema_version: int
    resource_ref: str
    intent: ResearchDiscoveryIntent
    decision: ResearchDiscoveryDecision

    def __post_init__(self) -> None:
        if self.schema_version != WEB_SEARCH_PREFLIGHT_SCHEMA_VERSION:
            raise ValueError("web search disclosure schema version is unsupported")
        if not isinstance(self.resource_ref, str) or not RESOURCE_REF_RE.fullmatch(self.resource_ref):
            raise ValueError("web search disclosure resource is invalid")
        if not isinstance(self.intent, ResearchDiscoveryIntent):
            raise TypeError("web search disclosure intent is invalid")
        if not isinstance(self.decision, ResearchDiscoveryDecision):
            raise TypeError("web search disclosure decision is invalid")
        if (
            self.intent.target_kind != "public_web_search"
            or self.intent.data_classification != "public"
            or self.decision.status != "confirmation_required"
            or self.decision.reason != "public_search_requires_broker_confirmation"
            or self.decision.query_sha256 != self.intent.query_sha256
            or self.decision.target_kind != self.intent.target_kind
            or self.decision.policy_revision != self.intent.policy_revision
        ):
            raise ValueError("web search disclosure evidence is inconsistent")

    @property
    def evidence_sha256(self) -> str:
        return _canonical_digest({
            "schema_version": self.schema_version,
            "resource_ref": self.resource_ref,
            "query_sha256": self.intent.query_sha256,
            "query_byte_count": self.intent.query_byte_count,
            "trigger_reason": self.intent.trigger_reason,
            "target_kind": self.intent.target_kind,
            "classification": self.intent.data_classification,
            "decision_status": self.decision.status,
            "decision_reason": self.decision.reason,
            "policy_revision": self.intent.policy_revision,
        })


@dataclass(frozen=True)
class WebSearchPreflightDecision:
    schema_version: int
    status: str
    reason: str
    service_id: str | None = None
    maximum_results: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != WEB_SEARCH_PREFLIGHT_SCHEMA_VERSION:
            raise ValueError("web search preflight schema version is unsupported")
        if self.status not in {"permitted", "denied"} or self.reason not in _REASONS:
            raise ValueError("web search preflight decision is invalid")
        if (self.status == "permitted") != (self.reason == "permitted"):
            raise ValueError("web search preflight decision is inconsistent")
        if self.status == "permitted":
            if not isinstance(self.service_id, str) or not _SERVICE_RE.fullmatch(self.service_id):
                raise ValueError("permitted web search preflight service is invalid")
            if not 1 <= self.maximum_results <= MAX_WEB_SEARCH_RESULTS:
                raise ValueError("permitted web search preflight result limit is invalid")
        elif self.service_id is not None or self.maximum_results != 0:
            raise ValueError("denied web search preflight cannot expose service data")

    @property
    def permitted(self) -> bool:
        return self.status == "permitted"


def evaluate_web_search_preflight(
    launch: object,
    proposal: object,
    service: object,
    disclosure: object,
    *,
    now_epoch: object,
) -> WebSearchPreflightDecision:
    """Recheck exact launch/query/service/disclosure bindings without I/O."""
    if not isinstance(launch, SupervisorLaunchRequest):
        raise TypeError("web search preflight launch is invalid")
    if not isinstance(proposal, ToolProposal):
        raise TypeError("web search preflight proposal is invalid")
    if not isinstance(service, WebSearchServicePrerequisite):
        raise TypeError("web search service prerequisite is invalid")
    if not isinstance(disclosure, WebSearchDisclosurePrerequisite):
        raise TypeError("web search disclosure prerequisite is invalid")
    now = _epoch(now_epoch, "web search preflight time")

    def denied(reason: str) -> WebSearchPreflightDecision:
        return WebSearchPreflightDecision(1, "denied", reason)

    if (launch.tool_id, launch.tool_version) != ("web.search", 1):
        return denied("launch_binding_invalid")
    commitments = {item.requirement_id: item for item in launch.prerequisite_bindings}
    if set(commitments) != {"network.search", "network.disclosure"}:
        return denied("launch_binding_invalid")
    if proposal.tool_id != "web.search" or proposal.tool_version != 1:
        return denied("query_binding_invalid")
    try:
        arguments = validate_web_search_arguments(proposal.arguments)
    except (TypeError, ValueError):
        return denied("query_binding_invalid")
    query = arguments["query"]
    query_sha256 = hashlib.sha256(query.encode("utf-8")).hexdigest()
    if (
        query_sha256 != disclosure.intent.query_sha256
        or len(query.encode("utf-8")) != disclosure.intent.query_byte_count
    ):
        return denied("query_binding_invalid")

    search_binding = commitments["network.search"]
    if (
        service.resource_ref != search_binding.resource_ref
        or service.evidence_sha256 != search_binding.evidence_sha256
    ):
        return denied("service_binding_invalid")
    if not service.available:
        return denied("service_unavailable")
    if now < service.observed_at_epoch or now >= service.expires_at_epoch:
        return denied("service_evidence_stale")

    disclosure_binding = commitments["network.disclosure"]
    if (
        disclosure.resource_ref != disclosure_binding.resource_ref
        or disclosure.evidence_sha256 != disclosure_binding.evidence_sha256
    ):
        return denied("disclosure_binding_invalid")
    if disclosure.decision.status != "confirmation_required":
        return denied("disclosure_denied")
    return WebSearchPreflightDecision(
        1, "permitted", "permitted", service.service_id, service.maximum_results,
    )


__all__ = [
    "MAX_WEB_SEARCH_SERVICE_EVIDENCE_SECONDS",
    "WEB_SEARCH_PREFLIGHT_POLICY_REVISION",
    "WEB_SEARCH_PREFLIGHT_SCHEMA_VERSION",
    "WebSearchDisclosurePrerequisite",
    "WebSearchPreflightDecision",
    "WebSearchServicePrerequisite",
    "evaluate_web_search_preflight",
]
