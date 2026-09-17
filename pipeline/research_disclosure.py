"""Pure disclosure policy for future research-source synthesis.

The first policy permits only already-public source packets to one explicitly
named local provider target.  Hosted-provider disclosure remains unsupported.
A decision is not provider availability, tool authority, or permission to
publish or persist a result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from pipeline.research_sources import ResearchSourcePacket


RESEARCH_DISCLOSURE_SCHEMA_VERSION = 1
RESEARCH_DISCLOSURE_POLICY_REVISION = "research-public-local-v1"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,255}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _model(value: object) -> str:
    if not isinstance(value, str) or not _MODEL_RE.fullmatch(value):
        raise ValueError("research provider model is invalid")
    return value


def _target_fingerprint(provider_id: str, model: str, deployment: str) -> str:
    encoded = json.dumps(
        {"deployment": deployment, "model": model, "provider_id": provider_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ResearchProviderTarget:
    schema_version: int
    provider_id: str
    model: str
    deployment: str
    target_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_DISCLOSURE_SCHEMA_VERSION:
            raise ValueError("research provider target schema version is unsupported")
        provider_id = _identifier(self.provider_id, "research provider ID")
        model = _model(self.model)
        if self.deployment not in {"local", "hosted"}:
            raise ValueError("research provider deployment is unsupported")
        expected = _target_fingerprint(provider_id, model, self.deployment)
        if not isinstance(self.target_sha256, str) or self.target_sha256 != expected:
            raise ValueError("research provider target digest is inconsistent")

    @classmethod
    def create(cls, provider_id: object, model: object, deployment: object):
        checked_provider = _identifier(provider_id, "research provider ID")
        checked_model = _model(model)
        if deployment not in {"local", "hosted"}:
            raise ValueError("research provider deployment is unsupported")
        return cls(
            1,
            checked_provider,
            checked_model,
            deployment,
            _target_fingerprint(checked_provider, checked_model, deployment),
        )


@dataclass(frozen=True)
class ResearchDisclosureIntent:
    schema_version: int
    packet_sha256: str
    source_count: int
    source_character_count: int
    data_classification: str
    purpose: str
    target: ResearchProviderTarget
    policy_revision: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_DISCLOSURE_SCHEMA_VERSION:
            raise ValueError("research disclosure schema version is unsupported")
        if not isinstance(self.packet_sha256, str) or not _DIGEST_RE.fullmatch(self.packet_sha256):
            raise ValueError("research disclosure packet digest is invalid")
        if (
            isinstance(self.source_count, bool)
            or not isinstance(self.source_count, int)
            or not 1 <= self.source_count <= 8
        ):
            raise ValueError("research disclosure source count is invalid")
        if (
            isinstance(self.source_character_count, bool)
            or not isinstance(self.source_character_count, int)
            or not 1 <= self.source_character_count <= 64_000
        ):
            raise ValueError("research disclosure character count is invalid")
        if self.data_classification != "public":
            raise ValueError("research disclosure classification is unsupported")
        if self.purpose != "factual_research":
            raise ValueError("research disclosure purpose is unsupported")
        if not isinstance(self.target, ResearchProviderTarget):
            raise TypeError("research disclosure target is invalid")
        if self.policy_revision != RESEARCH_DISCLOSURE_POLICY_REVISION:
            raise ValueError("research disclosure policy revision is unsupported")

    @classmethod
    def from_packet(cls, packet: object, target: object):
        if not isinstance(packet, ResearchSourcePacket):
            raise TypeError("research source packet is invalid")
        if not isinstance(target, ResearchProviderTarget):
            raise TypeError("research provider target is invalid")
        return cls(
            1,
            packet.packet_sha256,
            len(packet.sources),
            packet.source_character_count,
            "public",
            "factual_research",
            target,
            RESEARCH_DISCLOSURE_POLICY_REVISION,
        )


@dataclass(frozen=True)
class ResearchDisclosureDecision:
    schema_version: int
    status: str
    reason: str
    packet_sha256: str
    target_sha256: str
    policy_revision: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_DISCLOSURE_SCHEMA_VERSION:
            raise ValueError("research disclosure decision schema is unsupported")
        if self.status not in {"permitted", "denied"}:
            raise ValueError("research disclosure decision status is invalid")
        if self.reason not in {
            "permitted_public_local",
            "packet_binding_mismatch",
            "intent_mismatch",
            "hosted_disclosure_unsupported",
        }:
            raise ValueError("research disclosure decision reason is invalid")
        for label, value in (
            ("packet", self.packet_sha256), ("target", self.target_sha256),
        ):
            if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
                raise ValueError(f"research disclosure decision {label} digest is invalid")
        if self.policy_revision != RESEARCH_DISCLOSURE_POLICY_REVISION:
            raise ValueError("research disclosure decision policy revision is unsupported")


def evaluate_research_disclosure(
    intent: object,
    packet: object,
) -> ResearchDisclosureDecision:
    """Permit exact public data to an explicit local target only."""
    if not isinstance(intent, ResearchDisclosureIntent):
        raise TypeError("research disclosure intent is invalid")
    if not isinstance(packet, ResearchSourcePacket):
        raise TypeError("research source packet is invalid")

    def decision(status: str, reason: str) -> ResearchDisclosureDecision:
        return ResearchDisclosureDecision(
            1,
            status,
            reason,
            intent.packet_sha256,
            intent.target.target_sha256,
            intent.policy_revision,
        )

    if intent.packet_sha256 != packet.packet_sha256:
        return decision("denied", "packet_binding_mismatch")
    if (
        intent.source_count != len(packet.sources)
        or intent.source_character_count != packet.source_character_count
        or intent.data_classification != "public"
        or intent.purpose != "factual_research"
    ):
        return decision("denied", "intent_mismatch")
    if intent.target.deployment != "local":
        return decision("denied", "hosted_disclosure_unsupported")
    return decision("permitted", "permitted_public_local")


__all__ = [
    "RESEARCH_DISCLOSURE_POLICY_REVISION",
    "RESEARCH_DISCLOSURE_SCHEMA_VERSION",
    "ResearchDisclosureDecision",
    "ResearchDisclosureIntent",
    "ResearchProviderTarget",
    "evaluate_research_disclosure",
]
