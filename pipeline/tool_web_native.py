"""Unregistered native adapters for the controlled ``web.fetch`` smoke gate.

Nothing in application startup imports or constructs these adapters. The
resolver performs DNS only when explicitly called, and the transport performs
one pinned HTTPS GET only when explicitly invoked by a configured supervisor.
There is no proxy, redirect, credential, cookie, provider, or prompt path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import http.client
import ipaddress
import secrets
import socket
import ssl
from threading import RLock
import time
from typing import Callable
from urllib.parse import urlsplit

from pipeline.sandbox_supervisor import SupervisorCancellation
from pipeline.tool_contracts import ARTIFACT_REF_RE
from pipeline.tool_grants import RESOURCE_REF_RE
from pipeline.tool_web_connector import (
    WebDecodedChunk,
    WebFetchedArtifact,
    WebTransportCancelled,
    WebTransportPolicyError,
    WebTransportRequest,
    WebTransportResponse,
    WebTransportTimedOut,
    WebFetchSupervisor,
)
from pipeline.tool_web_disclosure import WebDisclosureIntent
from pipeline.tool_web_policy import (
    MAX_RESOLVED_ADDRESSES,
    WebDestination,
    WebResolutionEvidence,
)
from pipeline.tool_web_preflight import (
    WebDestinationPrerequisite,
    WebDisclosurePrerequisite,
)
from pipeline.tool_web_response import MAX_WEB_ENCODED_BYTES, WebResponseMetadata


NATIVE_WEB_RESOLVER_REVISION = "native-system-v1"
NATIVE_WEB_DNS_LIFETIME_SECONDS = 30.0
NATIVE_WEB_READ_CHUNK_BYTES = 64 * 1024
MAX_SESSION_WEB_PREREQUISITES = 64
MAX_SESSION_WEB_ARTIFACTS = 64
MAX_SESSION_WEB_ARTIFACT_BYTES = 16 * 1024 * 1024
_SUPPORTED_NATIVE_MEDIA = frozenset({"text/html", "text/plain", "text/markdown"})


class NativeWebResolver:
    """Explicit bounded system resolver; never called by passive surfaces."""

    available = True

    def __init__(
        self,
        *,
        getaddrinfo: Callable = socket.getaddrinfo,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not callable(getaddrinfo) or not callable(clock):
            raise TypeError("native web resolver dependency is invalid")
        self._getaddrinfo = getaddrinfo
        self._clock = clock

    def resolve(self, destination: WebDestination) -> WebResolutionEvidence:
        if not isinstance(destination, WebDestination):
            raise TypeError("native web destination is invalid")
        try:
            records = self._getaddrinfo(
                destination.host,
                destination.port,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
            )
        except Exception as error:
            raise WebTransportPolicyError("web destination resolution failed") from error
        addresses: set[str] = set()
        for record in records:
            try:
                value = str(ipaddress.ip_address(record[4][0]))
            except (IndexError, TypeError, ValueError) as error:
                raise WebTransportPolicyError("web resolver returned invalid evidence") from error
            addresses.add(value)
        ordered = tuple(sorted(addresses))
        if not ordered or len(ordered) > MAX_RESOLVED_ADDRESSES:
            raise WebTransportPolicyError("web resolver address count is unsupported")
        now = float(self._clock())
        return WebResolutionEvidence(
            1,
            destination.host,
            destination.port,
            ordered,
            NATIVE_WEB_RESOLVER_REVISION,
            now,
            now + NATIVE_WEB_DNS_LIFETIME_SECONDS,
        )


class SessionWebPrerequisiteStore:
    """Bounded session-only evidence store; not a grant or approval source."""

    available = True

    def __init__(
        self,
        resolver: NativeWebResolver,
        *,
        ref_factory: Callable[[], str] | None = None,
        maximum_records: int = MAX_SESSION_WEB_PREREQUISITES,
    ) -> None:
        if not isinstance(resolver, NativeWebResolver):
            raise TypeError("web prerequisite resolver is invalid")
        if ref_factory is not None and not callable(ref_factory):
            raise TypeError("web prerequisite reference factory is invalid")
        if (
            isinstance(maximum_records, bool)
            or not isinstance(maximum_records, int)
            or not 1 <= maximum_records <= 1024
        ):
            raise ValueError("web prerequisite store limit is invalid")
        self._resolver = resolver
        self._ref_factory = ref_factory or (lambda: f"TR-{secrets.token_hex(16)}")
        self._maximum_records = maximum_records
        self._reservations: dict[tuple[str, str], WebDestination] = {}
        self._destinations: dict[str, WebDestinationPrerequisite] = {}
        self._disclosures: dict[str, WebDisclosurePrerequisite] = {}
        self._lock = RLock()

    def reserve_public(self, destination: WebDestination) -> tuple[str, str]:
        """Reserve opaque bindings without DNS, network, or policy evidence."""
        if not isinstance(destination, WebDestination):
            raise TypeError("web prerequisite destination is invalid")
        with self._lock:
            if self._record_count() + 2 > self._maximum_records:
                raise WebTransportPolicyError("web prerequisite store is full")
        destination_ref = self._new_ref()
        disclosure_ref = self._new_ref()
        with self._lock:
            if self._record_count() + 2 > self._maximum_records:
                raise WebTransportPolicyError("web prerequisite store is full")
            if destination_ref == disclosure_ref or self._ref_exists(destination_ref) or self._ref_exists(
                disclosure_ref
            ):
                raise WebTransportPolicyError("web prerequisite reference was reused")
            self._reservations[(destination_ref, disclosure_ref)] = destination
        return destination_ref, disclosure_ref

    def prepare_reserved(
        self, destination_ref: str, disclosure_ref: str,
    ) -> tuple[WebDestinationPrerequisite, WebDisclosurePrerequisite]:
        """Resolve one previously inert reservation under explicit Core control."""
        with self._lock:
            destination = self._reservations.get((destination_ref, disclosure_ref))
        if destination is None:
            raise WebTransportPolicyError("web prerequisite reservation was not found")
        resolution = self._resolver.resolve(destination)
        url_bytes = destination.url.encode("utf-8")
        digest = hashlib.sha256(url_bytes).hexdigest()
        destination_record = WebDestinationPrerequisite(
            1, destination_ref, destination, resolution,
        )
        disclosure_record = WebDisclosurePrerequisite(
            1,
            disclosure_ref,
            digest,
            WebDisclosureIntent(
                1, "public", "user_supplied", len(url_bytes), digest,
            ),
        )
        with self._lock:
            current = self._reservations.get((destination_ref, disclosure_ref))
            if current != destination:
                raise WebTransportPolicyError("web prerequisite reservation changed")
            self._destinations[destination_ref] = destination_record
            self._disclosures[disclosure_ref] = disclosure_record
            del self._reservations[(destination_ref, disclosure_ref)]
        return destination_record, disclosure_record

    def prepare_public(
        self, destination: WebDestination,
    ) -> tuple[WebDestinationPrerequisite, WebDisclosurePrerequisite]:
        """Compatibility helper for trusted adapters that explicitly prepare now."""
        references = self.reserve_public(destination)
        return self.prepare_reserved(*references)

    def _record_count(self) -> int:
        return 2 * len(self._reservations) + len(self._destinations) + len(self._disclosures)

    def _ref_exists(self, reference: str) -> bool:
        return (
            reference in self._destinations
            or reference in self._disclosures
            or any(reference in pair for pair in self._reservations)
        )

    def _new_ref(self) -> str:
        value = self._ref_factory()
        if not isinstance(value, str) or not RESOURCE_REF_RE.fullmatch(value):
            raise WebTransportPolicyError("web prerequisite reference is invalid")
        return value

    def destination_for(self, resource_ref: str) -> WebDestinationPrerequisite:
        with self._lock:
            value = self._destinations.get(resource_ref)
        if value is None:
            raise KeyError("web destination prerequisite was not found")
        return value

    def disclosure_for(self, resource_ref: str) -> WebDisclosurePrerequisite:
        with self._lock:
            value = self._disclosures.get(resource_ref)
        if value is None:
            raise KeyError("web disclosure prerequisite was not found")
        return value

    def revoke(self, resource_ref: object) -> bool:
        if not isinstance(resource_ref, str):
            return False
        with self._lock:
            removed = self._destinations.pop(resource_ref, None)
            removed = self._disclosures.pop(resource_ref, None) or removed
            for pair in tuple(self._reservations):
                if resource_ref in pair:
                    del self._reservations[pair]
                    removed = True
        return removed is not None


class SessionWebQuarantineStore:
    """Bounded in-memory artifact storage for one application session."""

    available = True

    def __init__(
        self,
        *,
        ref_factory: Callable[[], str] | None = None,
        maximum_artifacts: int = MAX_SESSION_WEB_ARTIFACTS,
        maximum_total_bytes: int = MAX_SESSION_WEB_ARTIFACT_BYTES,
    ) -> None:
        if ref_factory is not None and not callable(ref_factory):
            raise TypeError("web artifact reference factory is invalid")
        if (
            isinstance(maximum_artifacts, bool)
            or not isinstance(maximum_artifacts, int)
            or not 1 <= maximum_artifacts <= 1024
            or isinstance(maximum_total_bytes, bool)
            or not isinstance(maximum_total_bytes, int)
            or not 1 <= maximum_total_bytes <= 64 * 1024 * 1024
        ):
            raise ValueError("web artifact store limit is invalid")
        self._ref_factory = ref_factory or (lambda: f"TF-{secrets.token_hex(16)}")
        self._maximum_artifacts = maximum_artifacts
        self._maximum_total_bytes = maximum_total_bytes
        self._records: dict[str, WebFetchedArtifact] = {}
        self._total_bytes = 0
        self._lock = RLock()

    def store(self, artifact: WebFetchedArtifact) -> str:
        if not isinstance(artifact, WebFetchedArtifact):
            raise TypeError("web artifact is invalid")
        size = len(artifact.payload.text.encode("utf-8"))
        reference = self._ref_factory()
        if not isinstance(reference, str) or not ARTIFACT_REF_RE.fullmatch(reference):
            raise ValueError("web artifact reference is invalid")
        with self._lock:
            if (
                len(self._records) >= self._maximum_artifacts
                or self._total_bytes + size > self._maximum_total_bytes
                or reference in self._records
            ):
                raise ValueError("web artifact store capacity is exhausted")
            self._records[reference] = artifact
            self._total_bytes += size
        return reference

    def get(self, reference: object) -> WebFetchedArtifact | None:
        if not isinstance(reference, str):
            return None
        with self._lock:
            return self._records.get(reference)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection whose TCP peer is fixed separately from TLS identity."""

    def __init__(self, request: WebTransportRequest, *, timeout: float) -> None:
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(request.tls_server_name, 443, timeout=timeout, context=context)
        self._selected_address = request.selected_address
        self._tls_server_name = request.tls_server_name

    def connect(self) -> None:
        raw = socket.create_connection(
            (self._selected_address, 443), self.timeout, self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self._tls_server_name)
        except Exception:
            raw.close()
            raise


