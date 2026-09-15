"""Fake-ready, live-disabled execution seam for ``web.fetch``.

The supervisor composes exact preflight evidence, one injected transport, the
bounded response collector, conservative text preparation, and one injected
quarantine sink. This module contains no DNS, socket, HTTP, proxy, credential,
cookie, provider, or durable-storage implementation. Real adapters remain a
separate native smoke and security-review gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import math
import re
from threading import RLock
from typing import Protocol
from urllib.parse import urlsplit

from pipeline.sandbox_supervisor import (
    SUPERVISOR_SCHEMA_VERSION,
    SupervisorCancellation,
    SupervisorCancelReceipt,
    SupervisorCompletion,
    SupervisorLaunchRequest,
    SupervisorRunStatus,
)
from pipeline.tool_contracts import ARTIFACT_REF_RE, ToolProposal, ToolResult
from pipeline.tool_grants import (
    INVOCATION_ID_RE,
    ToolInvocation,
    tool_invocation_fingerprint,
    tool_proposal_digest,
)
from pipeline.tool_web_parser import QuarantinedWebText, prepare_quarantined_web_text
from pipeline.tool_web_policy import WebDestination, evaluate_web_connection
from pipeline.tool_web_preflight import (
    WebDestinationPrerequisite,
    WebDisclosurePrerequisite,
    evaluate_web_fetch_preflight,
)
from pipeline.tool_web_response import (
    MAX_WEB_DECODED_BYTES,
    MAX_WEB_ENCODED_BYTES,
    WebResponseCollector,
    WebResponseMetadata,
)


WEB_CONNECTOR_SCHEMA_VERSION = 1
MAX_WEB_TRANSPORT_CHUNKS = 1024
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_WORKER_RE = re.compile(r"^TW-[A-Za-z0-9_-]{1,64}$")


class WebTransportPolicyError(RuntimeError):
    """A bounded transport policy rejection after a verified local stop."""


class WebTransportCancelled(RuntimeError):
    """The transport verified its local request was stopped after cancellation."""


class WebTransportTimedOut(RuntimeError):
    """The transport verified its local request was stopped after timeout."""


def _deadline(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 <= float(value) < 1e12
    ):
        raise ValueError("web transport deadline is invalid")
    return float(value)


@dataclass(frozen=True)
class WebTransportRequest:
    """One exact no-body HTTPS GET request for an injected trusted transport."""

    schema_version: int
    invocation_id: str
    binding_fingerprint: str
    worker_generation: str
    destination: WebDestination
    selected_address: str
    tls_server_name: str
    http_host: str
    authorization_deadline: float
    max_encoded_bytes: int = MAX_WEB_ENCODED_BYTES
    max_decoded_bytes: int = MAX_WEB_DECODED_BYTES
    method: str = "GET"
    follow_redirects: bool = False
    use_environment_proxy: bool = False
    send_credentials: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_CONNECTOR_SCHEMA_VERSION:
            raise ValueError("web transport request schema version is unsupported")
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ValueError("web transport invocation is invalid")
        if not isinstance(self.binding_fingerprint, str) or not _DIGEST_RE.fullmatch(
            self.binding_fingerprint
        ):
            raise ValueError("web transport binding fingerprint is invalid")
        if not isinstance(self.worker_generation, str) or not _WORKER_RE.fullmatch(self.worker_generation):
            raise ValueError("web transport worker generation is invalid")
        if not isinstance(self.destination, WebDestination):
            raise TypeError("web transport destination is invalid")
        try:
            address = ipaddress.ip_address(self.selected_address)
        except (TypeError, ValueError) as error:
            raise ValueError("web transport selected address is invalid") from error
        if str(address) != self.selected_address or not address.is_global:
            raise ValueError("web transport selected address is forbidden")
        if self.tls_server_name != self.destination.host:
            raise ValueError("web transport TLS server name is inconsistent")
        if self.http_host != urlsplit(self.destination.url).netloc:
            raise ValueError("web transport HTTP host is inconsistent")
        object.__setattr__(self, "authorization_deadline", _deadline(self.authorization_deadline))
        if self.max_encoded_bytes != MAX_WEB_ENCODED_BYTES:
            raise ValueError("web transport encoded-byte policy is unsupported")
        if self.max_decoded_bytes != MAX_WEB_DECODED_BYTES:
            raise ValueError("web transport decoded-byte policy is unsupported")
        if self.method != "GET":
            raise ValueError("web transport method is unsupported")
        if self.follow_redirects is not False:
            raise ValueError("automatic web redirects are forbidden")
        if self.use_environment_proxy is not False:
            raise ValueError("environment web proxies are forbidden")
        if self.send_credentials is not False:
            raise ValueError("web transport credentials are forbidden")

    @classmethod
    def from_launch(
        cls,
        launch: SupervisorLaunchRequest,
        destination: WebDestination,
        *,
        selected_address: str,
    ) -> "WebTransportRequest":
        return cls(
            1,
            launch.invocation_id,
            launch.binding_fingerprint,
            launch.worker_generation,
            destination,
            selected_address,
            destination.host,
            urlsplit(destination.url).netloc,
            launch.authorization_deadline,
        )


@dataclass(frozen=True)
class WebDecodedChunk:
    data: bytes
    encoded_bytes_consumed: int

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise TypeError("web transport decoded chunk is invalid")
        if (
            isinstance(self.encoded_bytes_consumed, bool)
            or not isinstance(self.encoded_bytes_consumed, int)
            or not 0 <= self.encoded_bytes_consumed <= MAX_WEB_ENCODED_BYTES
        ):
            raise ValueError("web transport encoded chunk count is invalid")


@dataclass(frozen=True)
class WebTransportResponse:
    """Bound response from a transport that disabled automatic redirects."""

    schema_version: int
    invocation_id: str
    binding_fingerprint: str
    worker_generation: str
    connected_address: str
    metadata: WebResponseMetadata
    chunks: tuple[WebDecodedChunk, ...]

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_CONNECTOR_SCHEMA_VERSION:
            raise ValueError("web transport response schema version is unsupported")
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ValueError("web transport response invocation is invalid")
        if not isinstance(self.binding_fingerprint, str) or not _DIGEST_RE.fullmatch(
            self.binding_fingerprint
        ):
            raise ValueError("web transport response binding is invalid")
        if not isinstance(self.worker_generation, str) or not _WORKER_RE.fullmatch(self.worker_generation):
            raise ValueError("web transport response worker generation is invalid")
        try:
            address = ipaddress.ip_address(self.connected_address)
        except (TypeError, ValueError) as error:
            raise ValueError("web transport connected address is invalid") from error
        if str(address) != self.connected_address:
            raise ValueError("web transport connected address must be canonical")
        if not isinstance(self.metadata, WebResponseMetadata):
            raise TypeError("web transport response metadata is invalid")
        chunks = tuple(self.chunks)
        if not 1 <= len(chunks) <= MAX_WEB_TRANSPORT_CHUNKS or not all(
            isinstance(item, WebDecodedChunk) for item in chunks
        ):
            raise ValueError("web transport response chunks are invalid")
        object.__setattr__(self, "chunks", chunks)

    def matches(self, request: WebTransportRequest) -> bool:
        return isinstance(request, WebTransportRequest) and (
            self.invocation_id == request.invocation_id
            and self.binding_fingerprint == request.binding_fingerprint
            and self.worker_generation == request.worker_generation
        )


class WebFetchPrerequisiteSource(Protocol):
    @property
    def available(self) -> bool: ...

    def destination_for(self, resource_ref: str) -> WebDestinationPrerequisite: ...

    def disclosure_for(self, resource_ref: str) -> WebDisclosurePrerequisite: ...


class WebFetchTransport(Protocol):
    @property
    def available(self) -> bool: ...

    def fetch(
        self, request: WebTransportRequest, cancellation: SupervisorCancellation,
    ) -> WebTransportResponse: ...

    def request_cancel(self, request: WebTransportRequest) -> None: ...


@dataclass(frozen=True)
class WebFetchedArtifact:
    """Internal provenance envelope for one quarantined fetched source."""

    schema_version: int
    invocation_fingerprint: str
    destination: WebDestination
    connected_address: str
    fetched_at_epoch: float
    destination_evidence_sha256: str
    disclosure_evidence_sha256: str
    payload: QuarantinedWebText

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_CONNECTOR_SCHEMA_VERSION:
            raise ValueError("web fetched artifact schema version is unsupported")
        for label, digest in (
            ("invocation fingerprint", self.invocation_fingerprint),
            ("destination evidence", self.destination_evidence_sha256),
            ("disclosure evidence", self.disclosure_evidence_sha256),
        ):
            if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
                raise ValueError(f"web fetched artifact {label} is invalid")
        if not isinstance(self.destination, WebDestination):
            raise TypeError("web fetched artifact destination is invalid")
        try:
            address = ipaddress.ip_address(self.connected_address)
        except (TypeError, ValueError) as error:
            raise ValueError("web fetched artifact address is invalid") from error
        if str(address) != self.connected_address or not address.is_global:
            raise ValueError("web fetched artifact address is forbidden")
        object.__setattr__(self, "fetched_at_epoch", _deadline(self.fetched_at_epoch))
        if not isinstance(self.payload, QuarantinedWebText):
            raise TypeError("web fetched artifact payload is invalid")


class WebQuarantineSink(Protocol):
    @property
    def available(self) -> bool: ...

    def store(self, artifact: WebFetchedArtifact) -> str: ...


class DisabledWebFetchSupervisor:
    """Default web executor: exact operation known, all execution denied."""

    available = False

    def supports(self, tool_id, tool_version):
        return False

    def run(self, request, invocation, proposal, cancellation):
        raise RuntimeError("web fetch execution is disabled")

    def request_cancel(self, request, cancellation):
        raise RuntimeError("web fetch execution is disabled")

    def query(self, request):
        raise RuntimeError("web fetch execution is disabled")


class WebFetchSupervisor:
    """Compose injected fake/trusted adapters under exact Core bindings."""

    def __init__(
        self,
        prerequisites: WebFetchPrerequisiteSource,
        transport: WebFetchTransport,
        quarantine: WebQuarantineSink,
        *,
        clock,
    ) -> None:
        if not callable(clock):
            raise TypeError("web fetch supervisor clock is invalid")
        self._prerequisites = prerequisites
        self._transport = transport
        self._quarantine = quarantine
        self._clock = clock
        self._active: set[tuple[str, str]] = set()
        self._active_transports: dict[tuple[str, str], WebTransportRequest] = {}
        self._lock = RLock()

    @property
    def available(self) -> bool:
        return all(self._is_available(item) for item in (
            self._prerequisites, self._transport, self._quarantine,
        ))

    def supports(self, tool_id, tool_version):
        return self.available and (tool_id, tool_version) == ("web.fetch", 1)

    @staticmethod
    def _is_available(component) -> bool:
        try:
            return component.available is True
        except Exception:
            return False

    @staticmethod
    def _failed(request, invocation, category="validation_failed"):
        result = ToolResult(
            1, invocation.invocation_id, "web.fetch", 1,
            "failed", None, "", "", category,
        )
        return SupervisorCompletion.from_request(
            request, outcome="failed", stop_state="verified_stopped", result=result,
        )

    def run(self, request, invocation, proposal, cancellation):
        if not self.supports("web.fetch", 1):
            raise RuntimeError("web fetch supervisor is unavailable")
        if (
            not isinstance(request, SupervisorLaunchRequest)
            or not isinstance(invocation, ToolInvocation)
            or not isinstance(proposal, ToolProposal)
            or not isinstance(cancellation, SupervisorCancellation)
            or not request.matches_invocation(invocation)
            or (proposal.tool_id, proposal.tool_version) != ("web.fetch", 1)
            or invocation.operation_digest != tool_proposal_digest(proposal)
        ):
            raise ValueError("web fetch supervisor binding is invalid")
        key = (request.invocation_id, request.worker_generation)
        with self._lock:
            if key in self._active:
                raise RuntimeError("web fetch worker generation is already active")
            self._active.add(key)
        try:
            if cancellation.requested:
                return self._cancelled(request, invocation)
            commitments = {item.requirement_id: item for item in request.prerequisite_bindings}
            if set(commitments) != {"network.destination", "network.disclosure"}:
                return self._failed(request, invocation)
            destination = WebDestination(1, proposal.arguments["url"])
            try:
                destination_evidence = self._prerequisites.destination_for(
                    commitments["network.destination"].resource_ref,
                )
                disclosure_evidence = self._prerequisites.disclosure_for(
                    commitments["network.disclosure"].resource_ref,
                )
            except Exception:
                return self._failed(request, invocation)
            preflight = evaluate_web_fetch_preflight(
                request, destination, destination_evidence, disclosure_evidence,
                now_epoch=self._clock(),
            )
            if not preflight.permitted:
                return self._failed(request, invocation, "permission_denied")
            if cancellation.requested or self._clock() >= request.authorization_deadline:
                return self._cancelled(request, invocation) if cancellation.requested else self._timed_out(
                    request, invocation,
                )
            transport_request = WebTransportRequest.from_launch(
                request, destination, selected_address=preflight.approved_addresses[0],
            )
            with self._lock:
                self._active_transports[key] = transport_request
            try:
                response = self._transport.fetch(transport_request, cancellation)
            except WebTransportCancelled:
                return self._cancelled(request, invocation)
            except WebTransportTimedOut:
                return self._timed_out(request, invocation)
            except WebTransportPolicyError:
                return self._failed(request, invocation, "execution_failed")
            except Exception:
                return SupervisorCompletion.from_request(
                    request, outcome="outcome_unknown", stop_state="not_verified",
                )
            finally:
                with self._lock:
                    self._active_transports.pop(key, None)
            if cancellation.requested:
                return self._cancelled(request, invocation)
            if self._clock() >= request.authorization_deadline:
                return self._timed_out(request, invocation)
            if not isinstance(response, WebTransportResponse) or not response.matches(transport_request):
                return self._failed(request, invocation, "execution_failed")
            connected = evaluate_web_connection(
                destination,
                destination_evidence.resolution,
                connected_address=response.connected_address,
                now_epoch=self._clock(),
            )
            if not connected.permitted or connected.selected_address != transport_request.selected_address:
                return self._failed(request, invocation, "permission_denied")
            try:
                collector = WebResponseCollector(response.metadata)
                for chunk in response.chunks:
                    collector.append(
                        chunk.data, encoded_bytes_consumed=chunk.encoded_bytes_consumed,
                    )
                prepared = prepare_quarantined_web_text(collector.finalize())
            except Exception:
                return self._failed(request, invocation, "execution_failed")
            try:
                artifact_ref = self._quarantine.store(
                    WebFetchedArtifact(
                        1,
                        tool_invocation_fingerprint(invocation),
                        destination,
                        connected.selected_address,
                        self._clock(),
                        destination_evidence.evidence_sha256,
                        disclosure_evidence.evidence_sha256,
                        prepared,
                    )
                )
            except Exception:
                return SupervisorCompletion.from_request(
                    request, outcome="outcome_unknown", stop_state="not_verified",
                )
            if not isinstance(artifact_ref, str) or not ARTIFACT_REF_RE.fullmatch(artifact_ref):
                return SupervisorCompletion.from_request(
                    request, outcome="outcome_unknown", stop_state="not_verified",
                )
            result = ToolResult(
                1, invocation.invocation_id, "web.fetch", 1,
                "completed", None, "", "", None, (artifact_ref,),
            )
            return SupervisorCompletion.from_request(
                request, outcome="completed", stop_state="verified_stopped", result=result,
            )
        finally:
            with self._lock:
                self._active.discard(key)
                self._active_transports.pop(key, None)

    @staticmethod
    def _cancelled(request, invocation):
        result = ToolResult(
            1, invocation.invocation_id, "web.fetch", 1,
            "cancelled", None, "", "", "cancelled",
        )
        return SupervisorCompletion.from_request(
            request, outcome="cancelled", stop_state="verified_stopped", result=result,
        )

    @staticmethod
    def _timed_out(request, invocation):
        result = ToolResult(
            1, invocation.invocation_id, "web.fetch", 1,
            "timed_out", None, "", "", "timed_out",
        )
        return SupervisorCompletion.from_request(
            request, outcome="timed_out", stop_state="verified_stopped", result=result,
        )

    def request_cancel(self, request, cancellation):
        if not isinstance(request, SupervisorLaunchRequest) or not isinstance(
            cancellation, SupervisorCancellation
        ):
            raise TypeError("web fetch cancellation request is invalid")
        cancellation.request()
        key = (request.invocation_id, request.worker_generation)
        with self._lock:
            transport_request = self._active_transports.get(key)
        if transport_request is not None:
            self._transport.request_cancel(transport_request)
        return SupervisorCancelReceipt(
            SUPERVISOR_SCHEMA_VERSION, request.invocation_id,
            request.worker_generation, "requested",
        )

    def query(self, request):
        if not isinstance(request, SupervisorLaunchRequest):
            raise TypeError("web fetch status request is invalid")
        with self._lock:
            state = "running" if (
                request.invocation_id, request.worker_generation,
            ) in self._active else "unknown"
        return SupervisorRunStatus.from_request(request, state=state)


__all__ = [
    "DisabledWebFetchSupervisor",
    "MAX_WEB_TRANSPORT_CHUNKS",
    "WEB_CONNECTOR_SCHEMA_VERSION",
    "WebDecodedChunk",
    "WebFetchPrerequisiteSource",
    "WebFetchSupervisor",
    "WebFetchTransport",
    "WebFetchedArtifact",
    "WebQuarantineSink",
    "WebTransportRequest",
    "WebTransportResponse",
    "WebTransportCancelled",
    "WebTransportPolicyError",
    "WebTransportTimedOut",
]
