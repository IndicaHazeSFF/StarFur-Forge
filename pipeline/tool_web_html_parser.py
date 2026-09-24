"""Bounded, inert HTML-to-text preparation for quarantined web payloads.

This is deliberately a format parser, not a browser.  It accepts only an
already-collected ``text/html`` payload, ignores markup/attributes entirely,
and returns explicitly untrusted plain text.  It does not fetch, execute
scripts, follow links, build prompts, persist content, or grant authority.
"""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import re
import unicodedata

from pipeline.tool_web_parser import QuarantinedWebText, WEB_EXTERNAL_TRUST_LABEL
from pipeline.tool_web_response import WebTextPayload


WEB_HTML_PREPARED_SCHEMA_VERSION = 1
WEB_HTML_SOURCE_MEDIA_TYPE = "text/html"
WEB_HTML_PREPARED_MEDIA_TYPE = "text/plain"
MAX_WEB_HTML_SOURCE_CHARACTERS = 256_000
MAX_WEB_HTML_PREPARED_CHARACTERS = 100_000
MAX_WEB_HTML_NODES = 32_000
MAX_WEB_HTML_DEPTH = 64
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_BLOCK_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "br", "caption", "dd", "div",
    "dl", "dt", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
})
_IGNORED_TAGS = frozenset({"script", "style", "template", "noscript", "iframe", "object", "embed"})


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _visible_text(value: str) -> None:
    for character in value:
        if character in {"\n", "\t"}:
            continue
        if unicodedata.category(character) in {"Cc", "Cf"}:
            raise ValueError("prepared HTML text contains forbidden control formatting")


class _BoundedHTMLTextExtractor(HTMLParser):
    """Streaming extractor that never builds a DOM or interprets attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._depth = 0
        self._ignored_depth = 0
        self._node_count = 0
        self._prepared_characters = 0

    def _node(self) -> None:
        self._node_count += 1
        if self._node_count > MAX_WEB_HTML_NODES:
            raise ValueError("HTML source exceeds its node limit")

    def _boundary(self) -> None:
        if self._parts and self._parts[-1] != "\n":
            self._parts.append("\n")

    def handle_starttag(self, tag: str, attrs) -> None:  # attrs are intentionally ignored.
        self._node()
        self._depth += 1
        if self._depth > MAX_WEB_HTML_DEPTH:
            raise ValueError("HTML source exceeds its nesting limit")
        normalized = tag.casefold()
        if normalized in _IGNORED_TAGS:
            self._ignored_depth += 1
        if normalized in _BLOCK_TAGS:
            self._boundary()

    def handle_startendtag(self, tag: str, attrs) -> None:
        self._node()
        if tag.casefold() in _BLOCK_TAGS:
            self._boundary()

    def handle_endtag(self, tag: str) -> None:
        self._node()
        normalized = tag.casefold()
        if normalized in _BLOCK_TAGS:
            self._boundary()
        if normalized in _IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1
        if self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        self._node()
        if self._ignored_depth:
            return
        normalized = " ".join(data.split())
        if not normalized:
            return
        extra = len(normalized) + (1 if self._parts and self._parts[-1] != "\n" else 0)
        self._prepared_characters += extra
        if self._prepared_characters > MAX_WEB_HTML_PREPARED_CHARACTERS:
            raise ValueError("prepared HTML text exceeds its character limit")
        if self._parts and self._parts[-1] != "\n":
            self._parts.append(" ")
        self._parts.append(normalized)

    def handle_comment(self, data: str) -> None:
        self._node()

    def handle_decl(self, decl: str) -> None:
        self._node()

    def handle_pi(self, data: str) -> None:
        self._node()

    def text(self) -> str:
        return "\n".join(
            part.strip() for part in "".join(self._parts).splitlines() if part.strip()
        )


def prepare_quarantined_web_html(payload: WebTextPayload) -> QuarantinedWebText:
    """Extract bounded visible text from an inert HTML response payload."""
    if not isinstance(payload, WebTextPayload):
        raise TypeError("HTML web payload is invalid")
    if payload.media_type != WEB_HTML_SOURCE_MEDIA_TYPE:
        raise ValueError("HTML parser requires a text/html payload")
    if len(payload.text) > MAX_WEB_HTML_SOURCE_CHARACTERS:
        raise ValueError("HTML source exceeds its character limit")
    extractor = _BoundedHTMLTextExtractor()
    try:
        extractor.feed(payload.text)
        extractor.close()
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("HTML source is malformed") from error
    text = unicodedata.normalize("NFC", extractor.text().replace("\r\n", "\n").replace("\r", "\n"))
    if not text:
        raise ValueError("prepared HTML text is empty")
    _visible_text(text)
    if len(text) > MAX_WEB_HTML_PREPARED_CHARACTERS:
        raise ValueError("prepared HTML text exceeds its character limit")
    return QuarantinedWebText(
        schema_version=1,
        media_type=WEB_HTML_PREPARED_MEDIA_TYPE,
        trust_label=WEB_EXTERNAL_TRUST_LABEL,
        text=text,
        character_count=len(text),
        source_sha256=payload.content_sha256,
        prepared_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        source_media_type=WEB_HTML_SOURCE_MEDIA_TYPE,
    )


__all__ = [
    "MAX_WEB_HTML_DEPTH",
    "MAX_WEB_HTML_NODES",
    "MAX_WEB_HTML_PREPARED_CHARACTERS",
    "MAX_WEB_HTML_SOURCE_CHARACTERS",
    "WEB_HTML_PREPARED_MEDIA_TYPE",
    "WEB_HTML_PREPARED_SCHEMA_VERSION",
    "WEB_HTML_SOURCE_MEDIA_TYPE",
    "prepare_quarantined_web_html",
]
