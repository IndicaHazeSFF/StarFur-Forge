"""Session-only prerequisite preparation for a future ``web.search`` runtime.

This is a Core storage and binding adapter, not a search adapter.  It reserves
an explicitly public query with its factual-research decision, then accepts only
one separately supplied, exact configured service observation.  It performs no
provider probe, network request, credential lookup, execution, or persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets
from threading import RLock
from typing import Callable

from pipeline.factual_research_policy import FactualResearchDecision
from pipeline.research_discovery import (
    ResearchDiscoveryIntent,
    evaluate_research_discovery,
)
from pipeline.tool_grants import RESOURCE_REF_RE
from pipeline.tool_web_search import MAX_WEB_SEARCH_RESULTS
from pipeline.tool_web_search import SessionWebSearchArtifactStore
from pipeline.tool_web_search_connector import WebSearchSupervisor
from pipeline.tool_web_search_preflight import (
    WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
    WebSearchDisclosurePrerequisite,
    WebSearchServicePrerequisite,
)


MAX_SESSION_WEB_SEARCH_PREREQUISITES = 64


@dataclass(frozen=True)
class _SearchReservation:
    query: str
    intent: ResearchDiscoveryIntent
    discovery: object


@dataclass(frozen=True)
class LocalWebSearchRuntime:
    """One injected local composition; construction itself performs no I/O."""

    prerequisites: "SessionWebSearchPrerequisiteStore"
    quarantine: SessionWebSearchArtifactStore
    supervisor: WebSearchSupervisor
    service_observation: Callable[[str], WebSearchServicePrerequisite]


class SessionWebSearchPrerequisiteStore:
    """Bounded, memory-only search/disclosure evidence source for one session."""

    available = True

    def __init__(
        self,
        *,
        service_id: str,
        deployment: str,
        maximum_results: int,
        ref_factory: Callable[[], str] | None = None,
        maximum_records: int = MAX_SESSION_WEB_SEARCH_PREREQUISITES,
    ) -> None:
        # Build one temporary record solely to reuse the strict public service
        # profile validation; it is never retained or used as readiness proof.
        WebSearchServicePrerequisite(
            1, "TR-search_profile", service_id, deployment, maximum_results,
            False, 1.0, 2.0, WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
        )
        if ref_factory is not None and not callable(ref_factory):
            raise TypeError("web search prerequisite reference factory is invalid")
        if (
            isinstance(maximum_records, bool)
            or not isinstance(maximum_records, int)
            or not 2 <= maximum_records <= 1024
        ):
            raise ValueError("web search prerequisite store limit is invalid")
        self._service_id = service_id
        self._deployment = deployment
        self._maximum_results = maximum_results
        self._ref_factory = ref_factory or (lambda: f"TR-{secrets.token_hex(16)}")
        self._maximum_records = maximum_records
        self._reservations: dict[tuple[str, str], _SearchReservation] = {}
        self._services: dict[str, WebSearchServicePrerequisite] = {}
        self._disclosures: dict[str, WebSearchDisclosurePrerequisite] = {}
        self._lock = RLock()

    def reserve_public(
        self, query: object, factual_decision: object,
    ) -> tuple[str, str]:
        """Reserve an exact public query without probing or contacting a service."""
        if not isinstance(factual_decision, FactualResearchDecision):
            raise TypeError("web search factual decision is invalid")
        intent = ResearchDiscoveryIntent.from_request(
            query,
            factual_decision,
            target_kind="public_web_search",
            data_classification="public",
        )
        discovery = evaluate_research_discovery(intent, query, factual_decision)
        if discovery.status != "confirmation_required":
            raise ValueError("web search disclosure is not eligible for confirmation")
        canonical_query = " ".join(query.strip().split())
        with self._lock:
            if self._record_count() + 2 > self._maximum_records:
                raise ValueError("web search prerequisite store is full")
        service_ref, disclosure_ref = self._new_ref(), self._new_ref()
        with self._lock:
            if (
                self._record_count() + 2 > self._maximum_records
                or service_ref == disclosure_ref
                or self._ref_exists(service_ref)
                or self._ref_exists(disclosure_ref)
            ):
                raise ValueError("web search prerequisite reference was reused or exhausted")
            self._reservations[(service_ref, disclosure_ref)] = _SearchReservation(
                canonical_query, intent, discovery,
            )
        return service_ref, disclosure_ref

    def prepare_reserved(
        self,
        service_ref: object,
        disclosure_ref: object,
        service: object,
    ) -> tuple[WebSearchServicePrerequisite, WebSearchDisclosurePrerequisite]:
        """Bind one inert reservation to an exact supplied service observation."""
        if not isinstance(service_ref, str) or not isinstance(disclosure_ref, str):
            raise TypeError("web search prerequisite reference is invalid")
        if not isinstance(service, WebSearchServicePrerequisite):
            raise TypeError("web search service observation is invalid")
        with self._lock:
            reservation = self._reservations.get((service_ref, disclosure_ref))
        if reservation is None:
            raise ValueError("web search prerequisite reservation was not found")
        if (
            service.resource_ref != service_ref
            or service.service_id != self._service_id
            or service.deployment != self._deployment
            or service.maximum_results != self._maximum_results
        ):
            raise ValueError("web search service observation does not match configured profile")
        disclosure = WebSearchDisclosurePrerequisite(
            1, disclosure_ref, reservation.intent, reservation.discovery,
        )
        with self._lock:
            current = self._reservations.get((service_ref, disclosure_ref))
            if current != reservation:
                raise ValueError("web search prerequisite reservation changed")
            self._services[service_ref] = service
            self._disclosures[disclosure_ref] = disclosure
            del self._reservations[(service_ref, disclosure_ref)]
        return service, disclosure

    def service_for(self, resource_ref: str) -> WebSearchServicePrerequisite:
        with self._lock:
            value = self._services.get(resource_ref)
        if value is None:
            raise KeyError("web search service prerequisite was not found")
        return value

    def disclosure_for(self, resource_ref: str) -> WebSearchDisclosurePrerequisite:
        with self._lock:
            value = self._disclosures.get(resource_ref)
        if value is None:
            raise KeyError("web search disclosure prerequisite was not found")
        return value

    def revoke(self, resource_ref: object) -> bool:
        if not isinstance(resource_ref, str):
            return False
        removed = False
        with self._lock:
            removed = self._services.pop(resource_ref, None) is not None
            removed = self._disclosures.pop(resource_ref, None) is not None or removed
            for pair in tuple(self._reservations):
                if resource_ref in pair:
                    del self._reservations[pair]
                    removed = True
        return removed

    def _record_count(self) -> int:
        return 2 * len(self._reservations) + len(self._services) + len(self._disclosures)

    def _ref_exists(self, reference: str) -> bool:
        return (
            reference in self._services
            or reference in self._disclosures
            or any(reference in pair for pair in self._reservations)
        )

    def _new_ref(self) -> str:
        value = self._ref_factory()
        if not isinstance(value, str) or not RESOURCE_REF_RE.fullmatch(value):
            raise ValueError("web search prerequisite reference is invalid")
        return value


__all__ = [
    "LocalWebSearchRuntime",
    "MAX_SESSION_WEB_SEARCH_PREREQUISITES",
    "SessionWebSearchPrerequisiteStore",
]
