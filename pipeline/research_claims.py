"""Strict cited-claim proposals for future research synthesis.

Provider output may propose claims against one exact source packet.  Parsing and
citation validation do not prove a claim true and cannot publish an answer,
approve memory, or grant any authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re

from pipeline.research_sources import ResearchSourcePacket


RESEARCH_CLAIM_SCHEMA_VERSION = 1
MAX_RESEARCH_CLAIMS = 16
MAX_RESEARCH_CLAIM_CHARACTERS = 1_000
MAX_RESEARCH_CLAIM_OUTPUT_BYTES = 32_000
_SOURCE_ID_RE = re.compile(r"^RS-[0-9a-f]{24}$")


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("research claim output contains duplicate JSON keys")
        result[key] = value
    return result


@dataclass(frozen=True)
class ResearchClaim:
    """One untrusted claim proposal with exact packet-local citations."""

    schema_version: int
    claim_id: str
    statement: str
    source_ids: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_CLAIM_SCHEMA_VERSION:
            raise ValueError("research claim schema version is unsupported")
        if not isinstance(self.claim_id, str) or not re.fullmatch(r"RC-[0-9]{3}", self.claim_id):
            raise ValueError("research claim ID is invalid")
        if (
            not isinstance(self.statement, str)
            or not self.statement.strip()
            or self.statement != " ".join(self.statement.split())
            or len(self.statement) > MAX_RESEARCH_CLAIM_CHARACTERS
        ):
            raise ValueError("research claim statement is invalid")
        source_ids = tuple(self.source_ids)
        if (
            not source_ids
            or len(source_ids) > 4
            or len(set(source_ids)) != len(source_ids)
            or any(not isinstance(value, str) or not _SOURCE_ID_RE.fullmatch(value) for value in source_ids)
        ):
            raise ValueError("research claim citations are invalid")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(float(self.confidence))
            or not 0 <= float(self.confidence) <= 1
        ):
            raise ValueError("research claim confidence is invalid")
        object.__setattr__(self, "source_ids", source_ids)
        object.__setattr__(self, "confidence", float(self.confidence))


@dataclass(frozen=True)
class ResearchClaimSet:
    schema_version: int
    packet_sha256: str
    claims: tuple[ResearchClaim, ...]

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_CLAIM_SCHEMA_VERSION:
            raise ValueError("research claim-set schema version is unsupported")
        if not isinstance(self.packet_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.packet_sha256):
            raise ValueError("research claim-set packet digest is invalid")
        claims = tuple(self.claims)
        if len(claims) > MAX_RESEARCH_CLAIMS:
            raise ValueError("research claim count exceeds its limit")
        if any(not isinstance(item, ResearchClaim) for item in claims):
            raise TypeError("research claim-set item is invalid")
        if len({item.claim_id for item in claims}) != len(claims):
            raise ValueError("research claim IDs must be unique")
        object.__setattr__(self, "claims", claims)


def parse_research_claims(raw: object, packet: object) -> ResearchClaimSet:
    """Validate untrusted JSON output against one exact source packet."""
    if not isinstance(packet, ResearchSourcePacket):
        raise TypeError("research source packet is invalid")
    if not isinstance(raw, str):
        raise TypeError("research claim output must be text")
    encoded = raw.encode("utf-8")
    if not encoded or len(encoded) > MAX_RESEARCH_CLAIM_OUTPUT_BYTES:
        raise ValueError("research claim output size is invalid")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("research claim output is not strict JSON") from error
    if not isinstance(value, dict) or set(value) != {"schema_version", "packet_sha256", "claims"}:
        raise ValueError("research claim envelope fields are invalid")
    if value["packet_sha256"] != packet.packet_sha256:
        raise ValueError("research claim packet binding is stale or mismatched")
    raw_claims = value["claims"]
    if not isinstance(raw_claims, list) or len(raw_claims) > MAX_RESEARCH_CLAIMS:
        raise ValueError("research claims must be a bounded array")
    allowed_sources = set(packet.source_ids())
    claims = []
    for index, item in enumerate(raw_claims, start=1):
        if not isinstance(item, dict) or set(item) != {
            "claim_id", "statement", "source_ids", "confidence",
        }:
            raise ValueError("research claim fields are invalid")
        if item["claim_id"] != f"RC-{index:03d}":
            raise ValueError("research claim IDs must be ordered")
        if not isinstance(item["source_ids"], list):
            raise TypeError("research claim citations must be an array")
        claim = ResearchClaim(
            1,
            item["claim_id"],
            item["statement"],
            tuple(item["source_ids"]),
            item["confidence"],
        )
        if any(source_id not in allowed_sources for source_id in claim.source_ids):
            raise ValueError("research claim cites a source outside its packet")
        claims.append(claim)
    return ResearchClaimSet(1, packet.packet_sha256, tuple(claims))


__all__ = [
    "MAX_RESEARCH_CLAIMS",
    "MAX_RESEARCH_CLAIM_CHARACTERS",
    "MAX_RESEARCH_CLAIM_OUTPUT_BYTES",
    "RESEARCH_CLAIM_SCHEMA_VERSION",
    "ResearchClaim",
    "ResearchClaimSet",
    "parse_research_claims",
]
