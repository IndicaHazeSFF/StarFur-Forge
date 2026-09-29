"""Strict untrusted relationship proposals between reviewed research claims.

This provider-free contract can validate a future evaluator's pairwise claim
classification against one exact session-local review.  A valid relationship
is still only an untrusted proposal: it does not establish corroboration,
conflict, truth, source independence, answer eligibility, or authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re

from pipeline.research_review import ResearchReviewRecord


RESEARCH_RELATIONSHIP_SCHEMA_VERSION = 1
MAX_RESEARCH_RELATIONSHIPS = 24
MAX_RESEARCH_RELATIONSHIP_OUTPUT_BYTES = 24_000

_RELATIONS = {
    "possibly_supports_same_proposition",
    "possibly_conflicts",
    "related_only",
    "insufficient_basis",
}
_REVIEW_ID_RE = re.compile(r"^RR-[0-9a-f]{24}$")
_CLAIM_ID_RE = re.compile(r"^RC-[0-9]{3}$")
_RELATIONSHIP_ID_RE = re.compile(r"^RL-[0-9]{3}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SINGLE_JSON_FENCE_RE = re.compile(
    r"\A[ \t\r\n]*```json[ \t]*\r?\n(?P<body>.*)\r?\n```[ \t\r\n]*\Z",
    re.IGNORECASE | re.DOTALL,
)


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("research relationship output contains duplicate JSON keys")
        value[key] = item
    return value


def _strict_json_candidate(raw: str) -> str:
    if raw.lstrip().startswith("{"):
        return raw
    match = _SINGLE_JSON_FENCE_RE.fullmatch(raw)
    if match is None:
        raise ValueError("research relationship output is not strict JSON")
    body = match.group("body")
    if not body.strip() or not body.lstrip().startswith("{"):
        raise ValueError("research relationship fence does not contain a JSON object")
    return body


@dataclass(frozen=True)
class ResearchClaimRelationship:
    """One pairwise relationship proposal, never a verification decision."""

    schema_version: int
    relationship_id: str
    left_claim_id: str
    right_claim_id: str
    relation: str
    confidence: float

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_RELATIONSHIP_SCHEMA_VERSION:
            raise ValueError("research relationship schema version is unsupported")
        if not isinstance(self.relationship_id, str) or not _RELATIONSHIP_ID_RE.fullmatch(self.relationship_id):
            raise ValueError("research relationship ID is invalid")
        if not isinstance(self.left_claim_id, str) or not _CLAIM_ID_RE.fullmatch(self.left_claim_id):
            raise ValueError("research relationship left claim ID is invalid")
        if not isinstance(self.right_claim_id, str) or not _CLAIM_ID_RE.fullmatch(self.right_claim_id):
            raise ValueError("research relationship right claim ID is invalid")
        if self.left_claim_id >= self.right_claim_id:
            raise ValueError("research relationship claim pair must be canonical and distinct")
        if self.relation not in _RELATIONS:
            raise ValueError("research relationship kind is invalid")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(float(self.confidence))
            or not 0 <= float(self.confidence) <= 1
        ):
            raise ValueError("research relationship confidence is invalid")
        object.__setattr__(self, "confidence", float(self.confidence))


@dataclass(frozen=True)
class ResearchClaimRelationshipSet:
    """Untrusted relationship proposals bound to one exact review."""

    schema_version: int
    review_id: str
    packet_sha256: str
    relationships: tuple[ResearchClaimRelationship, ...]

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_RELATIONSHIP_SCHEMA_VERSION:
            raise ValueError("research relationship-set schema version is unsupported")
        if not isinstance(self.review_id, str) or not _REVIEW_ID_RE.fullmatch(self.review_id):
            raise ValueError("research relationship-set review ID is invalid")
        if not isinstance(self.packet_sha256, str) or not _DIGEST_RE.fullmatch(self.packet_sha256):
            raise ValueError("research relationship-set packet digest is invalid")
        relationships = tuple(self.relationships)
        if len(relationships) > MAX_RESEARCH_RELATIONSHIPS:
            raise ValueError("research relationship count exceeds its limit")
        if any(not isinstance(item, ResearchClaimRelationship) for item in relationships):
            raise TypeError("research relationship-set item is invalid")
        if len({item.relationship_id for item in relationships}) != len(relationships):
            raise ValueError("research relationship IDs must be unique")
        pairs = {(item.left_claim_id, item.right_claim_id) for item in relationships}
        if len(pairs) != len(relationships):
            raise ValueError("research relationship claim pairs must be unique")
        object.__setattr__(self, "relationships", relationships)


def parse_research_claim_relationships(
    raw: object,
    review: object,
) -> ResearchClaimRelationshipSet:
    """Validate untrusted pairwise proposals against one exact review."""
    if not isinstance(review, ResearchReviewRecord):
        raise TypeError("research relationship review is invalid")
    if not isinstance(raw, str):
        raise TypeError("research relationship output must be text")
    try:
        encoded = raw.encode("utf-8")
    except UnicodeError as error:
        raise ValueError("research relationship output encoding is invalid") from error
    if not encoded or len(encoded) > MAX_RESEARCH_RELATIONSHIP_OUTPUT_BYTES:
        raise ValueError("research relationship output size is invalid")
    try:
        value = json.loads(_strict_json_candidate(raw), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("research relationship output is not strict JSON") from error
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "review_id", "packet_sha256", "relationships",
    }:
        raise ValueError("research relationship envelope fields are invalid")
    if value["review_id"] != review.review_id or value["packet_sha256"] != review.packet_sha256:
        raise ValueError("research relationship review binding is stale or mismatched")
    raw_relationships = value["relationships"]
    if not isinstance(raw_relationships, list) or len(raw_relationships) > MAX_RESEARCH_RELATIONSHIPS:
        raise ValueError("research relationships must be a bounded array")
    allowed_claims = {claim.claim_id for claim in review.result.claims.claims}
    relationships = []
    seen_pairs = set()
    for index, item in enumerate(raw_relationships, start=1):
        if not isinstance(item, dict) or set(item) != {
            "relationship_id", "left_claim_id", "right_claim_id", "relation", "confidence",
        }:
            raise ValueError("research relationship fields are invalid")
        if item["relationship_id"] != f"RL-{index:03d}":
            raise ValueError("research relationship IDs must be ordered")
        relationship = ResearchClaimRelationship(
            RESEARCH_RELATIONSHIP_SCHEMA_VERSION,
            item["relationship_id"],
            item["left_claim_id"],
            item["right_claim_id"],
            item["relation"],
            item["confidence"],
        )
        if (
            relationship.left_claim_id not in allowed_claims
            or relationship.right_claim_id not in allowed_claims
        ):
            raise ValueError("research relationship references a claim outside its review")
        pair = (relationship.left_claim_id, relationship.right_claim_id)
        if pair in seen_pairs:
            raise ValueError("research relationship claim pairs must be unique")
        seen_pairs.add(pair)
        relationships.append(relationship)
    return ResearchClaimRelationshipSet(
        RESEARCH_RELATIONSHIP_SCHEMA_VERSION,
        review.review_id,
        review.packet_sha256,
        tuple(relationships),
    )


def research_claim_relationship_json_schema(review: object) -> dict[str, object]:
    """Return an exact structured-output schema for one review.

    Provider schema conformance is not verification. The returned output must
    still pass :func:`parse_research_claim_relationships` in full.
    """
    if not isinstance(review, ResearchReviewRecord):
        raise TypeError("research relationship review is invalid")
    claim_ids = [claim.claim_id for claim in review.result.claims.claims]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "review_id", "packet_sha256", "relationships"],
        "properties": {
            "schema_version": {"type": "integer", "const": RESEARCH_RELATIONSHIP_SCHEMA_VERSION},
            "review_id": {"type": "string", "const": review.review_id},
            "packet_sha256": {"type": "string", "const": review.packet_sha256},
            "relationships": {
                "type": "array",
                "maxItems": MAX_RESEARCH_RELATIONSHIPS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "relationship_id", "left_claim_id", "right_claim_id", "relation", "confidence",
                    ],
                    "properties": {
                        "relationship_id": {"type": "string", "pattern": r"^RL-[0-9]{3}$"},
                        "left_claim_id": {"type": "string", "enum": claim_ids},
                        "right_claim_id": {"type": "string", "enum": claim_ids},
                        "relation": {"type": "string", "enum": sorted(_RELATIONS)},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
        },
    }


__all__ = [
    "MAX_RESEARCH_RELATIONSHIPS",
    "MAX_RESEARCH_RELATIONSHIP_OUTPUT_BYTES",
    "RESEARCH_RELATIONSHIP_SCHEMA_VERSION",
    "ResearchClaimRelationship",
    "ResearchClaimRelationshipSet",
    "parse_research_claim_relationships",
    "research_claim_relationship_json_schema",
]
