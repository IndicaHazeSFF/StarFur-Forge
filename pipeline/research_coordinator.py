"""Nonpublishing coordinator for one local cited-claim generation attempt.

This joins an exact source packet, local-only disclosure decision, prompt
envelope, injected provider, and strict claim parser.  It does not fetch,
route, retry, fall back, compose a user answer, or write any state.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol, runtime_checkable

from pipeline.research_claims import ResearchClaimSet, parse_research_claims
from pipeline.research_disclosure import (
    ResearchDisclosureDecision,
    ResearchProviderTarget,
)
from pipeline.research_prompt import build_research_claim_messages
from pipeline.research_sources import ResearchSourcePacket


RESEARCH_COORDINATOR_SCHEMA_VERSION = 1
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


@runtime_checkable
class ResearchClaimProvider(Protocol):
    """Minimal injected adapter; it grants no authority and owns no policy."""

    @property
    def available(self) -> bool: ...

    def propose_claims(
        self,
        messages: tuple[dict[str, str], dict[str, str]],
        *,
        model: str,
    ) -> str: ...


class ResearchCoordinatorError(RuntimeError):
    """Bounded operational failure without retaining provider output."""

    def __init__(self, reason: str) -> None:
        if reason not in {
            "disclosure_denied",
            "provider_unavailable",
            "provider_failed",
            "response_invalid",
        }:
            raise ValueError("research coordinator failure reason is invalid")
        super().__init__("research claim generation failed safely")
        self.reason = reason


@dataclass(frozen=True)
class ResearchCoordinationResult:
    schema_version: int
    packet_sha256: str
    target_sha256: str
    status: str
    claims: ResearchClaimSet

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_COORDINATOR_SCHEMA_VERSION:
            raise ValueError("research coordination schema version is unsupported")
        if self.status not in {"claims_proposed", "no_supported_claims"}:
            raise ValueError("research coordination status is invalid")
        if not isinstance(self.claims, ResearchClaimSet):
            raise TypeError("research coordination claims are invalid")
        if not isinstance(self.target_sha256, str) or not _DIGEST_RE.fullmatch(self.target_sha256):
            raise ValueError("research coordination target digest is invalid")
        if self.packet_sha256 != self.claims.packet_sha256:
            raise ValueError("research coordination packet binding is inconsistent")
        if self.status == "claims_proposed" and not self.claims.claims:
            raise ValueError("research coordination status requires claims")
        if self.status == "no_supported_claims" and self.claims.claims:
            raise ValueError("research coordination empty status cannot contain claims")


class ResearchClaimCoordinator:
    """Perform one bounded noncanonical claim-proposal attempt."""

    def __init__(self, provider: object) -> None:
        if not isinstance(provider, ResearchClaimProvider):
            raise TypeError("research claim provider is invalid")
        self._provider = provider

    def propose(
        self,
        packet: object,
        target: object,
        decision: object,
    ) -> ResearchCoordinationResult:
        if not isinstance(packet, ResearchSourcePacket):
            raise TypeError("research source packet is invalid")
        if not isinstance(target, ResearchProviderTarget):
            raise TypeError("research provider target is invalid")
        if not isinstance(decision, ResearchDisclosureDecision):
            raise TypeError("research disclosure decision is invalid")
        try:
            messages = build_research_claim_messages(packet, target, decision)
        except (TypeError, ValueError) as error:
            raise ResearchCoordinatorError("disclosure_denied") from error
        try:
            available = self._provider.available
        except Exception as error:
            raise ResearchCoordinatorError("provider_unavailable") from error
        if available is not True:
            raise ResearchCoordinatorError("provider_unavailable")
        try:
            raw = self._provider.propose_claims(messages, model=target.model)
        except Exception as error:
            raise ResearchCoordinatorError("provider_failed") from error
        try:
            claims = parse_research_claims(raw, packet)
        except (TypeError, ValueError) as error:
            raise ResearchCoordinatorError("response_invalid") from error
        status = "claims_proposed" if claims.claims else "no_supported_claims"
        return ResearchCoordinationResult(
            1,
            packet.packet_sha256,
            target.target_sha256,
            status,
            claims,
        )


__all__ = [
    "RESEARCH_COORDINATOR_SCHEMA_VERSION",
    "ResearchClaimCoordinator",
    "ResearchClaimProvider",
    "ResearchCoordinationResult",
    "ResearchCoordinatorError",
]
