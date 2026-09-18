"""Opt-in native transport and runtime composition for Brave Search.

Construction performs no DNS lookup or network request.  The transport uses a
fixed HTTPS host/path, ignores environment proxies, rejects non-global DNS
answers, pins the selected peer for TLS, bounds response bytes, and never
returns provider payloads or credentials through a public StarFur contract.
The standard Assistant application factory does not enable this runtime.
"""

from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
from threading import RLock
import time
from typing import Callable
from urllib.parse import urlencode

from pipeline.sandbox_supervisor import SupervisorCancellation
from pipeline.tool_web_search import MAX_WEB_SEARCH_RESULTS, SessionWebSearchArtifactStore
from pipeline.tool_web_search_brave import (
    BRAVE_SEARCH_RESPONSE_MEDIA_TYPE,
    BRAVE_SEARCH_SERVICE_ID,
    MAX_BRAVE_SEARCH_RESPONSE_BYTES,
    BraveSearchHTTPResponse,
    BraveSearchTransportRequest,
    BraveWebSearchAdapter,
    validate_brave_api_key,
)
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


BRAVE_SEARCH_API_KEY_ENV = "STARFUR_BRAVE_SEARCH_API_KEY"
BRAVE_SEARCH_HOST = "api.search.brave.com"
BRAVE_SEARCH_PATH = "/res/v1/web/search"
BRAVE_SEARCH_PORT = 443
BRAVE_SEARCH_SERVICE_EVIDENCE_SECONDS = 30.0
BRAVE_SEARCH_READ_CHUNK_BYTES = 64 * 1024
MAX_BRAVE_SEARCH_RESOLVED_ADDRESSES = 8


class EnvironmentBraveCredentialSource:
    """Read a user-supplied key just in time from one fixed environment name."""

    def __init__(
        self,
        *,
        getenv: Callable[[str], str | None] = os.getenv,
        variable_name: str = BRAVE_SEARCH_API_KEY_ENV,
    ) -> None:
        if not callable(getenv):
            raise TypeError("Brave credential reader is invalid")
        if variable_name != BRAVE_SEARCH_API_KEY_ENV:
            raise ValueError("Brave credential variable is unsupported")
        self._getenv = getenv
        self._variable_name = variable_name

    @property
    def available(self) -> bool:
        try:
            validate_brave_api_key(self._getenv(self._variable_name))
        except Exception:
            return False
        return True

    def read_api_key(self) -> str:
        return validate_brave_api_key(self._getenv(self._variable_name))


class _PinnedBraveHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, address: str, *, timeout: float) -> None:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(BRAVE_SEARCH_HOST, BRAVE_SEARCH_PORT, timeout=timeout, context=context)
        self._address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._address, BRAVE_SEARCH_PORT), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=BRAVE_SEARCH_HOST)
        except Exception:
            raw.close()
            raise


