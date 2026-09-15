"""Exact provider-free preflight for an authorized ``web.fetch`` launch.

The preflight joins the broker's content-free prerequisite commitments to
trusted Core-held destination and disclosure evidence. It performs no DNS,
socket, HTTP, parsing, storage, provider, grant, or approval work. Passing this
gate is not proof that a later connector used the approved address.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from pipeline.sandbox_supervisor import SupervisorLaunchRequest
from pipeline.tool_grants import RESOURCE_REF_RE
from pipeline.tool_web_disclosure import WebDisclosureIntent, evaluate_web_disclosure
from pipeline.tool_web_policy import (
    WebDestination,
    WebResolutionEvidence,
    evaluate_web_destination,
)


WEB_PREFLIGHT_SCHEMA_VERSION = 1
WEB_PREFLIGHT_REASONS = frozenset({
    "permitted",
    "launch_binding_invalid",
    "destination_binding_invalid",
    "destination_denied",
    "disclosure_binding_invalid",
    "disclosure_denied",
})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_digest(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _destination_digest(destination: WebDestination) -> str:
    return hashlib.sha256(destination.url.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WebDestinationPrerequisite:
    """Trusted Core-held evidence for one exact initial destination."""

    schema_version: int
    resource_ref: str
    destination: WebDestination
    resolution: WebResolutionEvidence

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_PREFLIGHT_SCHEMA_VERSION:
            raise ValueError("web destination prerequisite schema version is unsupported")
        if not isinstance(self.resource_ref, str) or not RESOURCE_REF_RE.fullmatch(self.resource_ref):
            raise ValueError("web destination prerequisite resource is invalid")
        if not isinstance(self.destination, WebDestination):
            raise TypeError("web destination prerequisite destination is invalid")
        if not isinstance(self.resolution, WebResolutionEvidence):
            raise TypeError("web destination prerequisite resolution is invalid")

    @property
    def evidence_sha256(self) -> str:
        return _canonical_digest({
            "schema_version": self.schema_version,
            "resource_ref": self.resource_ref,
            "url": self.destination.url,
            "host": self.resolution.host,
            "port": self.resolution.port,
            "addresses": list(self.resolution.addresses),
            "resolver_revision": self.resolution.resolver_revision,
            "observed_at_epoch": self.resolution.observed_at_epoch,
            "expires_at_epoch": self.resolution.expires_at_epoch,
        })


@dataclass(frozen=True)
class WebDisclosurePrerequisite:
    """Trusted classification of the exact URL bytes sent by the request."""

    schema_version: int
    resource_ref: str
    destination_sha256: str
    intent: WebDisclosureIntent

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_PREFLIGHT_SCHEMA_VERSION:
            raise ValueError("web disclosure prerequisite schema version is unsupported")
        if not isinstance(self.resource_ref, str) or not RESOURCE_REF_RE.fullmatch(self.resource_ref):
            raise ValueError("web disclosure prerequisite resource is invalid")
        if not isinstance(self.destination_sha256, str) or not _DIGEST_RE.fullmatch(
            self.destination_sha256
        ):
            raise ValueError("web disclosure prerequisite destination digest is invalid")
        if not isinstance(self.intent, WebDisclosureIntent):
            raise TypeError("web disclosure prerequisite intent is invalid")

    @property
    def evidence_sha256(self) -> str:
        return _canonical_digest({
            "schema_version": self.schema_version,
            "resource_ref": self.resource_ref,
            "destination_sha256": self.destination_sha256,
            "classification": self.intent.classification,
            "source_kind": self.intent.source_kind,
            "byte_count": self.intent.byte_count,
            "content_sha256": self.intent.content_sha256,
        })


@dataclass(frozen=True)
class WebFetchPreflightDecision:
    """Internal connector input; never tool authority or a public status view."""

    schema_version: int
    status: str
    reason: str
    approved_addresses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_PREFLIGHT_SCHEMA_VERSION:
            raise ValueError("web preflight decision schema version is unsupported")
        if self.status not in {"permitted", "denied"} or self.reason not in WEB_PREFLIGHT_REASONS:
            raise ValueError("web preflight decision is invalid")
        if (self.status == "permitted") != (self.reason == "permitted"):
            raise ValueError("web preflight status and reason disagree")
        addresses = tuple(self.approved_addresses)
        if self.status == "denied" and addresses:
            raise ValueError("denied web preflight cannot carry addresses")
        if self.status == "permitted" and not addresses:
            raise ValueError("permitted web preflight requires approved addresses")
        object.__setattr__(self, "approved_addresses", addresses)

    @property
    def permitted(self) -> bool:
        return self.status == "permitted"


def evaluate_web_fetch_preflight(
    launch: SupervisorLaunchRequest,
    destination: WebDestination,
    destination_prerequisite: WebDestinationPrerequisite,
    disclosure_prerequisite: WebDisclosurePrerequisite,
    *,
    now_epoch: float,
) -> WebFetchPreflightDecision:
    """Rejoin exact launch commitments and independently reevaluate policy."""
    if not isinstance(launch, SupervisorLaunchRequest):
        raise TypeError("web preflight launch is invalid")
    if not isinstance(destination, WebDestination):
        raise TypeError("web preflight destination is invalid")
    if not isinstance(destination_prerequisite, WebDestinationPrerequisite):
        raise TypeError("web preflight destination prerequisite is invalid")
    if not isinstance(disclosure_prerequisite, WebDisclosurePrerequisite):
        raise TypeError("web preflight disclosure prerequisite is invalid")

    def denied(reason: str) -> WebFetchPreflightDecision:
        return WebFetchPreflightDecision(1, "denied", reason)

    if (launch.tool_id, launch.tool_version) != ("web.fetch", 1):
        return denied("launch_binding_invalid")
    commitments = {item.requirement_id: item for item in launch.prerequisite_bindings}
    if set(commitments) != {"network.destination", "network.disclosure"}:
        return denied("launch_binding_invalid")
    destination_binding = commitments["network.destination"]
    if (
        destination_prerequisite.resource_ref != destination_binding.resource_ref
        or destination_prerequisite.evidence_sha256 != destination_binding.evidence_sha256
        or destination_prerequisite.destination != destination
    ):
        return denied("destination_binding_invalid")
    destination_decision = evaluate_web_destination(
        destination, destination_prerequisite.resolution, now_epoch=now_epoch,
    )
    if not destination_decision.permitted:
        return denied("destination_denied")

    disclosure_binding = commitments["network.disclosure"]
    url_bytes = destination.url.encode("utf-8")
    url_digest = _destination_digest(destination)
    intent = disclosure_prerequisite.intent
    if (
        disclosure_prerequisite.resource_ref != disclosure_binding.resource_ref
        or disclosure_prerequisite.evidence_sha256 != disclosure_binding.evidence_sha256
        or disclosure_prerequisite.destination_sha256 != url_digest
        or intent.byte_count != len(url_bytes)
        or intent.content_sha256 != url_digest
    ):
        return denied("disclosure_binding_invalid")
    disclosure_decision = evaluate_web_disclosure(intent)
    if not disclosure_decision.permitted:
        return denied("disclosure_denied")
    return WebFetchPreflightDecision(
        1, "permitted", "permitted", destination_decision.approved_addresses,
    )


__all__ = [
    "WEB_PREFLIGHT_REASONS",
    "WEB_PREFLIGHT_SCHEMA_VERSION",
    "WebDestinationPrerequisite",
    "WebDisclosurePrerequisite",
    "WebFetchPreflightDecision",
    "evaluate_web_fetch_preflight",
]
