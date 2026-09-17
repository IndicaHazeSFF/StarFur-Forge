"""Fake-ready, live-disabled execution seam for ``web.search``.

This composes exact preflight evidence, one injected search adapter, strict
provider-neutral candidates, and an injected session quarantine.  It contains
no real search service, HTTP, DNS, credentials, persistence, or app wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from threading import RLock
from typing import Protocol

from pipeline.sandbox_supervisor import (
    SUPERVISOR_SCHEMA_VERSION, SupervisorCancellation, SupervisorCancelReceipt,
    SupervisorCompletion, SupervisorLaunchRequest, SupervisorRunStatus,
)
from pipeline.tool_contracts import (
    ARTIFACT_REF_RE, ToolProposal, ToolResult, validate_web_search_arguments,
)
from pipeline.tool_grants import (
    INVOCATION_ID_RE, ToolInvocation, tool_proposal_digest,
)
from pipeline.tool_web_search import (
    MAX_WEB_SEARCH_RESULTS, WebSearchArtifact, WebSearchCandidate,
)
from pipeline.tool_web_search_preflight import (
    WebSearchDisclosurePrerequisite, WebSearchServicePrerequisite,
    evaluate_web_search_preflight,
)


WEB_SEARCH_CONNECTOR_SCHEMA_VERSION = 1
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_WORKER_RE = re.compile(r"^TW-[A-Za-z0-9_-]{1,64}$")


def _deadline(value: object) -> float:
    if (
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(float(value)) or not 0 <= float(value) < 1e12
    ):
        raise ValueError("web search deadline is invalid")
    return float(value)


class WebSearchAdapterCancelled(RuntimeError):
    """The adapter verified that its request stopped after cancellation."""


class WebSearchAdapterTimedOut(RuntimeError):
    """The adapter verified that its request stopped after timeout."""


class WebSearchAdapterPolicyError(RuntimeError):
    """The adapter rejected the request before an external effect."""


@dataclass(frozen=True)
class WebSearchRequest:
    """One exact internal request for a trusted search adapter."""

    schema_version: int
    invocation_id: str
    binding_fingerprint: str
    worker_generation: str
    service_id: str
    query: str
    query_sha256: str
    maximum_results: int
    authorization_deadline: float

    def __post_init__(self) -> None:
        if self.schema_version != WEB_SEARCH_CONNECTOR_SCHEMA_VERSION:
            raise ValueError("web search request schema version is unsupported")
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ValueError("web search request invocation is invalid")
        if not isinstance(self.binding_fingerprint, str) or not _DIGEST_RE.fullmatch(self.binding_fingerprint):
            raise ValueError("web search request binding is invalid")
        if not isinstance(self.worker_generation, str) or not _WORKER_RE.fullmatch(self.worker_generation):
            raise ValueError("web search request worker generation is invalid")
        if not isinstance(self.service_id, str) or not _SERVICE_RE.fullmatch(self.service_id):
            raise ValueError("web search request service is invalid")
        query = validate_web_search_arguments({"query": self.query})["query"]
        if self.query_sha256 != hashlib.sha256(query.encode("utf-8")).hexdigest():
            raise ValueError("web search request query binding is invalid")
        if (
            isinstance(self.maximum_results, bool)
            or not isinstance(self.maximum_results, int)
            or not 1 <= self.maximum_results <= MAX_WEB_SEARCH_RESULTS
        ):
            raise ValueError("web search request result limit is invalid")
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "authorization_deadline", _deadline(self.authorization_deadline))

    @classmethod
    def from_launch(cls, launch, *, service_id, query, maximum_results):
        normalized = validate_web_search_arguments({"query": query})["query"]
        return cls(
            1, launch.invocation_id, launch.binding_fingerprint,
            launch.worker_generation, service_id, normalized,
            hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            maximum_results, launch.authorization_deadline,
        )


@dataclass(frozen=True)
class WebSearchResponse:
    """Strict response already translated by a trusted adapter."""

    schema_version: int
    invocation_id: str
    binding_fingerprint: str
    worker_generation: str
    service_id: str
    query_sha256: str
    results: tuple[WebSearchCandidate, ...]

    def __post_init__(self) -> None:
        if self.schema_version != WEB_SEARCH_CONNECTOR_SCHEMA_VERSION:
            raise ValueError("web search response schema version is unsupported")
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ValueError("web search response invocation is invalid")
        if not isinstance(self.binding_fingerprint, str) or not _DIGEST_RE.fullmatch(self.binding_fingerprint):
            raise ValueError("web search response binding is invalid")
        if not isinstance(self.worker_generation, str) or not _WORKER_RE.fullmatch(self.worker_generation):
            raise ValueError("web search response worker generation is invalid")
        if not isinstance(self.service_id, str) or not _SERVICE_RE.fullmatch(self.service_id):
            raise ValueError("web search response service is invalid")
        if not isinstance(self.query_sha256, str) or not _DIGEST_RE.fullmatch(self.query_sha256):
            raise ValueError("web search response query digest is invalid")
        results = tuple(self.results)
        if not results or len(results) > MAX_WEB_SEARCH_RESULTS or not all(
            isinstance(item, WebSearchCandidate) for item in results
        ):
            raise ValueError("web search response results are invalid")
        object.__setattr__(self, "results", results)

    def matches(self, request: WebSearchRequest) -> bool:
        return isinstance(request, WebSearchRequest) and (
            self.invocation_id == request.invocation_id
            and self.binding_fingerprint == request.binding_fingerprint
            and self.worker_generation == request.worker_generation
            and self.service_id == request.service_id
            and self.query_sha256 == request.query_sha256
            and len(self.results) <= request.maximum_results
        )


class WebSearchPrerequisiteSource(Protocol):
    @property
    def available(self) -> bool: ...

    def service_for(self, resource_ref: str) -> WebSearchServicePrerequisite: ...

    def disclosure_for(self, resource_ref: str) -> WebSearchDisclosurePrerequisite: ...


class WebSearchAdapter(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def service_id(self) -> str: ...

    def search(self, request: WebSearchRequest, cancellation: SupervisorCancellation) -> WebSearchResponse: ...

    def request_cancel(self, request: WebSearchRequest) -> None: ...


class WebSearchQuarantineSink(Protocol):
    @property
    def available(self) -> bool: ...

    def store(self, artifact: WebSearchArtifact) -> str: ...


class DisabledWebSearchSupervisor:
    available = False

    def supports(self, tool_id, tool_version):
        return False

    def run(self, request, invocation, proposal, cancellation):
        raise RuntimeError("web search execution is disabled")

    def request_cancel(self, request, cancellation):
        raise RuntimeError("web search execution is disabled")

    def query(self, request):
        raise RuntimeError("web search execution is disabled")


class WebSearchSupervisor:
    """Compose fake/trusted dependencies under exact Core bindings."""

    def __init__(self, prerequisites, adapter, quarantine, *, clock) -> None:
        if not callable(clock):
            raise TypeError("web search supervisor clock is invalid")
        self._prerequisites = prerequisites
        self._adapter = adapter
        self._quarantine = quarantine
        self._clock = clock
        self._active = set()
        self._active_requests = {}
        self._lock = RLock()

    @staticmethod
    def _is_available(component):
        try:
            return component.available is True
        except Exception:
            return False

    @property
    def available(self):
        return all(self._is_available(item) for item in (
            self._prerequisites, self._adapter, self._quarantine,
        ))

    def supports(self, tool_id, tool_version):
        return self.available and (tool_id, tool_version) == ("web.search", 1)

    @staticmethod
    def _result(request, invocation, outcome, category):
        result = ToolResult(
            1, invocation.invocation_id, "web.search", 1,
            outcome, None, "", "", category,
        )
        return SupervisorCompletion.from_request(
            request, outcome=outcome, stop_state="verified_stopped", result=result,
        )

    def run(self, request, invocation, proposal, cancellation):
        if not self.supports("web.search", 1):
            raise RuntimeError("web search supervisor is unavailable")
        if (
            not isinstance(request, SupervisorLaunchRequest)
            or not isinstance(invocation, ToolInvocation)
            or not isinstance(proposal, ToolProposal)
            or not isinstance(cancellation, SupervisorCancellation)
            or not request.matches_invocation(invocation)
            or (proposal.tool_id, proposal.tool_version) != ("web.search", 1)
            or invocation.operation_digest != tool_proposal_digest(proposal)
        ):
            raise ValueError("web search supervisor binding is invalid")
        key = (request.invocation_id, request.worker_generation)
        with self._lock:
            if key in self._active:
                raise RuntimeError("web search worker generation is already active")
            self._active.add(key)
        try:
            if cancellation.requested:
                return self._result(request, invocation, "cancelled", "cancelled")
            commitments = {item.requirement_id: item for item in request.prerequisite_bindings}
            if set(commitments) != {"network.search", "network.disclosure"}:
                return self._result(request, invocation, "failed", "validation_failed")
            try:
                service = self._prerequisites.service_for(commitments["network.search"].resource_ref)
                disclosure = self._prerequisites.disclosure_for(
                    commitments["network.disclosure"].resource_ref,
                )
            except Exception:
                return self._result(request, invocation, "failed", "validation_failed")
            preflight = evaluate_web_search_preflight(
                request, proposal, service, disclosure, now_epoch=self._clock(),
            )
            if not preflight.permitted:
                return self._result(request, invocation, "failed", "permission_denied")
            try:
                adapter_service = self._adapter.service_id
            except Exception:
                return self._result(request, invocation, "failed", "backend_unavailable")
            if adapter_service != preflight.service_id:
                return self._result(request, invocation, "failed", "permission_denied")
            if cancellation.requested:
                return self._result(request, invocation, "cancelled", "cancelled")
            if self._clock() >= request.authorization_deadline:
                return self._result(request, invocation, "timed_out", "timed_out")
            query = validate_web_search_arguments(proposal.arguments)["query"]
            adapter_request = WebSearchRequest.from_launch(
                request, service_id=preflight.service_id, query=query,
                maximum_results=preflight.maximum_results,
            )
            with self._lock:
                self._active_requests[key] = adapter_request
            try:
                response = self._adapter.search(adapter_request, cancellation)
            except WebSearchAdapterCancelled:
                return self._result(request, invocation, "cancelled", "cancelled")
            except WebSearchAdapterTimedOut:
                return self._result(request, invocation, "timed_out", "timed_out")
            except WebSearchAdapterPolicyError:
                return self._result(request, invocation, "failed", "execution_failed")
            except Exception:
                return SupervisorCompletion.from_request(
                    request, outcome="outcome_unknown", stop_state="not_verified",
                )
            finally:
                with self._lock:
                    self._active_requests.pop(key, None)
            if cancellation.requested:
                return self._result(request, invocation, "cancelled", "cancelled")
            if self._clock() >= request.authorization_deadline:
                return self._result(request, invocation, "timed_out", "timed_out")
            if not isinstance(response, WebSearchResponse) or not response.matches(adapter_request):
                return self._result(request, invocation, "failed", "execution_failed")
            try:
                artifact = WebSearchArtifact.create(
                    adapter_request.query_sha256, adapter_request.service_id, response.results,
                )
            except Exception:
                return self._result(request, invocation, "failed", "execution_failed")
            try:
                artifact_ref = self._quarantine.store(artifact)
            except Exception:
                return SupervisorCompletion.from_request(
                    request, outcome="outcome_unknown", stop_state="not_verified",
                )
            if not isinstance(artifact_ref, str) or not ARTIFACT_REF_RE.fullmatch(artifact_ref):
                return SupervisorCompletion.from_request(
                    request, outcome="outcome_unknown", stop_state="not_verified",
                )
            result = ToolResult(
                1, invocation.invocation_id, "web.search", 1,
                "completed", None, "", "", None, (artifact_ref,),
            )
            return SupervisorCompletion.from_request(
                request, outcome="completed", stop_state="verified_stopped", result=result,
            )
        finally:
            with self._lock:
                self._active.discard(key)
                self._active_requests.pop(key, None)

    def request_cancel(self, request, cancellation):
        if not isinstance(request, SupervisorLaunchRequest) or not isinstance(
            cancellation, SupervisorCancellation
        ):
            raise TypeError("web search cancellation request is invalid")
        cancellation.request()
        key = (request.invocation_id, request.worker_generation)
        with self._lock:
            adapter_request = self._active_requests.get(key)
        if adapter_request is not None:
            self._adapter.request_cancel(adapter_request)
        return SupervisorCancelReceipt(
            SUPERVISOR_SCHEMA_VERSION, request.invocation_id,
            request.worker_generation, "requested",
        )

    def query(self, request):
        if not isinstance(request, SupervisorLaunchRequest):
            raise TypeError("web search status request is invalid")
        with self._lock:
            state = "running" if (
                request.invocation_id, request.worker_generation,
            ) in self._active else "unknown"
        return SupervisorRunStatus.from_request(request, state=state)


__all__ = [
    "DisabledWebSearchSupervisor", "WEB_SEARCH_CONNECTOR_SCHEMA_VERSION",
    "WebSearchAdapter", "WebSearchAdapterCancelled", "WebSearchAdapterPolicyError",
    "WebSearchAdapterTimedOut", "WebSearchPrerequisiteSource",
    "WebSearchQuarantineSink", "WebSearchRequest", "WebSearchResponse",
    "WebSearchSupervisor",
]
