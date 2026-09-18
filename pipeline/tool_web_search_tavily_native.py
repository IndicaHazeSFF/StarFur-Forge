"""Opt-in fixed-destination native transport for Tavily Search.

Construction performs no DNS lookup or network request. Execution uses one
fixed HTTPS POST endpoint, ignores environment proxies, rejects non-global DNS
answers, pins the selected peer for TLS, and asks Tavily for basic link results
without generated answers, raw content, images, or usage details.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import ssl
from threading import RLock
import time
from typing import Callable

from pipeline.sandbox_supervisor import SupervisorCancellation
from pipeline.tool_web_search import MAX_WEB_SEARCH_RESULTS, SessionWebSearchArtifactStore
from pipeline.tool_web_search_connector import (
    WebSearchAdapterCancelled,
    WebSearchAdapterPolicyError,
    WebSearchAdapterTimedOut,
    WebSearchSupervisor,
)
from pipeline.tool_web_search_preflight import (
    WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
    WebSearchServicePrerequisite,
)
from pipeline.tool_web_search_runtime import (
    LocalWebSearchRuntime,
    SessionWebSearchPrerequisiteStore,
)
from pipeline.tool_web_search_tavily import (
    MAX_TAVILY_SEARCH_RESPONSE_BYTES,
    TAVILY_SEARCH_RESPONSE_MEDIA_TYPE,
    TAVILY_SEARCH_SERVICE_ID,
    TavilySearchHTTPResponse,
    TavilySearchTransportRequest,
    TavilyWebSearchAdapter,
    validate_tavily_api_key,
)


TAVILY_SEARCH_API_KEY_ENV = "STARFUR_TAVILY_API_KEY"
TAVILY_SEARCH_HOST = "api.tavily.com"
TAVILY_SEARCH_PATH = "/search"
TAVILY_SEARCH_PORT = 443
TAVILY_SEARCH_SERVICE_EVIDENCE_SECONDS = 30.0
TAVILY_SEARCH_READ_CHUNK_BYTES = 64 * 1024
MAX_TAVILY_SEARCH_RESOLVED_ADDRESSES = 8
MAX_TAVILY_SEARCH_REQUEST_BYTES = 16 * 1024


class EnvironmentTavilyCredentialSource:
    """Read a user-supplied key just in time from one fixed environment name."""

    def __init__(
        self,
        *,
        getenv: Callable[[str], str | None] = os.getenv,
        variable_name: str = TAVILY_SEARCH_API_KEY_ENV,
    ) -> None:
        if not callable(getenv):
            raise TypeError("Tavily credential reader is invalid")
        if variable_name != TAVILY_SEARCH_API_KEY_ENV:
            raise ValueError("Tavily credential variable is unsupported")
        self._getenv = getenv
        self._variable_name = variable_name

    @property
    def available(self) -> bool:
        try:
            validate_tavily_api_key(self._getenv(self._variable_name))
        except Exception:
            return False
        return True

    def read_api_key(self) -> str:
        return validate_tavily_api_key(self._getenv(self._variable_name))


class _PinnedTavilyHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, address: str, *, timeout: float) -> None:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(TAVILY_SEARCH_HOST, TAVILY_SEARCH_PORT, timeout=timeout, context=context)
        self._address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._address, TAVILY_SEARCH_PORT), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=TAVILY_SEARCH_HOST)
        except Exception:
            raw.close()
            raise


class NativeTavilySearchTransport:
    """Fixed-destination HTTPS transport; never registered implicitly."""

    available = True

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        getaddrinfo: Callable = socket.getaddrinfo,
        connection_factory: Callable | None = None,
    ) -> None:
        if not callable(clock) or not callable(getaddrinfo):
            raise TypeError("Tavily transport dependency is invalid")
        if connection_factory is not None and not callable(connection_factory):
            raise TypeError("Tavily connection factory is invalid")
        self._clock = clock
        self._getaddrinfo = getaddrinfo
        self._connection_factory = connection_factory or (
            lambda address, timeout: _PinnedTavilyHTTPSConnection(address, timeout=timeout)
        )
        self._active: dict[tuple[str, str], object] = {}
        self._lock = RLock()

    def _resolve_public_address(self) -> str:
        try:
            records = self._getaddrinfo(
                TAVILY_SEARCH_HOST,
                TAVILY_SEARCH_PORT,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
            )
        except Exception as error:
            raise WebSearchAdapterPolicyError("hosted search resolution failed") from error
        addresses: set[str] = set()
        for record in records:
            try:
                address = ipaddress.ip_address(record[4][0])
            except (IndexError, TypeError, ValueError) as error:
                raise WebSearchAdapterPolicyError("hosted search resolution is invalid") from error
            if not address.is_global:
                raise WebSearchAdapterPolicyError("hosted search resolved to a forbidden address")
            addresses.add(str(address))
        if not addresses or len(addresses) > MAX_TAVILY_SEARCH_RESOLVED_ADDRESSES:
            raise WebSearchAdapterPolicyError("hosted search address count is unsupported")
        return sorted(addresses)[0]

    @staticmethod
    def _request_body(request: TavilySearchTransportRequest) -> bytes:
        body = json.dumps({
            "query": request.query,
            "search_depth": "basic",
            "max_results": request.maximum_results,
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_image_descriptions": False,
            "include_favicon": False,
            "auto_parameters": False,
            "include_usage": False,
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if not body or len(body) > MAX_TAVILY_SEARCH_REQUEST_BYTES:
            raise WebSearchAdapterPolicyError("hosted search request exceeds its limit")
        return body

    def search(
        self,
        request: TavilySearchTransportRequest,
        api_key: str,
        cancellation: SupervisorCancellation,
    ) -> TavilySearchHTTPResponse:
        if not isinstance(request, TavilySearchTransportRequest):
            raise TypeError("Tavily transport request is invalid")
        if not isinstance(cancellation, SupervisorCancellation):
            raise TypeError("Tavily transport cancellation is invalid")
        key_value = validate_tavily_api_key(api_key)
        if cancellation.requested:
            raise WebSearchAdapterCancelled("hosted search was cancelled")
        remaining = request.authorization_deadline - float(self._clock())
        if remaining <= 0:
            raise WebSearchAdapterTimedOut("hosted search authorization expired")
        body = self._request_body(request)
        address = self._resolve_public_address()
        if cancellation.requested:
            raise WebSearchAdapterCancelled("hosted search was cancelled")
        remaining = request.authorization_deadline - float(self._clock())
        if remaining <= 0:
            raise WebSearchAdapterTimedOut("hosted search authorization expired")
        operation = (request.invocation_id, request.worker_generation)
        connection = self._connection_factory(address, remaining)
        with self._lock:
            if operation in self._active:
                try:
                    connection.close()
                finally:
                    raise WebSearchAdapterPolicyError("hosted search request is already active")
            self._active[operation] = connection
        try:
            connection.putrequest("POST", TAVILY_SEARCH_PATH, skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", TAVILY_SEARCH_HOST)
            connection.putheader("Authorization", f"Bearer {key_value}")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(len(body)))
            connection.putheader("Accept", TAVILY_SEARCH_RESPONSE_MEDIA_TYPE)
            connection.putheader("Accept-Encoding", "identity")
            connection.putheader("User-Agent", "StarFur-Forge/1 web.search")
            connection.putheader("Connection", "close")
            connection.endheaders(body)
            peer = getattr(connection, "sock", None)
            if peer is None or not hasattr(peer, "getpeername"):
                raise WebSearchAdapterPolicyError("hosted search peer is unavailable")
            connected = str(ipaddress.ip_address(peer.getpeername()[0]))
            if connected != address or not ipaddress.ip_address(connected).is_global:
                raise WebSearchAdapterPolicyError("hosted search peer binding changed")
            response = connection.getresponse()
            if response.status != 200:
                return TavilySearchHTTPResponse(
                    response.status,
                    TAVILY_SEARCH_RESPONSE_MEDIA_TYPE,
                    b"{}",
                )
            media_type = self._media_type(self._single_header(response, "Content-Type"))
            content_encoding = (
                self._single_header(response, "Content-Encoding") or "identity"
            ).casefold()
            if content_encoding != "identity":
                raise WebSearchAdapterPolicyError("hosted search content encoding is unsupported")
            transfer_encoding = self._single_header(response, "Transfer-Encoding")
            if transfer_encoding is not None and transfer_encoding.casefold() != "chunked":
                raise WebSearchAdapterPolicyError("hosted search transfer encoding is unsupported")
            declared = self._content_length(self._single_header(response, "Content-Length"))
            chunks: list[bytes] = []
            total = 0
            while True:
                if cancellation.requested:
                    raise WebSearchAdapterCancelled("hosted search was cancelled")
                remaining = request.authorization_deadline - float(self._clock())
                if remaining <= 0:
                    raise WebSearchAdapterTimedOut("hosted search timed out")
                sock = getattr(connection, "sock", None)
                if sock is not None and hasattr(sock, "settimeout"):
                    sock.settimeout(remaining)
                chunk = response.read(TAVILY_SEARCH_READ_CHUNK_BYTES)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise WebSearchAdapterPolicyError("hosted search response body is invalid")
                total += len(chunk)
                if total > MAX_TAVILY_SEARCH_RESPONSE_BYTES:
                    raise WebSearchAdapterPolicyError("hosted search response exceeds its limit")
                chunks.append(chunk)
            response_body = b"".join(chunks)
            if not response_body or (declared is not None and declared != len(response_body)):
                raise WebSearchAdapterPolicyError("hosted search response length is inconsistent")
            return TavilySearchHTTPResponse(response.status, media_type, response_body)
        except (WebSearchAdapterCancelled, WebSearchAdapterPolicyError, WebSearchAdapterTimedOut):
            raise
        except (socket.timeout, TimeoutError) as error:
            raise WebSearchAdapterTimedOut("hosted search timed out") from error
        except Exception as error:
            if cancellation.requested:
                raise WebSearchAdapterCancelled("hosted search was cancelled") from error
            raise RuntimeError("hosted search transport failed") from error
        finally:
            try:
                connection.close()
            finally:
                with self._lock:
                    self._active.pop(operation, None)

    def request_cancel(self, request: TavilySearchTransportRequest) -> None:
        if not isinstance(request, TavilySearchTransportRequest):
            raise TypeError("Tavily cancellation request is invalid")
        operation = (request.invocation_id, request.worker_generation)
        with self._lock:
            connection = self._active.get(operation)
        if connection is not None:
            connection.close()

    @staticmethod
    def _single_header(response: object, name: str) -> str | None:
        values = [
            value.strip()
            for key, value in response.getheaders()
            if isinstance(key, str) and key.casefold() == name.casefold()
        ]
        if len(values) > 1:
            raise WebSearchAdapterPolicyError("hosted search response headers are ambiguous")
        return values[0] if values else None

    @staticmethod
    def _media_type(value: str | None) -> str:
        if value is None:
            raise WebSearchAdapterPolicyError("hosted search response media type is missing")
        parts = [part.strip() for part in value.split(";")]
        if parts[0].casefold() != TAVILY_SEARCH_RESPONSE_MEDIA_TYPE:
            raise WebSearchAdapterPolicyError("hosted search response media type is unsupported")
        for parameter in parts[1:]:
            if parameter.casefold() not in {"charset=utf-8", "charset=\"utf-8\""}:
                raise WebSearchAdapterPolicyError("hosted search response media parameter is unsupported")
        return TAVILY_SEARCH_RESPONSE_MEDIA_TYPE

    @staticmethod
    def _content_length(value: str | None) -> int | None:
        if value is None:
            return None
        if not value.isascii() or not value.isdecimal():
            raise WebSearchAdapterPolicyError("hosted search content length is invalid")
        length = int(value)
        if not 0 < length <= MAX_TAVILY_SEARCH_RESPONSE_BYTES:
            raise WebSearchAdapterPolicyError("hosted search content length is unsupported")
        return length


def create_tavily_web_search_runtime(
    *,
    getenv: Callable[[str], str | None] = os.getenv,
    clock: Callable[[], float] = time.time,
    getaddrinfo: Callable = socket.getaddrinfo,
    connection_factory: Callable | None = None,
    maximum_results: int = 5,
) -> LocalWebSearchRuntime:
    """Compose an opt-in session runtime without probing or contacting Tavily."""
    if (
        isinstance(maximum_results, bool)
        or not isinstance(maximum_results, int)
        or not 1 <= maximum_results <= MAX_WEB_SEARCH_RESULTS
    ):
        raise ValueError("Tavily search result limit is invalid")
    credentials = EnvironmentTavilyCredentialSource(getenv=getenv)
    transport = NativeTavilySearchTransport(
        clock=clock,
        getaddrinfo=getaddrinfo,
        connection_factory=connection_factory,
    )
    adapter = TavilyWebSearchAdapter(credentials, transport)
    prerequisites = SessionWebSearchPrerequisiteStore(
        service_id=TAVILY_SEARCH_SERVICE_ID,
        deployment="hosted",
        maximum_results=maximum_results,
    )
    quarantine = SessionWebSearchArtifactStore()

    def observe_service(resource_ref: str) -> WebSearchServicePrerequisite:
        now = float(clock())
        return WebSearchServicePrerequisite(
            1,
            resource_ref,
            TAVILY_SEARCH_SERVICE_ID,
            "hosted",
            maximum_results,
            adapter.available,
            now,
            now + TAVILY_SEARCH_SERVICE_EVIDENCE_SECONDS,
            WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
        )

    supervisor = WebSearchSupervisor(prerequisites, adapter, quarantine, clock=clock)
    return LocalWebSearchRuntime(prerequisites, quarantine, supervisor, observe_service)


__all__ = [
    "EnvironmentTavilyCredentialSource",
    "MAX_TAVILY_SEARCH_REQUEST_BYTES",
    "NativeTavilySearchTransport",
    "TAVILY_SEARCH_API_KEY_ENV",
    "TAVILY_SEARCH_HOST",
    "TAVILY_SEARCH_PATH",
    "TAVILY_SEARCH_PORT",
    "TAVILY_SEARCH_SERVICE_EVIDENCE_SECONDS",
    "create_tavily_web_search_runtime",
]
