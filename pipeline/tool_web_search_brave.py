"""Strict Brave Search adapter behind StarFur's provider-neutral search seam.

The adapter receives only an already-authorized ``WebSearchRequest``.  Its API
credential and HTTP transport are injected trusted dependencies; neither is
part of a proposal, grant, prerequisite, artifact, or public status record.
Provider output is reduced to bounded untrusted URL/title candidates before it
can cross back into the Core-owned quarantine.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Protocol

from pipeline.sandbox_supervisor import SupervisorCancellation
from pipeline.tool_web_search import MAX_WEB_SEARCH_RESULTS, WebSearchCandidate
from pipeline.tool_web_search_connector import (
    WebSearchAdapterCancelled,
    WebSearchAdapterPolicyError,
    WebSearchRequest,
    WebSearchResponse,
)


BRAVE_SEARCH_SERVICE_ID = "brave.search"
BRAVE_SEARCH_RESPONSE_MEDIA_TYPE = "application/json"
MAX_BRAVE_SEARCH_RESPONSE_BYTES = 512 * 1024
MAX_BRAVE_SEARCH_JSON_DEPTH = 12
MAX_BRAVE_SEARCH_JSON_NODES = 8192
MAX_BRAVE_SEARCH_API_KEY_BYTES = 2048


def validate_brave_api_key(value: object) -> str:
    """Validate a transient header value without retaining or rendering it."""
    if not isinstance(value, str):
        raise WebSearchAdapterPolicyError("hosted search credential is unavailable")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise WebSearchAdapterPolicyError("hosted search credential is invalid") from error
    if (
        not encoded
        or len(encoded) > MAX_BRAVE_SEARCH_API_KEY_BYTES
        or any(byte < 0x21 or byte > 0x7E for byte in encoded)
    ):
        raise WebSearchAdapterPolicyError("hosted search credential is invalid")
    return value


class BraveSearchCredentialSource(Protocol):
    """Trusted secret source; public availability must never reveal the key."""

    @property
    def available(self) -> bool: ...

    def read_api_key(self) -> str: ...


@dataclass(frozen=True)
class BraveSearchTransportRequest:
    """Secret-free exact request passed to the fixed Brave HTTP transport."""

    invocation_id: str
    binding_fingerprint: str
    worker_generation: str
    query: str
    maximum_results: int
    authorization_deadline: float

    @classmethod
    def from_search_request(cls, request: WebSearchRequest) -> "BraveSearchTransportRequest":
        if not isinstance(request, WebSearchRequest):
            raise TypeError("Brave search request is invalid")
        if request.service_id != BRAVE_SEARCH_SERVICE_ID:
            raise WebSearchAdapterPolicyError("hosted search service binding is invalid")
        return cls(
            request.invocation_id,
            request.binding_fingerprint,
            request.worker_generation,
            request.query,
            request.maximum_results,
            request.authorization_deadline,
        )


@dataclass(frozen=True)
class BraveSearchHTTPResponse:
    """Bounded raw HTTP result before provider-specific JSON reduction."""

    status_code: int
    media_type: str
    body: bytes

    def __post_init__(self) -> None:
        if (
            isinstance(self.status_code, bool)
            or not isinstance(self.status_code, int)
            or not 100 <= self.status_code <= 599
        ):
            raise ValueError("Brave search response status is invalid")
        if not isinstance(self.media_type, str) or self.media_type != BRAVE_SEARCH_RESPONSE_MEDIA_TYPE:
            raise ValueError("Brave search response media type is invalid")
        if not isinstance(self.body, bytes):
            raise TypeError("Brave search response body must be bytes")
        if not self.body or len(self.body) > MAX_BRAVE_SEARCH_RESPONSE_BYTES:
            raise ValueError("Brave search response body size is invalid")


class BraveSearchTransport(Protocol):
    @property
    def available(self) -> bool: ...

    def search(
        self,
        request: BraveSearchTransportRequest,
        api_key: str,
        cancellation: SupervisorCancellation,
    ) -> BraveSearchHTTPResponse: ...

    def request_cancel(self, request: BraveSearchTransportRequest) -> None: ...


def _reject_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Brave search JSON contains duplicate fields")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise ValueError(f"Brave search JSON contains non-finite number: {value}")


def _json_shape(value: object, depth: int = 0) -> tuple[int, int]:
    if depth > MAX_BRAVE_SEARCH_JSON_DEPTH:
        raise ValueError("Brave search JSON depth limit exceeded")
    nodes = 1
    deepest = depth
    if isinstance(value, Mapping):
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        children = ()
    for child in children:
        child_nodes, child_depth = _json_shape(child, depth + 1)
        nodes += child_nodes
        deepest = max(deepest, child_depth)
        if nodes > MAX_BRAVE_SEARCH_JSON_NODES:
            raise ValueError("Brave search JSON node limit exceeded")
    return nodes, deepest


def parse_brave_search_response(
    response: object,
    *,
    maximum_results: int,
) -> tuple[WebSearchCandidate, ...]:
    """Reduce one provider response to strict untrusted discovery candidates."""
    if not isinstance(response, BraveSearchHTTPResponse):
        raise TypeError("Brave search HTTP response is invalid")
    if response.status_code != 200:
        raise WebSearchAdapterPolicyError("hosted search request was rejected")
    if (
        isinstance(maximum_results, bool)
        or not isinstance(maximum_results, int)
        or not 1 <= maximum_results <= MAX_WEB_SEARCH_RESULTS
    ):
        raise ValueError("Brave search result limit is invalid")
    try:
        text = response.body.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Brave search response JSON is malformed") from error
    _json_shape(value)
    if not isinstance(value, Mapping):
        raise ValueError("Brave search response must be an object")
    web = value.get("web")
    results = web.get("results") if isinstance(web, Mapping) else None
    if not isinstance(results, list) or not results:
        raise ValueError("Brave search response has no web results")
    candidates: list[WebSearchCandidate] = []
    seen_urls: set[str] = set()
    for item in results[:maximum_results]:
        if not isinstance(item, Mapping):
            raise ValueError("Brave search result is invalid")
        if not isinstance(item.get("url"), str) or not isinstance(item.get("title"), str):
            raise ValueError("Brave search result fields are invalid")
        candidate = WebSearchCandidate(len(candidates) + 1, item["url"], item["title"])
        if candidate.url in seen_urls:
            raise ValueError("Brave search result URLs must be unique")
        seen_urls.add(candidate.url)
        candidates.append(candidate)
    if not candidates:
        raise ValueError("Brave search response has no usable results")
    return tuple(candidates)


class BraveWebSearchAdapter:
    """Translate exact Brave transport results into provider-neutral output."""

    service_id = BRAVE_SEARCH_SERVICE_ID

    def __init__(self, credential_source: object, transport: object) -> None:
        self._credentials = credential_source
        self._transport = transport

    @staticmethod
    def _available(component: object) -> bool:
        try:
            return component.available is True
        except Exception:
            return False

    @property
    def available(self) -> bool:
        return self._available(self._credentials) and self._available(self._transport)

    def search(
        self,
        request: WebSearchRequest,
        cancellation: SupervisorCancellation,
    ) -> WebSearchResponse:
        if not isinstance(cancellation, SupervisorCancellation):
            raise TypeError("Brave search cancellation is invalid")
        if not self.available:
            raise WebSearchAdapterPolicyError("hosted search adapter is unavailable")
        if cancellation.requested:
            raise WebSearchAdapterCancelled("hosted search was cancelled")
        transport_request = BraveSearchTransportRequest.from_search_request(request)
        api_key = validate_brave_api_key(self._credentials.read_api_key())
        raw = self._transport.search(transport_request, api_key, cancellation)
        results = parse_brave_search_response(raw, maximum_results=request.maximum_results)
        return WebSearchResponse(
            1,
            request.invocation_id,
            request.binding_fingerprint,
            request.worker_generation,
            request.service_id,
            request.query_sha256,
            results,
        )

    def request_cancel(self, request: WebSearchRequest) -> None:
        self._transport.request_cancel(BraveSearchTransportRequest.from_search_request(request))


__all__ = [
    "BRAVE_SEARCH_RESPONSE_MEDIA_TYPE",
    "BRAVE_SEARCH_SERVICE_ID",
    "BraveSearchCredentialSource",
    "BraveSearchHTTPResponse",
    "BraveSearchTransport",
    "BraveSearchTransportRequest",
    "BraveWebSearchAdapter",
    "MAX_BRAVE_SEARCH_API_KEY_BYTES",
    "MAX_BRAVE_SEARCH_JSON_DEPTH",
    "MAX_BRAVE_SEARCH_JSON_NODES",
    "MAX_BRAVE_SEARCH_RESPONSE_BYTES",
    "parse_brave_search_response",
    "validate_brave_api_key",
]
