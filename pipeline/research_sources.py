"""Bounded source-data frames for future factual research.

This module can translate an already quarantined public-web artifact into a
provider-neutral evidence packet.  It does not fetch, select a provider, send a
prompt, assess truth, create citations, or write memory.  Source prose remains
untrusted data even when it appears inside a valid packet.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

from pipeline.tool_contracts import ARTIFACT_REF_RE
from pipeline.tool_web_connector import WebFetchedArtifact
from pipeline.tool_web_parser import WEB_EXTERNAL_TRUST_LABEL
from pipeline.tool_web_response import ALLOWED_WEB_MEDIA_TYPES


RESEARCH_SOURCE_SCHEMA_VERSION = 1
RESEARCH_PACKET_SCHEMA_VERSION = 1
MAX_RESEARCH_QUESTION_CHARACTERS = 2_000
MAX_RESEARCH_SOURCES = 8
MAX_RESEARCH_SOURCE_CHARACTERS = 32_000
MAX_RESEARCH_PACKET_CHARACTERS = 64_000
RESEARCH_SOURCE_KIND = "public_web"
RESEARCH_TRUST_LABEL = "untrusted_external"
RESEARCH_HANDLING = "source_data_only"

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ID_RE = re.compile(r"^RS-[0-9a-f]{24}$")


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _normalized_question(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("research question must be text")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("research question is empty")
    if len(normalized) > MAX_RESEARCH_QUESTION_CHARACTERS:
        raise ValueError("research question exceeds its character limit")
    return normalized


def research_question_metadata(question: object) -> tuple[str, str, int]:
    """Return canonical question text plus bounded, non-content metadata.

    Callers that retain only the digest and byte count can later prove that a
    supplied question matches a research packet without retaining its text.
    This is a binding helper, not disclosure consent or answer authority.
    """
    normalized = _normalized_question(question)
    try:
        encoded = normalized.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("research question is not valid UTF-8") from error
    return normalized, hashlib.sha256(encoded).hexdigest(), len(encoded)


def _packet_digest(question: str, sources: tuple["ResearchSource", ...]) -> str:
    encoded = json.dumps(
        {
            "question": question,
            "sources": [
                {
                    "source_id": item.source_id,
                    "artifact_ref": item.artifact_ref,
                    "url": item.url,
                    "media_type": item.media_type,
                    "source_media_type": item.source_media_type,
                    "fetched_at_epoch": item.fetched_at_epoch,
                    "content_sha256": item.content_sha256,
                    "text": item.text,
                }
                for item in sources
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ResearchSource:
    """One bounded public source, still explicitly untrusted."""

    schema_version: int
    source_id: str
    artifact_ref: str
    source_kind: str
    trust_label: str
    handling: str
    url: str
    media_type: str
    fetched_at_epoch: float
    content_sha256: str
    text: str
    character_count: int
    source_media_type: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_SOURCE_SCHEMA_VERSION:
            raise ValueError("research source schema version is unsupported")
        if not isinstance(self.source_id, str) or not _SOURCE_ID_RE.fullmatch(self.source_id):
            raise ValueError("research source ID is invalid")
        if not isinstance(self.artifact_ref, str) or not ARTIFACT_REF_RE.fullmatch(self.artifact_ref):
            raise ValueError("research source artifact reference is invalid")
        if self.source_kind != RESEARCH_SOURCE_KIND:
            raise ValueError("research source kind is unsupported")
        if self.trust_label != RESEARCH_TRUST_LABEL or self.handling != RESEARCH_HANDLING:
            raise ValueError("research source trust boundary is invalid")
        if not isinstance(self.url, str) or not self.url.startswith("https://"):
            raise ValueError("research source URL is invalid")
        if self.media_type not in {"text/plain", "text/markdown"}:
            raise ValueError("research source media type is unsupported")
        source_media_type = self.media_type if self.source_media_type is None else self.source_media_type
        if source_media_type not in ALLOWED_WEB_MEDIA_TYPES:
            raise ValueError("research source media provenance is unsupported")
        if (
            isinstance(self.fetched_at_epoch, bool)
            or not isinstance(self.fetched_at_epoch, (int, float))
            or not math.isfinite(float(self.fetched_at_epoch))
            or not 0 <= float(self.fetched_at_epoch) < 1e12
        ):
            raise ValueError("research source timestamp is invalid")
        object.__setattr__(self, "fetched_at_epoch", float(self.fetched_at_epoch))
        _digest(self.content_sha256, "research source digest")
        if not isinstance(self.text, str) or not self.text:
            raise ValueError("research source text is empty")
        if (
            isinstance(self.character_count, bool)
            or not isinstance(self.character_count, int)
            or self.character_count != len(self.text)
            or self.character_count > MAX_RESEARCH_SOURCE_CHARACTERS
        ):
            raise ValueError("research source character count is invalid")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.content_sha256:
            raise ValueError("research source digest is inconsistent")
        object.__setattr__(self, "source_media_type", source_media_type)

    def public_dict(self) -> dict[str, object]:
        """Return explicit source data; callers must authorize any disclosure."""
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "trust_label": self.trust_label,
            "handling": self.handling,
            "url": self.url,
            "media_type": self.media_type,
            "source_media_type": self.source_media_type,
            "fetched_at_epoch": self.fetched_at_epoch,
            "content_sha256": self.content_sha256,
            "character_count": self.character_count,
            "text": self.text,
        }


@dataclass(frozen=True)
class ResearchSourcePacket:
    """One question plus bounded source data, without a truth conclusion."""

    schema_version: int
    question: str
    trust_label: str
    handling: str
    sources: tuple[ResearchSource, ...]
    source_character_count: int
    packet_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != RESEARCH_PACKET_SCHEMA_VERSION:
            raise ValueError("research packet schema version is unsupported")
        question = _normalized_question(self.question)
        if question != self.question:
            raise ValueError("research packet question is not canonical")
        if self.trust_label != RESEARCH_TRUST_LABEL or self.handling != RESEARCH_HANDLING:
            raise ValueError("research packet trust boundary is invalid")
        sources = tuple(self.sources)
        if not sources or len(sources) > MAX_RESEARCH_SOURCES:
            raise ValueError("research packet source count is invalid")
        if any(not isinstance(item, ResearchSource) for item in sources):
            raise TypeError("research packet source is invalid")
        if len({item.source_id for item in sources}) != len(sources):
            raise ValueError("research packet source IDs must be unique")
        if len({item.artifact_ref for item in sources}) != len(sources):
            raise ValueError("research packet artifact references must be unique")
        total = sum(item.character_count for item in sources)
        if (
            isinstance(self.source_character_count, bool)
            or not isinstance(self.source_character_count, int)
            or self.source_character_count != total
            or total > MAX_RESEARCH_PACKET_CHARACTERS
        ):
            raise ValueError("research packet character count is invalid")
        expected = _packet_digest(question, sources)
        if _digest(self.packet_sha256, "research packet digest") != expected:
            raise ValueError("research packet digest is inconsistent")
        object.__setattr__(self, "sources", sources)

    def source_ids(self) -> tuple[str, ...]:
        return tuple(item.source_id for item in self.sources)

    def source_data_dict(self) -> dict[str, object]:
        """Serialize only for a later independently authorized consumer."""
        return {
            "schema_version": self.schema_version,
            "question": self.question,
            "trust_label": self.trust_label,
            "handling": self.handling,
            "source_character_count": self.source_character_count,
            "packet_sha256": self.packet_sha256,
            "sources": [item.public_dict() for item in self.sources],
        }


def research_source_from_web_artifact(
    artifact_ref: object,
    artifact: object,
) -> ResearchSource:
    """Frame one complete bounded artifact without selecting or interpreting it."""
    if not isinstance(artifact_ref, str) or not ARTIFACT_REF_RE.fullmatch(artifact_ref):
        raise ValueError("research artifact reference is invalid")
    if not isinstance(artifact, WebFetchedArtifact):
        raise TypeError("research web artifact is invalid")
    payload = artifact.payload
    if payload.trust_label != WEB_EXTERNAL_TRUST_LABEL:
        raise ValueError("research web artifact trust label is invalid")
    if payload.character_count > MAX_RESEARCH_SOURCE_CHARACTERS:
        raise ValueError("research source requires a bounded selector")
    source_id = "RS-" + hashlib.sha256(
        (artifact.destination.url + "\n" + payload.prepared_sha256).encode("utf-8")
    ).hexdigest()[:24]
    return ResearchSource(
        1,
        source_id,
        artifact_ref,
        RESEARCH_SOURCE_KIND,
        RESEARCH_TRUST_LABEL,
        RESEARCH_HANDLING,
        artifact.destination.url,
        payload.media_type,
        artifact.fetched_at_epoch,
        payload.prepared_sha256,
        payload.text,
        payload.character_count,
        payload.source_media_type,
    )


def build_research_source_packet(
    question: object,
    sources: object,
) -> ResearchSourcePacket:
    """Build a deterministic packet without calling a provider or judging truth."""
    normalized_question, _, _ = research_question_metadata(question)
    if not isinstance(sources, (tuple, list)):
        raise TypeError("research packet sources must be a sequence")
    records = tuple(sources)
    if any(not isinstance(item, ResearchSource) for item in records):
        raise TypeError("research packet source is invalid")
    total = sum(item.character_count for item in records)
    packet = ResearchSourcePacket(
        1,
        normalized_question,
        RESEARCH_TRUST_LABEL,
        RESEARCH_HANDLING,
        records,
        total,
        _packet_digest(normalized_question, records),
    )
    return packet


__all__ = [
    "MAX_RESEARCH_PACKET_CHARACTERS",
    "MAX_RESEARCH_QUESTION_CHARACTERS",
    "MAX_RESEARCH_SOURCE_CHARACTERS",
    "MAX_RESEARCH_SOURCES",
    "RESEARCH_HANDLING",
    "RESEARCH_PACKET_SCHEMA_VERSION",
    "RESEARCH_SOURCE_KIND",
    "RESEARCH_SOURCE_SCHEMA_VERSION",
    "RESEARCH_TRUST_LABEL",
    "ResearchSource",
    "ResearchSourcePacket",
    "build_research_source_packet",
    "research_question_metadata",
    "research_source_from_web_artifact",
]
