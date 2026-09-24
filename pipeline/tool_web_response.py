"""Provider-free bounds for future public-text HTTP response ingestion.

This module opens no connection and performs no decompression or content
parsing. A future trusted connector may feed post-transfer-framing byte chunks
plus the exact entity-body byte count consumed before content decoding. HTTP
``chunked`` framing is not content encoding and is intentionally excluded from
that body count. The collector fails closed on size,
expansion, media-type, encoding, or UTF-8 violations.  A resulting text payload
is still untrusted source material, never a prompt, memory, or tool authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


WEB_RESPONSE_SCHEMA_VERSION = 1
MAX_WEB_ENCODED_BYTES = 2 * 1024 * 1024
MAX_WEB_DECODED_BYTES = 4 * 1024 * 1024
MAX_WEB_DECOMPRESSION_RATIO = 40.0
ALLOWED_WEB_MEDIA_TYPES = frozenset({
    "application/json",
    "application/xml",
    "text/html",
    "text/markdown",
    "text/plain",
    "text/xml",
})
ALLOWED_WEB_CONTENT_ENCODINGS = frozenset({"identity", "gzip"})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _byte_count(name: str, value: object, *, maximum: int, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    minimum = 0 if allow_zero else 1
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} is outside its allowed range")
    return value


@dataclass(frozen=True)
class WebResponseMetadata:
    """Sanitized response metadata supplied by a future trusted connector."""

    schema_version: int
    status_code: int
    media_type: str
    content_encoding: str
    declared_encoded_bytes: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_RESPONSE_SCHEMA_VERSION:
            raise ValueError("web response schema version is unsupported")
        if isinstance(self.status_code, bool) or self.status_code != 200:
            raise ValueError("web response status is unsupported")
        if self.media_type not in ALLOWED_WEB_MEDIA_TYPES:
            raise ValueError("web response media type is unsupported")
        if self.content_encoding not in ALLOWED_WEB_CONTENT_ENCODINGS:
            raise ValueError("web response content encoding is unsupported")
        if self.declared_encoded_bytes is not None:
            _byte_count(
                "declared_encoded_bytes",
                self.declared_encoded_bytes,
                maximum=MAX_WEB_ENCODED_BYTES,
            )


@dataclass(frozen=True)
class WebTextPayload:
    """Bounded untrusted text; not sanitized instructions or canonical data."""

    schema_version: int
    media_type: str
    text: str
    encoded_bytes: int
    decoded_bytes: int
    content_sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_RESPONSE_SCHEMA_VERSION:
            raise ValueError("web text payload schema version is unsupported")
        if self.media_type not in ALLOWED_WEB_MEDIA_TYPES:
            raise ValueError("web text payload media type is unsupported")
        if not isinstance(self.text, str) or not self.text:
            raise ValueError("web text payload is empty")
        if "\x00" in self.text:
            raise ValueError("web text payload contains forbidden control data")
        encoded = _byte_count("encoded_bytes", self.encoded_bytes, maximum=MAX_WEB_ENCODED_BYTES, allow_zero=False)
        decoded = _byte_count("decoded_bytes", self.decoded_bytes, maximum=MAX_WEB_DECODED_BYTES, allow_zero=False)
        rendered = self.text.encode("utf-8")
        if len(rendered) != decoded:
            raise ValueError("web text payload decoded size is inconsistent")
        if not isinstance(self.content_sha256, str) or not _DIGEST_RE.fullmatch(self.content_sha256):
            raise ValueError("web text payload digest is invalid")
        if hashlib.sha256(rendered).hexdigest() != self.content_sha256:
            raise ValueError("web text payload digest is inconsistent")
        object.__setattr__(self, "encoded_bytes", encoded)
        object.__setattr__(self, "decoded_bytes", decoded)


class WebResponseCollector:
    """Collect an already-decoded response under independent byte ceilings."""

    def __init__(self, metadata: WebResponseMetadata) -> None:
        if not isinstance(metadata, WebResponseMetadata):
            raise TypeError("web response metadata is invalid")
        self._metadata = metadata
        self._encoded_bytes = 0
        self._decoded_bytes = 0
        self._chunks: list[bytes] = []
        self._closed = False
        self._failed = False

    def _deny(self, message: str) -> None:
        self._failed = True
        self._chunks.clear()
        raise ValueError(message)

    def append(self, decoded_chunk: bytes, *, encoded_bytes_consumed: int) -> None:
        if self._closed or self._failed:
            raise RuntimeError("web response collector is closed")
        if not isinstance(decoded_chunk, bytes):
            self._deny("web response chunk must be bytes")
        try:
            encoded = _byte_count(
                "encoded_bytes_consumed",
                encoded_bytes_consumed,
                maximum=MAX_WEB_ENCODED_BYTES,
            )
        except (TypeError, ValueError):
            self._deny("web response encoded body count is invalid")
        next_encoded = self._encoded_bytes + encoded
        next_decoded = self._decoded_bytes + len(decoded_chunk)
        if next_encoded > MAX_WEB_ENCODED_BYTES:
            self._deny("web response encoded body exceeds its limit")
        if next_decoded > MAX_WEB_DECODED_BYTES:
            self._deny("web response decoded body exceeds its limit")
        self._encoded_bytes = next_encoded
        self._decoded_bytes = next_decoded
        if decoded_chunk:
            self._chunks.append(decoded_chunk)

    def finalize(self) -> WebTextPayload:
        if self._closed or self._failed:
            raise RuntimeError("web response collector is closed")
        self._closed = True
        body = b"".join(self._chunks)
        self._chunks.clear()
        if not body or self._encoded_bytes == 0:
            raise ValueError("web response body is empty")
        declared = self._metadata.declared_encoded_bytes
        if declared is not None and declared != self._encoded_bytes:
            raise ValueError("web response declared size is inconsistent")
        if self._metadata.content_encoding == "identity" and self._encoded_bytes != len(body):
            raise ValueError("identity web response size is inconsistent")
        if len(body) / self._encoded_bytes > MAX_WEB_DECOMPRESSION_RATIO:
            raise ValueError("web response expansion ratio exceeds its limit")
        try:
            text = body.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError("web response is not valid UTF-8") from error
        if "\x00" in text:
            raise ValueError("web response contains forbidden control data")
        return WebTextPayload(
            schema_version=1,
            media_type=self._metadata.media_type,
            text=text,
            encoded_bytes=self._encoded_bytes,
            decoded_bytes=len(body),
            content_sha256=hashlib.sha256(body).hexdigest(),
        )


__all__ = [
    "ALLOWED_WEB_CONTENT_ENCODINGS",
    "ALLOWED_WEB_MEDIA_TYPES",
    "MAX_WEB_DECODED_BYTES",
    "MAX_WEB_DECOMPRESSION_RATIO",
    "MAX_WEB_ENCODED_BYTES",
    "WEB_RESPONSE_SCHEMA_VERSION",
    "WebResponseCollector",
    "WebResponseMetadata",
    "WebTextPayload",
]
