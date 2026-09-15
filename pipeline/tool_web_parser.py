"""Conservative preparation of bounded public web text.

Only plain text and Markdown are accepted initially.  Preparation normalizes
text representation and rejects hidden/control formatting, but deliberately
does not remove instruction-like prose.  Output remains explicitly untrusted
external data and must be framed as source material by any later prompt builder.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata

from pipeline.tool_web_response import WebTextPayload


WEB_PARSED_TEXT_SCHEMA_VERSION = 1
MAX_WEB_PARSED_CHARACTERS = 200_000
SUPPORTED_WEB_PARSE_MEDIA_TYPES = frozenset({"text/plain", "text/markdown"})
WEB_EXTERNAL_TRUST_LABEL = "untrusted_external"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _validate_visible_text(text: str) -> None:
    for character in text:
        if character in {"\n", "\t"}:
            continue
        if unicodedata.category(character) in {"Cc", "Cf"}:
            raise ValueError("parsed web text contains forbidden control formatting")


@dataclass(frozen=True)
class QuarantinedWebText:
    """Normalized external text that remains untrusted and noncanonical."""

    schema_version: int
    media_type: str
    trust_label: str
    text: str
    character_count: int
    source_sha256: str
    prepared_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_PARSED_TEXT_SCHEMA_VERSION:
            raise ValueError("parsed web text schema version is unsupported")
        if self.media_type not in SUPPORTED_WEB_PARSE_MEDIA_TYPES:
            raise ValueError("parsed web text media type is unsupported")
        if self.trust_label != WEB_EXTERNAL_TRUST_LABEL:
            raise ValueError("parsed web text trust label is invalid")
        if not isinstance(self.text, str) or not self.text or not self.text.strip():
            raise ValueError("parsed web text is empty")
        if (
            isinstance(self.character_count, bool)
            or not isinstance(self.character_count, int)
            or self.character_count != len(self.text)
            or self.character_count > MAX_WEB_PARSED_CHARACTERS
        ):
            raise ValueError("parsed web text character count is invalid")
        if unicodedata.normalize("NFC", self.text) != self.text or "\r" in self.text:
            raise ValueError("parsed web text is not canonical")
        _validate_visible_text(self.text)
        _validate_digest(self.source_sha256, "parsed web source digest")
        prepared = _validate_digest(self.prepared_sha256, "parsed web prepared digest")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != prepared:
            raise ValueError("parsed web prepared digest is inconsistent")


def prepare_quarantined_web_text(payload: WebTextPayload) -> QuarantinedWebText:
    """Normalize supported inert text without interpreting its claims."""
    if not isinstance(payload, WebTextPayload):
        raise TypeError("web text payload is invalid")
    if payload.media_type not in SUPPORTED_WEB_PARSE_MEDIA_TYPES:
        raise ValueError("web text payload requires a dedicated parser")
    normalized = unicodedata.normalize("NFC", payload.text.replace("\r\n", "\n").replace("\r", "\n"))
    if not normalized.strip():
        raise ValueError("parsed web text is empty")
    if len(normalized) > MAX_WEB_PARSED_CHARACTERS:
        raise ValueError("parsed web text exceeds its character limit")
    _validate_visible_text(normalized)
    return QuarantinedWebText(
        schema_version=1,
        media_type=payload.media_type,
        trust_label=WEB_EXTERNAL_TRUST_LABEL,
        text=normalized,
        character_count=len(normalized),
        source_sha256=payload.content_sha256,
        prepared_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    )


__all__ = [
    "MAX_WEB_PARSED_CHARACTERS",
    "SUPPORTED_WEB_PARSE_MEDIA_TYPES",
    "WEB_EXTERNAL_TRUST_LABEL",
    "WEB_PARSED_TEXT_SCHEMA_VERSION",
    "QuarantinedWebText",
    "prepare_quarantined_web_text",
]