class NativeHTTPSWebTransport:
    """Pinned stdlib HTTPS GET adapter; unregistered until controlled smoke."""

    available = True

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        connection_factory: Callable | None = None,
    ) -> None:
        if not callable(clock) or (connection_factory is not None and not callable(connection_factory)):
            raise TypeError("native web transport dependency is invalid")
        self._clock = clock
        self._connection_factory = connection_factory or (
            lambda request, timeout: _PinnedHTTPSConnection(request, timeout=timeout)
        )
        self._active: dict[tuple[str, str], object] = {}
        self._lock = RLock()

    def fetch(
        self, request: WebTransportRequest, cancellation: SupervisorCancellation,
    ) -> WebTransportResponse:
        if not isinstance(request, WebTransportRequest) or not isinstance(
            cancellation, SupervisorCancellation
        ):
            raise TypeError("native web transport request is invalid")
        if cancellation.requested:
            raise WebTransportCancelled("web fetch was cancelled")
        remaining = request.authorization_deadline - float(self._clock())
        if remaining <= 0:
            raise WebTransportTimedOut("web fetch authorization expired")
        key = (request.invocation_id, request.worker_generation)
        with self._lock:
            if key in self._active:
                raise WebTransportPolicyError("web transport request is already active")
        connection = self._connection_factory(request, remaining)
        with self._lock:
            if key in self._active:
                connection.close()
                raise WebTransportPolicyError("web transport request is already active")
            self._active[key] = connection
        try:
            parsed = urlsplit(request.destination.url)
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.putrequest("GET", target, skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", request.http_host)
            connection.putheader("Accept", "text/html, text/plain, text/markdown")
            connection.putheader("Accept-Encoding", "identity")
            connection.putheader("User-Agent", "StarFur-Forge/1 web.fetch")
            connection.putheader("Connection", "close")
            connection.endheaders()
            # Capture the actual TLS peer before ``getresponse``. Python's
            # HTTP client may clear ``connection.sock`` immediately when the
            # server honors our deliberate ``Connection: close`` request.
            peer = getattr(connection, "sock", None)
            if peer is None or not hasattr(peer, "getpeername"):
                raise WebTransportPolicyError("web transport peer is unavailable")
            connected_address = str(ipaddress.ip_address(peer.getpeername()[0]))
            response = connection.getresponse()
            if response.status != 200:
                raise WebTransportPolicyError("web response status is unsupported")
            media_type = self._media_type(self._single_header(response, "Content-Type"))
            content_encoding = (self._single_header(response, "Content-Encoding") or "identity").casefold()
            if content_encoding != "identity":
                raise WebTransportPolicyError("native web content encoding is unsupported")
            declared = self._content_length(self._single_header(response, "Content-Length"))
            transfer_encoding = self._single_header(response, "Transfer-Encoding")
            if transfer_encoding is not None and transfer_encoding.casefold() != "chunked":
                raise WebTransportPolicyError("native web transfer encoding is unsupported")
            if transfer_encoding is not None and declared is not None:
                # A framing body and a declared entity length are ambiguous at
                # this boundary; do not let a conflicting header weaken caps.
                raise WebTransportPolicyError("native web response length framing is ambiguous")
            chunks: list[WebDecodedChunk] = []
            total = 0
            while True:
                if cancellation.requested:
                    raise WebTransportCancelled("web fetch was cancelled")
                remaining = request.authorization_deadline - float(self._clock())
                if remaining <= 0:
                    raise WebTransportTimedOut("web fetch timed out")
                sock = getattr(connection, "sock", None)
                if sock is not None and hasattr(sock, "settimeout"):
                    sock.settimeout(remaining)
                data = response.read(NATIVE_WEB_READ_CHUNK_BYTES)
                if not data:
                    break
                if not isinstance(data, bytes):
                    raise WebTransportPolicyError("web response body is invalid")
                total += len(data)
                if total > MAX_WEB_ENCODED_BYTES:
                    raise WebTransportPolicyError("web response body exceeds its limit")
                # ``http.client`` has removed permitted HTTP chunk framing.
                # With content encoding fixed to identity, this exact entity
                # body count remains the bounded input to the response parser.
                chunks.append(WebDecodedChunk(data, len(data)))
            if not chunks:
                raise WebTransportPolicyError("web response body is empty")
            if declared is not None and declared != total:
                raise WebTransportPolicyError("web response length is inconsistent")
            return WebTransportResponse(
                1,
                request.invocation_id,
                request.binding_fingerprint,
                request.worker_generation,
                connected_address,
                WebResponseMetadata(1, 200, media_type, "identity", total),
                tuple(chunks),
            )
        except WebTransportPolicyError:
            raise
        except (socket.timeout, TimeoutError) as error:
            raise WebTransportTimedOut("web fetch timed out") from error
        except Exception as error:
            if cancellation.requested:
                raise WebTransportCancelled("web fetch was cancelled") from error
            raise RuntimeError("native web transport failed") from error
        finally:
            try:
                connection.close()
            finally:
                with self._lock:
                    self._active.pop(key, None)

    def request_cancel(self, request: WebTransportRequest) -> None:
        if not isinstance(request, WebTransportRequest):
            raise TypeError("native web cancellation request is invalid")
        key = (request.invocation_id, request.worker_generation)
        with self._lock:
            connection = self._active.get(key)
        if connection is not None:
            connection.close()

    @staticmethod
    def _single_header(response, name: str) -> str | None:
        values = [
            value.strip() for key, value in response.getheaders()
            if isinstance(key, str) and key.casefold() == name.casefold()
        ]
        if len(values) > 1:
            raise WebTransportPolicyError("duplicate web response header is forbidden")
        if values and (
            len(values[0]) > 1024
            or "\r" in values[0]
            or "\n" in values[0]
            or any(ord(character) < 32 and character != "\t" for character in values[0])
        ):
            raise WebTransportPolicyError("web response header value is invalid")
        return values[0] if values else None

    @staticmethod
    def _media_type(value: str | None) -> str:
        if not isinstance(value, str) or not value:
            raise WebTransportPolicyError("web response content type is missing")
        parts = [item.strip() for item in value.split(";")]
        media_type = parts[0].casefold()
        if media_type not in _SUPPORTED_NATIVE_MEDIA:
            raise WebTransportPolicyError("native web media type is unsupported")
        for parameter in parts[1:]:
            if parameter.casefold() not in {"charset=utf-8", 'charset="utf-8"'}:
                raise WebTransportPolicyError("web response content type parameter is unsupported")
        return media_type

    @staticmethod
    def _content_length(value: str | None) -> int | None:
        if value is None:
            return None
        if not value.isascii() or not value.isdigit():
            raise WebTransportPolicyError("web response content length is invalid")
        length = int(value)
        if not 0 <= length <= MAX_WEB_ENCODED_BYTES:
            raise WebTransportPolicyError("web response content length exceeds its limit")
        return length


@dataclass(frozen=True)
class NativeWebToolRuntime:
    """One session-local native composition; construction performs no I/O."""

    prerequisites: SessionWebPrerequisiteStore
    quarantine: SessionWebQuarantineStore
    supervisor: WebFetchSupervisor


def build_native_web_tool_runtime() -> NativeWebToolRuntime:
    """Construct the explicit local-CLI adapter without resolving or fetching."""
    prerequisites = SessionWebPrerequisiteStore(NativeWebResolver())
    quarantine = SessionWebQuarantineStore()
    supervisor = WebFetchSupervisor(
        prerequisites,
        NativeHTTPSWebTransport(),
        quarantine,
        clock=time.time,
    )
    return NativeWebToolRuntime(prerequisites, quarantine, supervisor)


__all__ = [
    "MAX_SESSION_WEB_ARTIFACTS",
    "MAX_SESSION_WEB_ARTIFACT_BYTES",
    "MAX_SESSION_WEB_PREREQUISITES",
    "NATIVE_WEB_DNS_LIFETIME_SECONDS",
    "NATIVE_WEB_RESOLVER_REVISION",
    "NativeWebToolRuntime",
    "NativeHTTPSWebTransport",
    "NativeWebResolver",
    "SessionWebPrerequisiteStore",
    "SessionWebQuarantineStore",
    "build_native_web_tool_runtime",
]