class NativeBraveSearchTransport:
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
            raise TypeError("Brave transport dependency is invalid")
        if connection_factory is not None and not callable(connection_factory):
            raise TypeError("Brave connection factory is invalid")
        self._clock = clock
        self._getaddrinfo = getaddrinfo
        self._connection_factory = connection_factory or (
            lambda address, timeout: _PinnedBraveHTTPSConnection(address, timeout=timeout)
        )
        self._active: dict[tuple[str, str], object] = {}
        self._lock = RLock()

    def _resolve_public_address(self) -> str:
        try:
            records = self._getaddrinfo(
                BRAVE_SEARCH_HOST,
                BRAVE_SEARCH_PORT,
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
        if not addresses or len(addresses) > MAX_BRAVE_SEARCH_RESOLVED_ADDRESSES:
            raise WebSearchAdapterPolicyError("hosted search address count is unsupported")
        return sorted(addresses)[0]

    def search(
        self,
        request: BraveSearchTransportRequest,
        api_key: str,
        cancellation: SupervisorCancellation,
    ) -> BraveSearchHTTPResponse:
        if not isinstance(request, BraveSearchTransportRequest):
            raise TypeError("Brave transport request is invalid")
        if not isinstance(cancellation, SupervisorCancellation):
            raise TypeError("Brave transport cancellation is invalid")
        key_value = validate_brave_api_key(api_key)
        if cancellation.requested:
            raise WebSearchAdapterCancelled("hosted search was cancelled")
        remaining = request.authorization_deadline - float(self._clock())
        if remaining <= 0:
            raise WebSearchAdapterTimedOut("hosted search authorization expired")
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
            target = BRAVE_SEARCH_PATH + "?" + urlencode({
                "q": request.query,
                "count": str(request.maximum_results),
            })
            connection.putrequest("GET", target, skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", BRAVE_SEARCH_HOST)
            connection.putheader("Accept", BRAVE_SEARCH_RESPONSE_MEDIA_TYPE)
            connection.putheader("Accept-Encoding", "identity")
            connection.putheader("X-Subscription-Token", key_value)
            connection.putheader("User-Agent", "StarFur-Forge/1 web.search")
            connection.putheader("Connection", "close")
            connection.endheaders()
            peer = getattr(connection, "sock", None)
            if peer is None or not hasattr(peer, "getpeername"):
                raise WebSearchAdapterPolicyError("hosted search peer is unavailable")
            connected = str(ipaddress.ip_address(peer.getpeername()[0]))
            if connected != address or not ipaddress.ip_address(connected).is_global:
                raise WebSearchAdapterPolicyError("hosted search peer binding changed")
            response = connection.getresponse()
            if response.status != 200:
                return BraveSearchHTTPResponse(
                    response.status,
                    BRAVE_SEARCH_RESPONSE_MEDIA_TYPE,
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
                chunk = response.read(BRAVE_SEARCH_READ_CHUNK_BYTES)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise WebSearchAdapterPolicyError("hosted search response body is invalid")
                total += len(chunk)
                if total > MAX_BRAVE_SEARCH_RESPONSE_BYTES:
                    raise WebSearchAdapterPolicyError("hosted search response exceeds its limit")
                chunks.append(chunk)
            body = b"".join(chunks)
            if not body or (declared is not None and declared != len(body)):
                raise WebSearchAdapterPolicyError("hosted search response length is inconsistent")
            return BraveSearchHTTPResponse(response.status, media_type, body)
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

    def request_cancel(self, request: BraveSearchTransportRequest) -> None:
        if not isinstance(request, BraveSearchTransportRequest):
            raise TypeError("Brave cancellation request is invalid")
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
        if parts[0].casefold() != BRAVE_SEARCH_RESPONSE_MEDIA_TYPE:
            raise WebSearchAdapterPolicyError("hosted search response media type is unsupported")
        for parameter in parts[1:]:
            if parameter.casefold() not in {"charset=utf-8", "charset=\"utf-8\""}:
                raise WebSearchAdapterPolicyError("hosted search response media parameter is unsupported")
        return BRAVE_SEARCH_RESPONSE_MEDIA_TYPE

    @staticmethod
    def _content_length(value: str | None) -> int | None:
        if value is None:
            return None
        if not value.isascii() or not value.isdecimal():
            raise WebSearchAdapterPolicyError("hosted search content length is invalid")
        length = int(value)
        if not 0 < length <= MAX_BRAVE_SEARCH_RESPONSE_BYTES:
            raise WebSearchAdapterPolicyError("hosted search content length is unsupported")
        return length


def create_brave_web_search_runtime(
    *,
    getenv: Callable[[str], str | None] = os.getenv,
    clock: Callable[[], float] = time.time,
    getaddrinfo: Callable = socket.getaddrinfo,
    connection_factory: Callable | None = None,
    maximum_results: int = 5,
) -> LocalWebSearchRuntime:
    """Compose an opt-in session runtime without probing or contacting Brave."""
    if (
        isinstance(maximum_results, bool)
        or not isinstance(maximum_results, int)
        or not 1 <= maximum_results <= MAX_WEB_SEARCH_RESULTS
    ):
        raise ValueError("Brave search result limit is invalid")
    credentials = EnvironmentBraveCredentialSource(getenv=getenv)
    transport = NativeBraveSearchTransport(
        clock=clock,
        getaddrinfo=getaddrinfo,
        connection_factory=connection_factory,
    )
    adapter = BraveWebSearchAdapter(credentials, transport)
    prerequisites = SessionWebSearchPrerequisiteStore(
        service_id=BRAVE_SEARCH_SERVICE_ID,
        deployment="hosted",
        maximum_results=maximum_results,
    )
    quarantine = SessionWebSearchArtifactStore()

    def observe_service(resource_ref: str) -> WebSearchServicePrerequisite:
        now = float(clock())
        return WebSearchServicePrerequisite(
            1,
            resource_ref,
            BRAVE_SEARCH_SERVICE_ID,
            "hosted",
            maximum_results,
            adapter.available,
            now,
            now + BRAVE_SEARCH_SERVICE_EVIDENCE_SECONDS,
            WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
        )

    supervisor = WebSearchSupervisor(
        prerequisites,
        adapter,
        quarantine,
        clock=clock,
    )
    return LocalWebSearchRuntime(
        prerequisites,
        quarantine,
        supervisor,
        observe_service,
    )


__all__ = [
    "BRAVE_SEARCH_API_KEY_ENV",
    "BRAVE_SEARCH_HOST",
    "BRAVE_SEARCH_PATH",
    "BRAVE_SEARCH_PORT",
    "BRAVE_SEARCH_SERVICE_EVIDENCE_SECONDS",
    "EnvironmentBraveCredentialSource",
    "NativeBraveSearchTransport",
    "create_brave_web_search_runtime",
]
