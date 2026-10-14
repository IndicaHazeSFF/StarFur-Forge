"""Presentation-neutral application boundary for Assistant Mode.

``AssistantApplication`` owns bounded, ephemeral ``AssistantSession`` objects
for presentation conversations. Canonical memory remains shared through the
existing domain-aware storage primitives; only recent messages, active model,
last-selected memories, and confirmation state are isolated per conversation.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
import threading
import time
from time import perf_counter
from pathlib import Path
from typing import Callable, Iterator

from pipeline.assistant import (
    PROJECT_ROOT, AssistantSession, ProviderCapacityBusyError, load_config,
    load_persona, load_policy,
)
from pipeline.capabilities import CapabilityManifest, CapabilityRegistry, build_core_capability_registry
from pipeline.command_input import (
    MIXED_CONTROL_INPUT_GUIDANCE, has_ambiguous_multiline_controls, is_context_stats_request,
)
from pipeline.db import upsert_assistant_memory_proposal
from pipeline.document_annotation import DocumentProposalAnnotator, FailoverDocumentProposalAnnotator
from pipeline.document_intake import PreparedDocument, extract_document_memory_candidates_resilient
from pipeline.retrieval import DeterministicMemoryRetriever, MemoryRetriever
from pipeline.task_profiles import (
    TASK_DOCUMENT_ANNOTATION,
    TASK_DOCUMENT_ANNOTATION_FALLBACK,
    TaskProfiles,
)
from pipeline.task_routing import (
    ProviderRouteRegistry,
    TaskRoutePlanner,
    provider_route_status_from_runtime,
)
from pipeline.tool_approval import ToolApprovalController
from pipeline.tool_broker import ToolBroker, ToolBrokerError, ToolDispatchContext
from pipeline.tool_contracts import build_core_tool_contract_registry, decode_tool_proposal_json
from pipeline.tool_grants import SessionToolGrantController, ToolInvocationIssuer
from pipeline.tool_execution_router import ToolExecutionBinding, ToolExecutionRouter
from pipeline.tool_prerequisites import SessionToolPrerequisiteController
from pipeline.tool_web_policy import WebDestination
from pipeline.persona_asset_resolver import InstalledPersonaAssetPackage, PersonaAssetResolver
from pipeline.persona_assets import BUILTIN_MURR_ASSET_MANIFEST
from pipeline.persona_registry import PersonaRegistry, load_persona_package
from pipeline.persona_runtime import PersonaRuntimeRegistry
from pipeline.provider_registry import ChatProviderRegistry
from pipeline.providers import ChatProvider, provider_health_snapshot, provider_is_configured
from pipeline.provider_workload_gate import ProviderWorkloadGate
from pipeline.provider_process_gate import ProviderProcessGate
from pipeline.research_coordinator import ResearchClaimCoordinator, ResearchCoordinatorError
from pipeline.research_brief import build_research_cited_brief
from pipeline.research_answer_policy import evaluate_research_answer_policy
from pipeline.research_answer_binding import evaluate_research_answer_binding
from pipeline.research_disclosure import ResearchDisclosureIntent, evaluate_research_disclosure
from pipeline.research_relationship_coordinator import ResearchRelationshipCoordinator, ResearchRelationshipCoordinatorError
from pipeline.research_relationship_brief import build_research_relationship_brief
from pipeline.research_relationship_disclosure import (
    ResearchRelationshipDisclosureIntent,
    evaluate_research_relationship_disclosure,
)
from pipeline.research_relationship_review import SessionResearchRelationshipReviewStore
from pipeline.research_review import SessionResearchReviewStore
from pipeline.research_selection import select_research_sources
from pipeline.research_sources import build_research_source_packet
from pipeline.resident_presentation import ResidentPresentationPlan
from pipeline.resident_snapshot import ResidentSnapshot
from pipeline.sandbox_execution_status import (
    DisabledSandboxExecutionStatusProvider,
    SandboxExecutionStatus,
    SandboxExecutionStatusProvider,
)
from pipeline.tool_status import ToolStatusSummary
from pipeline.system_metrics import LocalSystemMetricsProvider, NullSystemMetricsProvider, SystemMetricsProvider, SystemMetricsSnapshot


DEFAULT_CONVERSATION_ID = "default"
DEFAULT_MAX_CONVERSATIONS = 16
DEFAULT_PROVIDER_PROCESS_GATE_ROOT = PROJECT_ROOT / "data" / "runtime" / "provider-workload"
_CONVERSATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")
_ROUTE_TRACE_ID_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_ROUTE_TRACE_OUTCOMES = frozenset({
    "submitted", "completed", "route_unavailable", "provider_adapter_unavailable",
    "provider_capability_unavailable", "provider_request_failed",
    "provider_stream_failed", "provider_stream_cancelled", "provider_concurrency_busy",
    "provider_thinking_control_unavailable", "provider_output_limit",
})


@dataclass(frozen=True)
class AssistantResponse:
    """One request's text/model and closed completion status, captured under its session lock."""

    content: str
    model: str
    finish_reason: str | None

    def __post_init__(self):
        if not isinstance(self.content, str) or not isinstance(self.model, str):
            raise TypeError("assistant response text and model must be strings")
        if self.finish_reason is not None and (
            not isinstance(self.finish_reason, str) or self.finish_reason not in {"stop", "length"}
        ):
            raise ValueError("assistant response finish reason is invalid")


@dataclass
class _SessionSlot:
    """One bounded ephemeral session plus its request-serialization state."""

    session: AssistantSession
    lock: threading.RLock
    session_instance_id: str
    tool_broker: ToolBroker
    research_reviews: SessionResearchReviewStore
    research_relationship_reviews: SessionResearchRelationshipReviewStore
    local_web_runtime: object | None = None
    local_web_search_runtime: object | None = None
    active_requests: int = 0


class ConversationNotFoundError(LookupError):
    """Raised when a read-only request names no live ephemeral conversation."""


def normalize_conversation_id(value) -> str:
    """Validate an opaque, local conversation key without treating it as auth.

    Callers that omit an identifier retain the legacy default session. The key
    is intentionally constrained because it is used only as a bounded in-memory
    map key, never as a filesystem path, domain, or authorization decision.
    """
    if value is None:
        return DEFAULT_CONVERSATION_ID
    if not isinstance(value, str):
        raise ValueError("Conversation identifier must be a string.")
    key = value.strip()
    if not key:
        raise ValueError("Conversation identifier must not be empty.")
    if not _CONVERSATION_ID_RE.fullmatch(key):
        raise ValueError(
            "Conversation identifier must use 1-128 letters, numbers, dots, underscores, colons, at-signs, or hyphens."
        )
    return key


def _bounded_task_route_trace(value: object) -> list[dict[str, object]]:
    """Copy only a small, public completed-turn route trace for diagnostics."""
    if not isinstance(value, (list, tuple)):
        return []
    bounded: list[dict[str, object]] = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        requested = item.get("requested_task_id")
        selected = item.get("selected_task_id")
        provider = item.get("provider")
        model = item.get("model")
        outcome = item.get("outcome")
        fallback_used = item.get("fallback_used")
        if not all(isinstance(part, str) and _ROUTE_TRACE_ID_RE.fullmatch(part) for part in (requested, selected, provider)):
            continue
        if not isinstance(model, str) or not model.strip() or len(model) > 256:
            continue
        if outcome not in _ROUTE_TRACE_OUTCOMES or not isinstance(fallback_used, bool):
            continue
        bounded_item = {
            "requested_task_id": requested,
            "selected_task_id": selected,
            "provider": provider,
            "model": model,
            "fallback_used": fallback_used,
            "outcome": outcome,
        }
        resource_profile = item.get("resource_profile")
        if isinstance(resource_profile, str) and resource_profile in {"interactive", "balanced", "background"}:
            bounded_item["resource_profile"] = resource_profile
        bounded.append(bounded_item)
    return bounded


class AssistantApplication:
    """Shared application facade around bounded, isolated assistant sessions."""

    def __init__(
        self,
        session: AssistantSession,
        *,
        capability_manifest: CapabilityManifest | None = None,
        proposal_creator=upsert_assistant_memory_proposal,
        session_factory: Callable[[], AssistantSession] | None = None,
        max_conversations: int = DEFAULT_MAX_CONVERSATIONS,
        retriever: MemoryRetriever | None = None,
        system_metrics_provider: SystemMetricsProvider | None = None,
        sandbox_status_provider: SandboxExecutionStatusProvider | None = None,
        persona_asset_resolver: PersonaAssetResolver | None = None,
        local_web_runtime_factory: Callable[[], object] | None = None,
        local_web_search_runtime_factory: Callable[[], object] | None = None,
        workload_gate: ProviderWorkloadGate | None = None,
    ):
        if max_conversations <= 0:
            raise ValueError("max_conversations must be positive.")
        if workload_gate is not None and not isinstance(workload_gate, ProviderWorkloadGate):
            raise TypeError("workload_gate must be a ProviderWorkloadGate or None.")
        self.session = session
        self._workload_gate = workload_gate or self._default_workload_gate(session)
        self.retriever = retriever or getattr(session, "retriever", None)
        self.system_metrics_provider = system_metrics_provider or NullSystemMetricsProvider()
        if not callable(getattr(self.system_metrics_provider, "snapshot", None)):
            raise TypeError("system_metrics_provider must provide a callable snapshot method.")
        self.sandbox_status_provider = (
            sandbox_status_provider or DisabledSandboxExecutionStatusProvider()
        )
        if not callable(getattr(self.sandbox_status_provider, "snapshot", None)):
            raise TypeError("sandbox_status_provider must provide a callable snapshot method.")
        if persona_asset_resolver is not None and not isinstance(persona_asset_resolver, PersonaAssetResolver):
            raise TypeError("persona_asset_resolver must be a PersonaAssetResolver or None.")
        self.persona_asset_resolver = persona_asset_resolver or PersonaAssetResolver()
        self.capability_manifest = capability_manifest or build_core_capability_registry().build_manifest()
        # The registry lock protects only lookup, creation, LRU ordering, and
        # eviction.  Individual conversations retain their own locks so a
        # streamed request in chat A cannot block independent chat B.
        self._registry_lock = threading.RLock()
        self._proposal_creator = proposal_creator
        self._session_factory = session_factory
        self._max_conversations = max_conversations
        if local_web_runtime_factory is not None and not callable(local_web_runtime_factory):
            raise TypeError("local_web_runtime_factory must be callable or None")
        if local_web_search_runtime_factory is not None and not callable(local_web_search_runtime_factory):
            raise TypeError("local_web_search_runtime_factory must be callable or None")
        self._local_web_runtime_factory = local_web_runtime_factory
        self._local_web_search_runtime_factory = local_web_search_runtime_factory
        self._tool_contracts = build_core_tool_contract_registry()
        self._sessions = OrderedDict([
            (DEFAULT_CONVERSATION_ID, self._new_session_slot(session)),
        ])
        self._initialize_provider_health(session)
        self._attach_capability_manifest(session)
        self._attach_retriever(session)
        self._attach_workload_gate(session)

    @staticmethod
    def _default_workload_gate(session):
        """Build one local capacity-one gate without touching any provider."""
        registry = getattr(session, "chat_provider_registry", None)
        provider_ids = getattr(registry, "provider_ids", None)
        if not callable(provider_ids):
            return None
        ids = tuple(provider_ids())
        return ProviderWorkloadGate({provider_id: 1 for provider_id in ids}) if ids else None

    def _new_session_slot(self, session: AssistantSession) -> _SessionSlot:
        session_instance_id = f"session-{secrets.token_hex(16)}"
        prerequisites = SessionToolPrerequisiteController()
        local_web_runtime = None
        local_web_search_runtime = None
        bindings = []
        if self._local_web_runtime_factory is not None:
            local_web_runtime = self._local_web_runtime_factory()
            if not all(hasattr(local_web_runtime, name) for name in (
                "prerequisites", "quarantine", "supervisor",
            )):
                raise TypeError("local web tool runtime is invalid")
            bindings.append(ToolExecutionBinding("web.fetch", 1, local_web_runtime.supervisor))
        if self._local_web_search_runtime_factory is not None:
            local_web_search_runtime = self._local_web_search_runtime_factory()
            if not all(hasattr(local_web_search_runtime, name) for name in (
                "prerequisites", "quarantine", "supervisor", "service_observation",
            )) or not callable(local_web_search_runtime.service_observation):
                raise TypeError("local web search tool runtime is invalid")
            bindings.append(ToolExecutionBinding(
                "web.search", 1, local_web_search_runtime.supervisor,
            ))
        supervisor = ToolExecutionRouter(tuple(bindings)) if bindings else None
        return _SessionSlot(
            session=session,
            lock=threading.RLock(),
            session_instance_id=session_instance_id,
            tool_broker=ToolBroker(
                self._tool_contracts,
                ToolInvocationIssuer(self._tool_contracts),
                SessionToolGrantController(),
                ToolApprovalController(),
                prerequisites=prerequisites,
                supervisor=supervisor,
            ),
            research_reviews=SessionResearchReviewStore(),
            research_relationship_reviews=SessionResearchRelationshipReviewStore(),
            local_web_runtime=local_web_runtime,
            local_web_search_runtime=local_web_search_runtime,
        )

    def _attach_capability_manifest(self, session):
        setter = getattr(session, "set_capability_manifest", None)
        if callable(setter):
            setter(self.capability_manifest)

    def _attach_retriever(self, session):
        if self.retriever is None:
            return
        setter = getattr(session, "set_retriever", None)
        if callable(setter):
            setter(self.retriever)

    def _attach_workload_gate(self, session):
        """Attach only the shared process-local capacity gate to real sessions."""
        if self._workload_gate is not None and isinstance(session, AssistantSession):
            session._provider_workload_gate = self._workload_gate

    @staticmethod
    def _initialize_provider_health(session):
        """Keep a bounded provider-health snapshot with ephemeral session state."""
        if not hasattr(session, "provider_health_snapshot"):
            session.provider_health_snapshot = {
                "status": "not_probed",
                "probe_performed": False,
                "checked_at": None,
                "model_count": None,
                "error": None,
            }

    @staticmethod
    def _provider_health_for_session(session):
        return dict(getattr(session, "provider_health_snapshot", {
            "status": "not_probed",
            "probe_performed": False,
            "checked_at": None,
            "model_count": None,
            "error": None,
        }))

    def _probe_provider_for_session(self, session):
        """Run one explicit non-generating provider probe and retain its result."""
        snapshot = provider_health_snapshot(getattr(session, "provider", None))
        session.provider_health_snapshot = snapshot
        return dict(snapshot)

    def _session_for(self, conversation_id=None):
        """Return one ephemeral session, creating/evicting only non-default ones.

        This compatibility helper does not hold a request lock; application
        operations use ``_locked_session_for`` below. The legacy default
        session is retained permanently for CLI and clients that omit a key.
        Additional sessions are least-recently-used and never write session
        state to SQLite or Chroma when evicted.
        """
        with self._registry_lock:
            key = normalize_conversation_id(conversation_id)
            slot = self._session_slot_for(key)
            # A caller using this compatibility accessor has not acquired a
            # request pin.  Never evict the newly returned session while
            # making room; if every older session is busy, temporarily retain
            # the bounded overflow until a request releases its pin.
            self._evict_sessions_if_needed(exclude_keys={key})
            return slot.session

    def _session_slot_for(self, conversation_id=None):
        """Look up/create a slot while ``_registry_lock`` is held."""
        key = normalize_conversation_id(conversation_id)
        existing = self._sessions.get(key)
        if existing is not None:
            self._sessions.move_to_end(key)
            return existing
        if self._session_factory is None:
            raise ValueError(
                "Conversation isolation requires an application session factory."
            )
        session = self._session_factory()
        self._initialize_provider_health(session)
        self._attach_capability_manifest(session)
        self._attach_retriever(session)
        self._attach_workload_gate(session)
        # Do not evict here.  A newly created slot is not yet request-pinned,
        # so eviction at this point can select and remove the very slot this
        # method is about to return when older conversations are busy.
        slot = self._new_session_slot(session)
        self._sessions[key] = slot
        return slot

    def _evict_sessions_if_needed(self, *, exclude_keys=frozenset()):
        """Keep only the configured number of non-default in-memory sessions."""
        if not isinstance(exclude_keys, (set, frozenset)):
            raise TypeError("excluded session keys must be a set")
        while len(self._sessions) - 1 > self._max_conversations:
            evictable_key = next(
                (
                    key for key, slot in self._sessions.items()
                    if (
                        key != DEFAULT_CONVERSATION_ID
                        and key not in exclude_keys
                        and slot.active_requests == 0
                    )
                ),
                None,
            )
            # A request pins its slot until it completes. Temporarily allowing
            # the bounded registry to exceed its cap is safer than replacing
            # an active conversation with a new empty session mid-turn.
            if evictable_key is None:
                return
            del self._sessions[evictable_key]

    @contextmanager
    def _locked_session_for(self, conversation_id=None) -> Iterator[AssistantSession]:
        """Borrow one session and serialize only that conversation's request."""
        with self._registry_lock:
            slot = self._session_slot_for(conversation_id)
            slot.active_requests += 1
        try:
            with slot.lock:
                yield slot.session
        finally:
            with self._registry_lock:
                slot.active_requests -= 1
                self._evict_sessions_if_needed()

    @contextmanager
    def _locked_tool_slot_for(self, conversation_id=None) -> Iterator[_SessionSlot]:
        """Borrow a complete slot for trusted local tool-control operations."""
        with self._registry_lock:
            slot = self._session_slot_for(conversation_id)
            slot.active_requests += 1
        try:
            with slot.lock:
                yield slot
        finally:
            with self._registry_lock:
                slot.active_requests -= 1
                self._evict_sessions_if_needed()

    @contextmanager
    def _locked_existing_session_for(self, conversation_id=None) -> Iterator[AssistantSession]:
        """Borrow an existing session without allowing a read to seed one."""
        with self._registry_lock:
            key = normalize_conversation_id(conversation_id)
            slot = self._sessions.get(key)
            if slot is None:
                raise ConversationNotFoundError("Conversation session was not found.")
            self._sessions.move_to_end(key)
            slot.active_requests += 1
        try:
            with slot.lock:
                yield slot.session
        finally:
            with self._registry_lock:
                slot.active_requests -= 1
                self._evict_sessions_if_needed()

    @contextmanager
    def _locked_existing_tool_slot_for(self, conversation_id=None) -> Iterator[_SessionSlot]:
        """Borrow an existing complete slot for passive session-local views."""
        with self._registry_lock:
            key = normalize_conversation_id(conversation_id)
            slot = self._sessions.get(key)
            if slot is None:
                raise ConversationNotFoundError("Conversation session was not found.")
            self._sessions.move_to_end(key)
            slot.active_requests += 1
        try:
            with slot.lock:
                yield slot
        finally:
            with self._registry_lock:
                slot.active_requests -= 1
                self._evict_sessions_if_needed()

    @staticmethod
    def _active_model_for_session(session):
        return getattr(session, "active_model", None) or getattr(session.config, "chat_model", "unknown")

    @property
    def active_model(self):
        return self.active_model_for()

    def active_model_for(self, conversation_id=None):
        with self._locked_session_for(conversation_id) as session:
            return self._active_model_for_session(session)

    @contextmanager
    def _streaming(self, session, stream_writer: Callable[[str], None] | None) -> Iterator[None]:
        """Temporarily route one request through a presentation stream writer."""
        if stream_writer is None:
            yield
            return
        old_stream = getattr(session, "stream", False)
        old_writer = getattr(session, "stream_writer", None)
        session.stream = True
        session.stream_writer = stream_writer
        try:
            yield
        finally:
            session.stream = old_stream
            session.stream_writer = old_writer

    @staticmethod
    def _is_tool_control_namespace(user_text: object) -> bool:
        if not isinstance(user_text, str):
            return False
        lowered = user_text.strip().casefold()
        return lowered == "tool" or lowered.startswith("tool ")

    @staticmethod
    def _tool_dispatch_context(slot: _SessionSlot) -> ToolDispatchContext:
        session = slot.session
        runtime = getattr(session, "persona_runtime_state", None)
        persona_id = getattr(runtime, "persona_id", None) or "unselected"
        adventure = getattr(session, "adventure_session", None)
        record = getattr(adventure, "record", None)
        adventure_id = getattr(record, "adventure_id", None)
        policy = getattr(session, "policy", "")
        policy_digest = hashlib.sha256(str(policy).encode("utf-8")).hexdigest()[:16]
        return ToolDispatchContext(
            principal_id="local.cli",
            session_instance_id=slot.session_instance_id,
            persona_id=persona_id,
            adventure_id=adventure_id,
            policy_revision=f"policy-{policy_digest}",
        )

    @staticmethod
    def _format_tool_record(record) -> str:
        return (
            f"{record.invocation.invocation_id} {record.invocation.tool_id} v{record.invocation.tool_version} "
            f"[{record.state}] {record.reason}"
        )

    def _local_tool_control(self, slot: _SessionSlot, user_text: str) -> str:
        """Handle exact local-only tool controls before any model command path."""
        command = user_text.strip()
        lowered = command.casefold()
        context = self._tool_dispatch_context(slot)
        slot.tool_broker.invalidate_context(context)

        if lowered in {"tool", "tool help"}:
            return (
                "Local tool controls (sandbox execution disabled):\n"
                "tool propose sandbox.run <JSON arguments>\n"
                "tool propose web.fetch {\"url\":\"https://...\"}\n"
                "tool fetch <https://...>\n"
                "tool propose web.search {\"query\":\"...\"}\n"
                "tool search <public query>\n"
                "tool list\n"
                "tool status <TI-id>\n"
                "tool preview <TI-id>\n"
                "tool grant <TI-id>\n"
                "tool approve <TI-id>\n"
                "tool prepare <TI-id>\n"
                "tool execute <TI-id>\n"
                "tool artifact <TF-id>\n"
                "tool search artifact <TF-search_id>\n"
                "tool search select <TF-search_id> <rank>\n"
                "tool search fetch <TF-search_id> <rank>\n"
                "tool research <TF-id>: <question>\n"
                "tool research selected <TF-search_id> <rank>: <question>\n"
                "tool research search <public query> <rank>: <question>\n"
                "tool research list\n"
                "tool research inspect <RR-id>\n"
                "tool research relationships <RR-id>\n"
                "tool research relationships list\n"
                "tool research relationships inspect <RX-id>\n"
                "tool research relationships brief <RX-id>\n"
                "tool research brief <RR-id>\n"
                "tool research answer <RR-id>\n"
                "tool deny <TI-id>\n"
                "tool revoke <TI-id>\n"
                "tool cancel <TI-id>"
            )
        if lowered in {"tool list", "tool status"}:
            records = slot.tool_broker.records()
            if not records:
                return "No local tool requests are registered for this session."
            lines = ["Local tool requests:"]
            lines.extend(self._format_tool_record(item) for item in records[-20:])
            return "\n".join(lines)

        fast_fetch_match = re.fullmatch(r"tool\s+fetch\s+(https://\S+)", command, flags=re.IGNORECASE)
        if fast_fetch_match:
            if slot.local_web_runtime is None:
                return "Native web.fetch is unavailable in this application mode."
            url = fast_fetch_match.group(1)
            proposed = self._local_tool_control(
                slot,
                "tool propose web.fetch " + json.dumps({"url": url}, separators=(",", ":")),
            )
            match = re.search(r"\b(TI-[A-Za-z0-9_-]{1,64})\b", proposed)
            if match is None:
                return "Fast web fetch was rejected safely: " + proposed
            request_id = match.group(1)
            for action in ("grant", "approve", "prepare"):
                result = self._local_tool_control(slot, f"tool {action} {request_id}")
                if "rejected safely" in result or "unavailable" in result or "expired" in result:
                    return f"Fast web fetch stopped before execution: {result}"
            completed = self._local_tool_control(slot, f"tool execute {request_id}")
            return (
                f"Explicit local fast fetch confirmed for {url}.\n{completed}\n"
                "Inspect any returned artifact explicitly with tool artifact <TF-id>."
            )

        proposal_match = re.fullmatch(
            r"tool\s+propose\s+sandbox\.run\s+(.+)", command, flags=re.IGNORECASE | re.DOTALL,
        )
        if proposal_match:
            raw_arguments = proposal_match.group(1).strip()
            envelope = (
                '{"schema_version":1,"tool_id":"sandbox.run","tool_version":1,"arguments":'
                + raw_arguments + "}"
            )
            try:
                proposal = decode_tool_proposal_json(envelope)
                request_id = f"TI-{secrets.token_hex(16)}"
                record = slot.tool_broker.submit(
                    proposal,
                    request_id=request_id,
                    trusted_principal_id=context.principal_id,
                    session_instance_id=context.session_instance_id,
                    persona_id=context.persona_id,
                    adventure_id=context.adventure_id,
                    policy_revision=context.policy_revision,
                )
            except (TypeError, ValueError, RuntimeError) as error:
                return f"Tool proposal was rejected safely: {error}"
            return (
                f"Registered inert tool proposal {record.invocation.invocation_id} for sandbox.run. "
                "No files were created and no work was executed. Use tool preview, then tool grant and tool approve."
            )

        web_proposal_match = re.fullmatch(
            r"tool\s+propose\s+web\.fetch\s+(.+)", command, flags=re.IGNORECASE | re.DOTALL,
        )
        if web_proposal_match:
            if slot.local_web_runtime is None:
                return "Native web.fetch is unavailable in this application mode."
            raw_arguments = web_proposal_match.group(1).strip()
            envelope = (
                '{"schema_version":1,"tool_id":"web.fetch","tool_version":1,"arguments":'
                + raw_arguments + "}"
            )
            references = ()
            try:
                proposal = decode_tool_proposal_json(envelope)
                references = slot.local_web_runtime.prerequisites.reserve_public(
                    WebDestination(1, proposal.arguments["url"]),
                )
                request_id = f"TI-{secrets.token_hex(16)}"
                record = slot.tool_broker.submit(
                    proposal,
                    request_id=request_id,
                    trusted_principal_id=context.principal_id,
                    session_instance_id=context.session_instance_id,
                    persona_id=context.persona_id,
                    adventure_id=context.adventure_id,
                    policy_revision=context.policy_revision,
                    resource_refs=references,
                )
            except (TypeError, ValueError, RuntimeError) as error:
                for reference in references:
                    slot.local_web_runtime.prerequisites.revoke(reference)
                return f"Tool proposal was rejected safely: {error}"
            return (
                f"Registered inert tool proposal {record.invocation.invocation_id} for web.fetch. "
                "No DNS lookup or network request occurred. Use tool preview, grant, approve, prepare, then execute."
            )

        search_proposal_match = re.fullmatch(
            r"tool\s+propose\s+web\.search\s+(.+)", command, flags=re.IGNORECASE | re.DOTALL,
        )
        if search_proposal_match:
            if slot.local_web_search_runtime is None:
                return "Public web.search is unavailable in this application mode."
            raw_arguments = search_proposal_match.group(1).strip()
            envelope = (
                '{"schema_version":1,"tool_id":"web.search","tool_version":1,"arguments":'
                + raw_arguments + "}"
            )
            references = ()
            try:
                proposal = decode_tool_proposal_json(envelope)
                from pipeline.factual_research_policy import explicit_local_research_tool_decision
                factual = explicit_local_research_tool_decision()
                references = slot.local_web_search_runtime.prerequisites.reserve_public(
                    proposal.arguments["query"], factual,
                )
                request_id = f"TI-{secrets.token_hex(16)}"
                record = slot.tool_broker.submit(
                    proposal,
                    request_id=request_id,
                    trusted_principal_id=context.principal_id,
                    session_instance_id=context.session_instance_id,
                    persona_id=context.persona_id,
                    adventure_id=context.adventure_id,
                    policy_revision=context.policy_revision,
                    resource_refs=references,
                )
            except (TypeError, ValueError, RuntimeError) as error:
                for reference in references:
                    slot.local_web_search_runtime.prerequisites.revoke(reference)
                return f"Tool proposal was rejected safely: {error}"
            return (
                f"Registered inert tool proposal {record.invocation.invocation_id} for web.search. "
                "No provider probe or search request occurred. Use tool preview, grant, approve, prepare, then execute."
            )

        artifact_match = re.fullmatch(
            r"tool\s+artifact\s+(TF-[A-Za-z0-9_-]{1,64})", command, flags=re.IGNORECASE,
        )
        if artifact_match:
            if slot.local_web_runtime is None:
                return "Local web artifact storage is unavailable."
            artifact_ref = "TF-" + artifact_match.group(1)[3:]
            artifact = slot.local_web_runtime.quarantine.get(artifact_ref)
            if artifact is None:
                return "Tool artifact was not found in this local session."
            text = artifact.payload.text
            visible = text[:12000]
            suffix = "\n[display truncated]" if len(text) > len(visible) else ""
            return (
                f"Quarantined web artifact {artifact_ref}\n"
                f"Source: {artifact.destination.url}\n"
                f"Source media: {artifact.payload.source_media_type}\n"
                f"Prepared media: {artifact.payload.media_type}\n"
                f"Trust: {artifact.payload.trust_label}\n"
                f"Characters: {artifact.payload.character_count}\n"
                f"Digest: {artifact.payload.prepared_sha256}\n\n{visible}{suffix}"
            )

        search_artifact_match = re.fullmatch(
            r"tool\s+search\s+artifact\s+(TF-search_[A-Za-z0-9_-]{1,64})",
            command,
            flags=re.IGNORECASE,
        )
        if search_artifact_match:
            if slot.local_web_search_runtime is None:
                return "Local web-search artifact storage is unavailable."
            artifact_ref = "TF-search_" + search_artifact_match.group(1)[10:]
            artifact = slot.local_web_search_runtime.quarantine.get(artifact_ref)
            if artifact is None:
                return "Search artifact was not found in this local session."
            lines = [
                f"Quarantined search artifact {artifact_ref}",
                f"Service: {artifact.service_id}",
                f"Trust: {artifact.trust_label}",
                f"Digest: {artifact.artifact_sha256}",
                "Untrusted discovery links:",
            ]
            lines.extend(f"{item.rank}. {item.title} — {item.url}" for item in artifact.results)
            lines.append("Discovery links are not factual support or permission to fetch them.")
            return "\n".join(lines)

        search_select_match = re.fullmatch(
            r"tool\s+search\s+select\s+(TF-search_[A-Za-z0-9_-]{1,64})\s+([1-8])",
            command,
            flags=re.IGNORECASE,
        )
        if search_select_match:
            if slot.local_web_search_runtime is None:
                return "Local web-search artifact storage is unavailable."
            if slot.local_web_runtime is None:
                return "Native web.fetch is unavailable in this application mode."
            artifact_ref = "TF-search_" + search_select_match.group(1)[10:]
            artifact = slot.local_web_search_runtime.quarantine.get(artifact_ref)
            if artifact is None:
                return "Search artifact was not found in this local session."
            rank = int(search_select_match.group(2))
            candidate = next((item for item in artifact.results if item.rank == rank), None)
            if candidate is None:
                return "Selected search-result rank was not found in this local artifact."
            references = ()
            try:
                proposal = decode_tool_proposal_json(json.dumps({
                    "schema_version": 1,
                    "tool_id": "web.fetch",
                    "tool_version": 1,
                    "arguments": {"url": candidate.url},
                }, separators=(",", ":"), ensure_ascii=False))
                destination = WebDestination(1, proposal.arguments["url"])
                references = slot.local_web_runtime.prerequisites.reserve_public(destination)
                request_id = f"TI-{secrets.token_hex(16)}"
                record = slot.tool_broker.submit(
                    proposal,
                    request_id=request_id,
                    trusted_principal_id=context.principal_id,
                    session_instance_id=context.session_instance_id,
                    persona_id=context.persona_id,
                    adventure_id=context.adventure_id,
                    policy_revision=context.policy_revision,
                    resource_refs=references,
                )
            except (TypeError, ValueError, RuntimeError) as error:
                for reference in references:
                    slot.local_web_runtime.prerequisites.revoke(reference)
                return f"Search-link selection was rejected safely: {error}"
            return (
                f"Selected untrusted discovery link {rank} from {artifact_ref}; registered inert web.fetch "
                f"proposal {record.invocation.invocation_id}. No DNS lookup or network request occurred. "
                "Selection is not factual support; preview, grant, approve, prepare, and execute it separately."
            )

        fast_search_fetch_match = re.fullmatch(
            r"tool\s+search\s+fetch\s+(TF-search_[A-Za-z0-9_-]{1,64})\s+([1-8])",
            command,
            flags=re.IGNORECASE,
        )
        if fast_search_fetch_match:
            artifact_ref = "TF-search_" + fast_search_fetch_match.group(1)[10:]
            rank = fast_search_fetch_match.group(2)
            selected = self._local_tool_control(slot, f"tool search select {artifact_ref} {rank}")
            match = re.search(r"\b(TI-[A-Za-z0-9_-]{1,64})\b", selected)
            if match is None:
                return "Fast search-link fetch was rejected safely: " + selected
            request_id = match.group(1)
            for action in ("grant", "approve", "prepare"):
                result = self._local_tool_control(slot, f"tool {action} {request_id}")
                if "rejected safely" in result or "unavailable" in result or "expired" in result:
                    return f"Fast search-link fetch stopped before execution: {result}"
            completed = self._local_tool_control(slot, f"tool execute {request_id}")
            return (
                f"Explicit local fast fetch confirmed for selected discovery link {rank}.\n"
                + completed
                + "\nInspect any returned artifact explicitly with tool artifact <TF-id>."
            )

        fast_search_match = re.fullmatch(
            r"tool\s+search\s+(.+)", command, flags=re.IGNORECASE | re.DOTALL,
        )
        if fast_search_match:
            if slot.local_web_search_runtime is None:
                return "Public web.search is unavailable in this application mode."
            query = fast_search_match.group(1).strip()
            if query.casefold() in {"artifact", "select", "fetch"} or query.casefold().startswith(("artifact ", "select ", "fetch ")):
                return "Unknown or malformed local tool command. Use tool help. Tool commands never fall through to model generation."
            proposed = self._local_tool_control(
                slot,
                "tool propose web.search " + json.dumps({"query": query}, separators=(",", ":")),
            )
            match = re.search(r"\b(TI-[A-Za-z0-9_-]{1,64})\b", proposed)
            if match is None:
                return "Fast web search was rejected safely: " + proposed
            request_id = match.group(1)
            for action in ("grant", "approve", "prepare"):
                result = self._local_tool_control(slot, f"tool {action} {request_id}")
                if "rejected safely" in result or "unavailable" in result or "expired" in result:
                    return f"Fast web search stopped before execution: {result}"
            completed = self._local_tool_control(slot, f"tool execute {request_id}")
            return (
                "Explicit local fast web search confirmed.\n"
                + completed
                + "\nInspect any returned discovery links explicitly with tool search artifact <TF-search_id>."
            )

        selected_research_match = re.fullmatch(
            r"tool\s+research\s+selected\s+(TF-search_[A-Za-z0-9_-]{1,64})\s+([1-8])\s*:\s*(.+)",
            command,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if selected_research_match:
            artifact_ref = "TF-search_" + selected_research_match.group(1)[10:]
            rank = selected_research_match.group(2)
            question = selected_research_match.group(3)
            fetched = self._local_tool_control(slot, f"tool search fetch {artifact_ref} {rank}")
            match = re.search(r"\b(TF-[A-Za-z0-9_-]{1,64})\b", fetched)
            if match is None:
                return "Selected-link research stopped before source review: " + fetched
            source_ref = match.group(1)
            reviewed = self._local_tool_control(slot, f"tool research {source_ref}: {question}")
            return (
                "Explicit local selected-link research confirmed.\n"
                + fetched
                + "\n"
                + reviewed
            )

        searched_research_match = re.fullmatch(
            r"tool\s+research\s+search\s+(.+?)\s+([1-8])\s*:\s*(.+)",
            command,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if searched_research_match:
            query = searched_research_match.group(1).strip()
            rank = searched_research_match.group(2)
            question = searched_research_match.group(3)
            if not query or not question.strip():
                return "Unknown or malformed local tool command. Use tool help. Tool commands never fall through to model generation."
            searched = self._local_tool_control(slot, f"tool search {query}")
            match = re.search(r"\b(TF-search_[A-Za-z0-9_-]{1,64})\b", searched)
            if match is None:
                return "Fast search-to-research stopped before source selection: " + searched
            artifact_ref = match.group(1)
            reviewed = self._local_tool_control(
                slot,
                f"tool research selected {artifact_ref} {rank}: {question}",
            )
            return (
                f"Explicit local fast search-to-research confirmed for selected discovery link {rank}.\n"
                + searched
                + "\n"
                + reviewed
            )

        if lowered == "tool research relationships list":
            summaries = slot.research_relationship_reviews.summaries()
            if not summaries:
                return "No session-local research relationship reviews are available."
            lines = ["Session-local research relationship reviews:"]
            for item in summaries:
                lines.append(
                    f"{item['relationship_review_id']} [{item['status']}] "
                    f"from {item['claim_review_id']}; {item['relationship_count']} relationship(s)"
                )
            lines.append("Relationship reviews are untrusted, noncanonical, and disappear when this session is evicted or restarted.")
            return "\n".join(lines)

        relationship_inspect_match = re.fullmatch(
            r"tool\s+research\s+relationships\s+inspect\s+(RX-[0-9a-f]{24})",
            command,
            flags=re.IGNORECASE,
        )
        if relationship_inspect_match:
            relationship_review_id = "RX-" + relationship_inspect_match.group(1)[3:]
            relationship_review = slot.research_relationship_reviews.get(relationship_review_id)
            if relationship_review is None:
                return "Research relationship review was not found in this local session."
            lines = [
                f"Research relationship review {relationship_review.relationship_review_id} [{relationship_review.status}]",
                f"Claim review: {relationship_review.claim_review_id}",
            ]
            relationships = relationship_review.result.relationships.relationships
            if relationships:
                lines.append("Untrusted claim-relationship proposals:")
                lines.extend(
                    f"{item.relationship_id} [confidence {item.confidence:.2f}] "
                    f"{item.left_claim_id} {item.relation} {item.right_claim_id}"
                    for item in relationships
                )
            else:
                lines.append("No claim relationships were proposed.")
            lines.append(
                "Read-only relationship review; it is not verification, a final answer, or writable state."
            )
            return "\n".join(lines)

        relationship_brief_match = re.fullmatch(
            r"tool\s+research\s+relationships\s+brief\s+(RX-[0-9a-f]{24})",
            command,
            flags=re.IGNORECASE,
        )
        if relationship_brief_match:
            relationship_review_id = "RX-" + relationship_brief_match.group(1)[3:]
            relationship_review = slot.research_relationship_reviews.get(relationship_review_id)
            if relationship_review is None:
                return "Research relationship review was not found in this local session."
            review = slot.research_reviews.get(relationship_review.claim_review_id)
            if review is None:
                return "The source claim review is no longer available in this local session."
            try:
                brief = build_research_relationship_brief(review, relationship_review)
            except (TypeError, ValueError) as error:
                return f"Research relationship brief was rejected safely: {error}"
            if not brief.items:
                return (
                    f"Relationship brief for {brief.relationship_review_id}: no claim relationships were proposed. "
                    "No model was called and no state was created."
                )
            lines = [
                f"Claim-relationship brief for {brief.relationship_review_id} (untrusted; not verification)",
            ]
            for item in brief.items:
                lines.extend((
                    f"- {item.left_claim_id}: {item.left_statement}",
                    f"  {item.relation} ({item.confidence:.2f})",
                    f"  {item.right_claim_id}: {item.right_statement}",
                ))
            lines.append(
                "Deterministic presentation of existing relationship proposals only; no model was called and no corroboration, answer, memory, learning, adventure, or canonical state was created."
            )
            return "\n".join(lines)

        relationship_match = re.fullmatch(
            r"tool\s+research\s+relationships\s+(RR-[0-9a-f]{24})",
            command,
            flags=re.IGNORECASE,
        )
        if relationship_match:
            review_id = "RR-" + relationship_match.group(1)[3:]
            review = slot.research_reviews.get(review_id)
            if review is None:
                return "Research claim review was not found in this local session."
            try:
                provider = slot.session.local_research_relationship_provider()
                target = provider.target
                intent = ResearchRelationshipDisclosureIntent.from_review(review, target)
                decision = evaluate_research_relationship_disclosure(intent, review)
                result = ResearchRelationshipCoordinator(provider).propose(review, target, decision)
                relationship_review = slot.research_relationship_reviews.create(review, result)
            except ResearchRelationshipCoordinatorError as error:
                return (
                    f"Research relationship generation failed safely ({error.reason}); "
                    "no verification, answer, memory, learning record, or canonical state was published."
                )
            except (TypeError, ValueError, RuntimeError) as error:
                return f"Research relationship request was rejected safely: {error}"
            lines = [
                "Research claim-relationship proposals (untrusted; not verification)",
                f"Review: {relationship_review.relationship_review_id} (session-local; claim review {review.review_id})",
            ]
            relationships = result.relationships.relationships
            if relationships:
                lines.extend(
                    f"{item.relationship_id} [confidence {item.confidence:.2f}] "
                    f"{item.left_claim_id} {item.relation} {item.right_claim_id}"
                    for item in relationships
                )
            else:
                lines.append("No claim relationships were proposed.")
            lines.append(
                "Review output only; it cannot establish corroboration, truth, a final answer, memory, learning, adventure, or canonical state."
            )
            lines.append(
                f"Use tool research relationships inspect {relationship_review.relationship_review_id} to reopen this relationship review."
            )
            return "\n".join(lines)

        if lowered == "tool research list":
            summaries = slot.research_reviews.summaries()
            if not summaries:
                return "No session-local research claim reviews are available."
            lines = ["Session-local research claim reviews:"]
            for item in summaries:
                lines.append(
                    f"{item['review_id']} [{item['status']}] "
                    f"{item['claim_count']} claim(s), {item['source_count']} source(s)"
                )
            lines.append("Review records are noncanonical and disappear when this session is evicted or restarted.")
            return "\n".join(lines)

        review_match = re.fullmatch(
            r"tool\s+research\s+inspect\s+(RR-[0-9a-f]{24})",
            command,
            flags=re.IGNORECASE,
        )
        if review_match:
            review_id = "RR-" + review_match.group(1)[3:]
            review = slot.research_reviews.get(review_id)
            if review is None:
                return "Research claim review was not found in this local session."
            lines = [
                f"Research claim review {review.review_id} [{review.status}]",
                "Sources:",
            ]
            lines.extend(
                f"- {source_id} {url} (fetched {datetime.fromtimestamp(fetched_at_epoch, timezone.utc).isoformat()})"
                for source_id, url, fetched_at_epoch in review.source_labels
            )
            if review.result.claims.claims:
                lines.append("Untrusted cited claim proposals:")
                for claim in review.result.claims.claims:
                    lines.append(f"{claim.claim_id} [confidence {claim.confidence:.2f}] {claim.statement}")
                    lines.append("  Cites: " + ", ".join(claim.source_ids))
                    evidence = review.evidence.for_claim(claim.claim_id)
                    if evidence is not None:
                        lines.append(
                            f"  Citation diversity: {evidence.citation_diversity} "
                            f"({evidence.cited_source_count} source(s), {evidence.cited_host_count} host(s)); "
                            "not verification."
                        )
            else:
                lines.append("No directly supported claims were proposed from these sources.")
            lines.append(
                "Read-only review record; it is not a final answer and cannot create memory, learning, adventure, or canonical state."
            )
            return "\n".join(lines)

        brief_match = re.fullmatch(
            r"tool\s+research\s+brief\s+(RR-[0-9a-f]{24})",
            command,
            flags=re.IGNORECASE,
        )
        if brief_match:
            review_id = "RR-" + brief_match.group(1)[3:]
            review = slot.research_reviews.get(review_id)
            if review is None:
                return "Research claim review was not found in this local session."
            try:
                brief = build_research_cited_brief(review)
            except (TypeError, ValueError) as error:
                return f"Research brief was rejected safely: {error}"
            if not brief.claims:
                return (
                    f"Source-backed research brief for {brief.review_id}: no directly supported claims were proposed. "
                    "No final answer was composed."
                )
            lines = [
                f"Source-backed research brief for {brief.review_id} (unverified; not a final answer)",
            ]
            for claim in brief.claims:
                lines.append(f"- {claim.statement}")
                lines.extend(
                    f"  Source: {citation.url} (fetched {datetime.fromtimestamp(citation.fetched_at_epoch, timezone.utc).isoformat()})"
                    for citation in claim.citations
                )
                lines.append(f"  Citation diversity: {claim.citation_diversity}; not verification.")
            lines.append(
                "Deterministic presentation of reviewed claim proposals only; no memory, learning, adventure, or canonical state was created."
            )
            return "\n".join(lines)

        answer_question_match = re.fullmatch(
            r"tool\s+research\s+answer\s+(RR-[0-9a-f]{24})\s*:\s*(.+)",
            command,
            flags=re.IGNORECASE,
        )
        answer_match = re.fullmatch(
            r"tool\s+research\s+answer\s+(RR-[0-9a-f]{24})",
            command,
            flags=re.IGNORECASE,
        )
        if answer_question_match or answer_match:
            matched = answer_question_match or answer_match
            review_id = "RR-" + matched.group(1)[3:]
            review = slot.research_reviews.get(review_id)
            if review is None:
                return "Research claim review was not found in this local session."
            try:
                if answer_question_match:
                    binding = evaluate_research_answer_binding(
                        review,
                        answer_question_match.group(2),
                    )
                    if binding.status != "matches_review":
                        return (
                            "Research answer was rejected safely: the supplied question does not match "
                            "this review's bounded question binding. No model was called and no state was created."
                        )
                decision = evaluate_research_answer_policy(review)
                brief = build_research_cited_brief(review)
            except (TypeError, ValueError) as error:
                return f"Research answer was rejected safely: {error}"
            if decision.status == "insufficient_support":
                return (
                    "Research answer unavailable: no directly supported claims were proposed from the reviewed sources. "
                    "StarFur will not invent an answer."
                )
            lines = [
                "Research answer (source-backed, unverified)",
                "This is a deterministic presentation of explicitly reviewed cited claims, not verified truth:",
            ]
            if answer_question_match:
                lines.append("Question binding: exact reviewed question match.")
            for claim in brief.claims:
                lines.append(f"- {claim.statement}")
                lines.extend(
                    f"  Source: {citation.url} (fetched {datetime.fromtimestamp(citation.fetched_at_epoch, timezone.utc).isoformat()})"
                    for citation in claim.citations
                )
                lines.append(f"  Citation diversity: {claim.citation_diversity}; not verification.")
            lines.append(
                "No model was called for this answer. No memory, learning, adventure, or canonical state was created."
            )
            return "\n".join(lines)

        research_match = re.fullmatch(
            r"tool\s+research\s+((?:TF-[A-Za-z0-9_-]{1,64})(?:\s*,\s*TF-[A-Za-z0-9_-]{1,64}){0,7})\s*:\s*(.+)",
            command,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if research_match:
            if slot.local_web_runtime is None:
                return "Local research source storage is unavailable."
            artifact_refs = tuple(
                "TF-" + item.strip()[3:]
                for item in research_match.group(1).split(",")
            )
            artifacts = []
            for artifact_ref in artifact_refs:
                artifact = slot.local_web_runtime.quarantine.get(artifact_ref)
                if artifact is None:
                    return "Research source was not found in this local session."
                artifacts.append((artifact_ref, artifact))
            try:
                sources = select_research_sources(artifacts)
                packet = build_research_source_packet(research_match.group(2), sources)
                provider = slot.session.local_research_claim_provider()
                target = provider.target
                intent = ResearchDisclosureIntent.from_packet(packet, target)
                decision = evaluate_research_disclosure(intent, packet)
                result = ResearchClaimCoordinator(provider).propose(packet, target, decision)
                review = slot.research_reviews.create(packet, result)
            except ResearchCoordinatorError as error:
                return (
                    f"Research claim generation failed safely ({error.reason}); "
                    "no claim, memory, learning record, or canonical state was published."
                )
            except (TypeError, ValueError, RuntimeError) as error:
                return f"Research request was rejected safely: {error}"
            lines = [
                "Research claim proposals (untrusted; not a final answer)",
                f"Review: {review.review_id} (session-local)",
                "Sources:",
            ]
            lines.extend(
                f"- {source.source_id} {source.url} "
                f"(fetched {datetime.fromtimestamp(source.fetched_at_epoch, timezone.utc).isoformat()})"
                for source in sources
            )
            if result.claims.claims:
                for claim in result.claims.claims:
                    lines.append(
                        f"{claim.claim_id} [confidence {claim.confidence:.2f}] {claim.statement}"
                    )
                    lines.append("  Cites: " + ", ".join(claim.source_ids))
                    evidence = review.evidence.for_claim(claim.claim_id)
                    if evidence is not None:
                        lines.append(
                            f"  Citation diversity: {evidence.citation_diversity} "
                            f"({evidence.cited_source_count} source(s), {evidence.cited_host_count} host(s)); "
                            "not verification."
                        )
            else:
                lines.append("No directly supported claims were proposed from this source.")
            lines.append(
                "Review output only; no final answer, memory, learning, adventure, or canonical state was created."
            )
            lines.append(f"Use tool research inspect {review.review_id} to reopen this claim review.")
            return "\n".join(lines)

        action_match = re.fullmatch(
            r"tool\s+(status|preview|grant|approve|prepare|execute|deny|revoke|cancel)\s+(TI-[A-Za-z0-9_-]{1,64})",
            command,
            flags=re.IGNORECASE,
        )
        if action_match:
            action = action_match.group(1).casefold()
            request_id = "TI-" + action_match.group(2)[3:]
            record = slot.tool_broker.get(request_id)
            if record is None:
                return "Tool request was not found in this local session."
            try:
                if action == "status":
                    return self._format_tool_record(record)
                if action == "preview":
                    arguments = record.proposal.arguments
                    if record.invocation.tool_id == "sandbox.run":
                        files = arguments["files"]
                        file_bytes = sum(len(item["content"].encode("utf-8")) for item in files)
                        lines = [
                            f"Tool proposal preview: {request_id}",
                            "Status: " + record.state,
                            "Tool: sandbox.run v1",
                            "Task kind: " + arguments["task_kind"],
                            "Objective: " + arguments["objective"],
                            f"Inline files: {len(files)} ({file_bytes} UTF-8 bytes)",
                        ]
                        lines.extend(f"- {item['path']}" for item in files)
                        lines.append("Preview only; file contents were not materialized or executed.")
                    elif record.invocation.tool_id == "web.fetch":
                        lines = [
                            f"Tool proposal preview: {request_id}",
                            "Status: " + record.state,
                            "Tool: web.fetch v1",
                            "Exact public URL: " + arguments["url"],
                            "Method: GET; credentials, redirects, proxies, and private disclosure disabled.",
                            "Preview only; no DNS lookup or network request occurred.",
                        ]
                    else:
                        lines = [
                            f"Tool proposal preview: {request_id}",
                            "Status: " + record.state,
                            "Tool: web.search v1",
                            "Public query is intentionally withheld from passive preview.",
                            "Public-data disclosure, service readiness, and explicit confirmation are required.",
                            "Preview only; no provider probe or search request occurred.",
                        ]
                    return "\n".join(lines)
                if action == "grant":
                    record = slot.tool_broker.grant(request_id)
                    return f"Granted one session-local use for {request_id}; explicit approval is still required."
                if action == "approve":
                    record = slot.tool_broker.approve(request_id)
                    if record.invocation.tool_id == "sandbox.run":
                        return f"Approved {request_id} once. Execution remains disabled."
                    return f"Approved {request_id} once. Use tool prepare {request_id} before execution."
                if action == "prepare":
                    if record.state != "approved":
                        return "Tool preparation requires the exact request to be granted and approved first."
                    if record.invocation.tool_id == "web.fetch" and slot.local_web_runtime is not None:
                        destination_record, disclosure_record = (
                            slot.local_web_runtime.prerequisites.prepare_reserved(
                                *record.invocation.resource_refs,
                            )
                        )
                        remaining = destination_record.resolution.expires_at_epoch - time.time()
                        requirement_records = (
                            ("network.destination", destination_record),
                            ("network.disclosure", disclosure_record),
                        )
                        prepared_message = (
                            f"Prepared exact public destination and URL-only disclosure evidence for {request_id}. "
                            "Execute within 25 seconds or create a new request."
                        )
                    elif record.invocation.tool_id == "web.search" and slot.local_web_search_runtime is not None:
                        service_ref, disclosure_ref = record.invocation.resource_refs
                        service_record, disclosure_record = (
                            slot.local_web_search_runtime.prerequisites.prepare_reserved(
                                service_ref,
                                disclosure_ref,
                                slot.local_web_search_runtime.service_observation(service_ref),
                            )
                        )
                        remaining = service_record.expires_at_epoch - time.time()
                        requirement_records = (
                            ("network.search", service_record),
                            ("network.disclosure", disclosure_record),
                        )
                        prepared_message = (
                            f"Prepared exact search-service and public-query disclosure evidence for {request_id}. "
                            "Execute within 25 seconds or create a new request."
                        )
                    else:
                        return "Tool preparation is unavailable for this request."
                    if remaining <= 1:
                        return "Tool preparation expired before it could be recorded; create a new request."
                    for requirement_id, evidence_record in requirement_records:
                        slot.tool_broker.record_prerequisite(
                            request_id,
                            requirement_id=requirement_id,
                            resource_ref=evidence_record.resource_ref,
                            evidence_sha256=evidence_record.evidence_sha256,
                            lifetime_seconds=min(remaining, 25.0),
                        )
                    return prepared_message
                if action == "execute":
                    if (
                        record.invocation.tool_id == "web.fetch"
                        and slot.local_web_runtime is None
                    ) or (
                        record.invocation.tool_id == "web.search"
                        and slot.local_web_search_runtime is None
                    ) or record.invocation.tool_id not in {"web.fetch", "web.search"}:
                        return "Tool execution is unavailable for this request."
                    record = slot.tool_broker.dispatch(request_id, context=context)
                    result = record.result
                    if result is not None and result.artifact_refs:
                        if record.invocation.tool_id == "web.search":
                            return (
                                f"Completed {request_id}; quarantined search artifact: {result.artifact_refs[0]}. "
                                f"Use tool search artifact {result.artifact_refs[0]} to inspect untrusted links."
                            )
                        return (
                            f"Completed {request_id}; quarantined artifact: {result.artifact_refs[0]}. "
                            f"Use tool artifact {result.artifact_refs[0]} to inspect untrusted text."
                        )
                    return f"Tool execution ended [{record.state}] {record.reason}; no artifact is available."
                if action in {"deny", "revoke"}:
                    record = slot.tool_broker.deny(request_id)
                    return f"Revoked and denied {request_id}; it cannot execute."
                record = slot.tool_broker.cancel(request_id)
                return f"Cancelled {request_id}; it cannot execute."
            except (ToolBrokerError, TypeError, ValueError, RuntimeError) as error:
                return f"Tool control was rejected safely: {error}"

        return (
            "Unknown or malformed local tool command. Use tool help. "
            "Tool commands never fall through to model generation."
        )

    def respond(
        self,
        user_text: str,
        *,
        stream_writer: Callable[[str], None] | None = None,
        conversation_id=None,
        external_document_context=None,
        trusted_local_control: bool = False,
    ):
        """Run one chat/command request through its bounded isolated session."""
        return self.respond_completion(
            user_text, stream_writer=stream_writer, conversation_id=conversation_id,
            external_document_context=external_document_context, trusted_local_control=trusted_local_control,
        ).content

    def respond_completion(
        self, user_text: str, *, stream_writer=None, conversation_id=None,
        external_document_context=None, trusted_local_control: bool = False,
    ) -> AssistantResponse:
        """Capture response metadata atomically with the request that produced it."""
        if not isinstance(trusted_local_control, bool):
            raise TypeError("trusted_local_control must be a boolean")
        with self._locked_tool_slot_for(conversation_id) as slot:
            session = slot.session
            session.last_chat_finish_reason = "stop"
            with self._streaming(session, stream_writer):
                if has_ambiguous_multiline_controls(user_text):
                    content = MIXED_CONTROL_INPUT_GUIDANCE
                elif is_context_stats_request(user_text) and getattr(session, "_pending_bulk_proposal_ids", None) is None:
                    reader = getattr(session, "context_stats", None)
                    content = reader() if callable(reader) else "Context diagnostics are unavailable for this session."
                elif self._is_tool_control_namespace(user_text):
                    if not trusted_local_control:
                        content = (
                            "Tool controls are unavailable through shared chat/API requests. "
                            "Use the trusted local Assistant CLI."
                        )
                    else:
                        content = self._local_tool_control(slot, user_text)
                elif external_document_context is None:
                    content = session.respond(user_text)
                else:
                    content = session.respond(user_text, external_document_context=external_document_context)
                reason = getattr(session, "last_chat_finish_reason", None)
                return AssistantResponse(
                    content or "", self._active_model_for_session(session),
                    reason if isinstance(reason, str) and reason in {"stop", "length"} else None,
                )

    def domain_for(self, conversation_id=None) -> str:
        """Return the selected session domain without treating it as client input."""
        with self._locked_session_for(conversation_id) as session:
            return session.config.domain

    def context_stats(self, *, conversation_id=None):
        """Expose the session's bounded, read-only latest-turn diagnostics."""
        with self._locked_session_for(conversation_id) as session:
            return session.context_stats()

    def persona_runtime_snapshot(self, *, conversation_id=None):
        """Return one bounded persona-runtime view without creating or mutating state."""
        with self._locked_existing_session_for(conversation_id) as session:
            runtime = getattr(session, "persona_runtime_state", None)
            public_dict = getattr(runtime, "public_dict", None)
            if not callable(public_dict):
                return {
                    "object": "starfur.persona_runtime",
                    "available": False,
                    "persona": None,
                }
            return {
                "object": "starfur.persona_runtime",
                "available": True,
                "persona": public_dict(),
            }

    def resident_snapshot(self, *, conversation_id=None):
        """Return a compact read-only resident/dashboard view for one session.

        This boundary intentionally observes only existing public session
        summaries while holding the normal conversation lock.  It neither
        seeds runtime state nor reads canonical memory, provider payloads,
        prompt text, candidate content, or hidden adventure resource values.
        """
        with self._locked_existing_tool_slot_for(conversation_id) as slot:
            session = slot.session
            runtime = getattr(session, "persona_runtime_state", None)
            runtime_public = getattr(runtime, "public_dict", None)
            lifecycle = getattr(session, "provider_lifecycle", None)
            lifecycle_public = getattr(lifecycle, "public_dict", None)
            provider = getattr(session, "provider", None)
            health = self._provider_health_for_session(session)
            adventure = getattr(session, "adventure_session", None)
            adventure_public = getattr(adventure, "public_dict", None)
            roleplay = getattr(session, "roleplay_state", None)
            roleplay_public = getattr(roleplay, "public_dict", None)
            turn = getattr(session, "adventure_turn", None)
            ordinary_inbox = getattr(session, "adventure_turn_candidate_inbox", None)
            mutation_inbox = getattr(session, "adventure_turn_mutation_candidate_inbox", None)

            def candidate_count(inbox):
                batch = getattr(inbox, "batch", None)
                candidates = getattr(batch, "candidates", ())
                return len(candidates) if isinstance(candidates, tuple) else 0

            manifest = self.capability_manifest
            route_preview = self._route_diagnostics_for_session(
                session,
                provider_name=getattr(session, "_provider_name", None) or getattr(provider, "name", None),
                provider_health=health,
            )
            route_tasks = route_preview.get("tasks", {})
            task_decisions = tuple(route_tasks.values()) if isinstance(route_tasks, dict) else ()
            routing = {
                "configured_task_count": len(task_decisions),
                "routable_task_count": sum(
                    1 for decision in task_decisions
                    if isinstance(decision, dict) and decision.get("status") == "routable"
                ),
                "unavailable_task_count": sum(
                    1 for decision in task_decisions
                    if isinstance(decision, dict) and decision.get("status") == "unavailable"
                ),
            }
            try:
                metrics = self.system_metrics_provider.snapshot()
                metrics_public = metrics.public_dict()
            except Exception:
                # Dashboard observation is never worth failing an otherwise
                # healthy resident snapshot or leaking host exception text.
                metrics_public = SystemMetricsSnapshot.unavailable("observation_failed").public_dict()
            try:
                sandbox_status = self.sandbox_status_provider.snapshot()
                if not isinstance(sandbox_status, SandboxExecutionStatus):
                    raise TypeError("sandbox status provider returned an invalid value")
                sandbox_public = sandbox_status.public_dict()
            except Exception:
                # Apartment polling must remain safe and must not expose an
                # injected status-source failure or turn it into a probe.
                sandbox_public = SandboxExecutionStatus.observation_failed().public_dict()
            try:
                tool_activity = slot.tool_broker.status_summary().public_dict()
            except Exception:
                # Passive presentation never exposes broker failure details.
                tool_activity = ToolStatusSummary.empty().public_dict()
            snapshot = ResidentSnapshot(
                conversation_id=normalize_conversation_id(conversation_id),
                persona=runtime_public() if callable(runtime_public) else None,
                provider={
                    "name": getattr(session, "_provider_name", None) or getattr(provider, "name", None) or "unknown",
                    "configured": provider_is_configured(provider),
                    "health": health["status"],
                    "model": self._active_model_for_session(session),
                },
                lifecycle=lifecycle_public() if callable(lifecycle_public) else None,
                system_metrics=metrics_public,
                capability_ids=tuple(item.id for item in manifest.capabilities),
                adventure=adventure_public() if callable(adventure_public) else {"mounted": False, "storage": "session_ephemeral"},
                roleplay=roleplay_public() if callable(roleplay_public) else {"active": False, "storage": "session_ephemeral"},
                turn={
                    "active": getattr(turn, "active", False) is True,
                    "staged_count": len(getattr(turn, "drafts", ())),
                    "last_task_routes": _bounded_task_route_trace(
                        (getattr(session, "last_turn_diagnostics", None) or {}).get("task_routes")
                    ),
                },
                candidates={
                    "ordinary_count": candidate_count(ordinary_inbox),
                    "mutation_count": candidate_count(mutation_inbox),
                    "storage": "session_ephemeral",
                },
                routing=routing,
                focus_mode={
                    "enabled": getattr(session, "focus_mode_enabled", False) is True,
                },
                sandbox_execution=sandbox_public,
                tool_activity=tool_activity,
            ).public_dict()
            # A plan contains generic stable asset slots only.  It is derived
            # from the same bounded public snapshot rather than from prompt
            # text, memory, raw provider output, or installed asset paths.
            snapshot["presentation"] = ResidentPresentationPlan.from_resident_snapshot(snapshot).public_dict()
            return snapshot

    def annotate_document(self, document: PreparedDocument, *, annotator=None, progress=None):
        """Return validated external-document candidates without persistence.

        This is intentionally separate from ``respond``: documents are source
        material rather than chat turns, and the result remains review-only.
        ``annotator`` is injectable so presentation/API tests never need Ollama.
        """
        with self._locked_session_for() as session:
            max_attempts = 3
            workload_lease = None
            if annotator is None:
                provider, profile, provider_id = self._document_annotation_route(
                    session, TASK_DOCUMENT_ANNOTATION,
                )
                profiles = getattr(session.config, "task_profiles", TaskProfiles())
                primary = DocumentProposalAnnotator(
                    provider,
                    profile.model,
                    options=profile.options,
                    max_output_tokens=profile.options.get("num_predict", 1024),
                    model_thinking=profile.model_thinking,
                )
                if profile.fallback_task is None:
                    annotator = primary
                else:
                    if profile.fallback_task != TASK_DOCUMENT_ANNOTATION_FALLBACK:
                        raise RuntimeError(
                            "Document annotation fallback must use the explicit "
                            f"{TASK_DOCUMENT_ANNOTATION_FALLBACK!r} profile."
                        )
                    fallback_config = profiles.get(TASK_DOCUMENT_ANNOTATION_FALLBACK)
                    if fallback_config is None or fallback_config.fallback_task is not None:
                        raise RuntimeError("Document annotation fallback profile is invalid.")
                    _, fallback_profile, fallback_provider_id = self._document_annotation_route(
                        session, TASK_DOCUMENT_ANNOTATION_FALLBACK,
                    )
                    if fallback_provider_id != provider_id:
                        raise RuntimeError("Document annotation fallback provider is invalid.")
                    annotator = FailoverDocumentProposalAnnotator(
                        primary,
                        DocumentProposalAnnotator(
                            provider,
                            fallback_profile.model,
                            options=fallback_profile.options,
                            max_output_tokens=fallback_profile.options.get("num_predict", 1024),
                            model_thinking=fallback_profile.model_thinking,
                        ),
                    )
                    max_attempts = annotator.max_attempts
                if self._workload_gate is not None:
                    admission = self._workload_gate.try_acquire(
                        provider_id, profile.max_concurrent_requests or 1,
                    )
                    if admission.lease is None:
                        raise ProviderCapacityBusyError(
                            "selected provider capacity is currently busy"
                        )
                    workload_lease = admission.lease
            lifecycle = getattr(session, "provider_lifecycle", None)
            if lifecycle is not None:
                lifecycle.begin_generation(stream=False, model=getattr(annotator, "model", self._active_model_for_session(session)))
            started_at = perf_counter()
            try:
                result = extract_document_memory_candidates_resilient(
                    document, annotator, max_attempts=max_attempts, progress=progress,
                )
            except Exception as error:
                if lifecycle is not None:
                    lifecycle.fail(error)
                raise
            finally:
                if workload_lease is not None:
                    self._workload_gate.release(workload_lease)
            if lifecycle is not None:
                lifecycle.finish()
            if result.execution is not None:
                result = replace(
                    result,
                    execution=replace(result.execution, elapsed_ms=(perf_counter() - started_at) * 1000),
                )
            return result

    def _document_annotation_route(self, session, task_id):
        """Select one annotation profile through the pure route planner.

        Annotation's separately configured fallback is a content-validation
        retry policy, not permission to silently select another live provider.
        This helper accepts only the requested exact task route; the existing
        bounded fallback adapter remains below this boundary.
        """
        provider = getattr(session, "provider", None)
        if not provider_is_configured(provider):
            raise RuntimeError("Document annotation provider is unavailable.")
        provider_name = getattr(session, "_provider_name", None) or getattr(provider, "name", None) or "unknown"
        provider_status = provider_route_status_from_runtime(
            provider_name,
            configured=True,
            health_status=self._provider_health_for_session(session).get("status"),
        )
        profiles = getattr(session.config, "task_profiles", TaskProfiles())
        decision = TaskRoutePlanner(
            profiles,
            ProviderRouteRegistry({provider_status.provider_id: provider_status}),
        ).plan(
            task_id,
            default_model=self._active_model_for_session(session),
            default_provider_id=provider_status.provider_id,
            base_options={},
        )
        selected = decision.selected
        if selected is None or selected.task_id != task_id:
            raise RuntimeError("Document annotation route is unavailable.")
        focus_deferred = getattr(session, "focus_mode_defers_profile", None)
        if callable(focus_deferred) and focus_deferred(selected.profile):
            raise RuntimeError(
                f"Document annotation task {task_id!r} is deferred by Focus Mode "
                f"({selected.profile.resource_profile} workload)."
            )
        return provider, selected.profile, selected.provider_id

    def create_document_pending_proposal(self, candidate):
        """Explicitly hand one server-reviewed candidate to the normal proposal store."""
        proposal = candidate.proposal
        return self._proposal_creator(
            proposal,
            domain=proposal["domain"],
            source_reference=candidate.source_reference,
            observation_text=candidate.observation_text,
        )

    def create_document_pending_proposals(self, candidates):
        """Hand an already validated review batch to the normal proposal writer.

        Review validation happens before this method is called.  Each candidate
        intentionally still uses the ordinary idempotent writer, so a retried
        batch cannot create duplicate evidence or bypass proposal approval.
        """
        return tuple(
            self.create_document_pending_proposal(candidate)
            for candidate in candidates
        )

    def runtime_diagnostics(self, *, conversation_id=None, probe_provider=False):
        """Return bounded provider/application diagnostics without probing services.

        This snapshot is passive by default: it reports configured
        provider/model and the already-recorded latest turn, but never calls a
        provider, reruns retrieval, or reads a database. ``probe_provider``
        is an explicit non-generating availability check through the provider
        boundary and records only bounded health metadata in session state.
        """
        with self._locked_session_for(conversation_id) as session:
            if probe_provider:
                self._probe_provider_for_session(session)
            provider = getattr(session, "provider", None)
            provider_name = getattr(session, "_provider_name", None) or getattr(provider, "name", None)
            provider_health = self._provider_health_for_session(session)
            snapshot = getattr(session, "last_turn_diagnostics", None) or {}
            phase_timings = dict(snapshot.get("phase_timings") or {})
            latest_turn = None
            if snapshot:
                reason = snapshot.get("finish_reason")
                latest_turn = {
                    "status": snapshot.get("turn_status", "unknown"),
                    "completed": bool(snapshot.get("completed")),
                    "finish_reason": reason if isinstance(reason, str) and reason in {"stop", "length", "unknown"} else None,
                    "model": snapshot.get("model", self._active_model_for_session(session)),
                    "provider": snapshot.get("provider", provider_name or "unknown"),
                    "response_characters": snapshot.get("response_characters", 0),
                    "response_latency_ms": snapshot.get("response_latency_ms"),
                    "time_to_first_token_ms": snapshot.get("time_to_first_token_ms"),
                    "proposal_outcome": snapshot.get("proposal_outcome", "skipped"),
                    "task_routes": _bounded_task_route_trace(snapshot.get("task_routes")),
                    "phase_timings": phase_timings,
                }
            manifest = self.capability_manifest
            routing = self._route_diagnostics_for_session(
                session,
                provider_name=provider_name,
                provider_health=provider_health,
            )
            return {
                "status": "ready" if provider_is_configured(provider) else "provider_unavailable",
                "provider": {
                    "name": provider_name or "unknown",
                    "configured": provider_is_configured(provider),
                    "health": provider_health["status"],
                    "probe_performed": provider_health["probe_performed"],
                    "checked_at": provider_health["checked_at"],
                    "model_count": provider_health["model_count"],
                    "error": provider_health["error"],
                },
                "model": {
                    "active": self._active_model_for_session(session),
                    "startup": getattr(session.config, "chat_model", None),
                },
                "routing": routing,
                "capabilities": {
                    "schema_version": manifest.schema_version,
                    "fingerprint": manifest.fingerprint,
                    "ids": [item.id for item in manifest.capabilities],
                },
                "session": {
                    "latest_turn_available": latest_turn is not None,
                    "conversation": normalize_conversation_id(conversation_id),
                },
                "lifecycle": getattr(session, "provider_lifecycle", None).public_dict() if getattr(session, "provider_lifecycle", None) is not None else None,
                "fallback": {"used": False, "reason": None},
                "latest_turn": latest_turn,
            }

    def _route_diagnostics_for_session(self, session, *, provider_name, provider_health):
        """Build a passive route preview without probing or calling a provider."""
        provider = getattr(session, "provider", None)
        status = provider_route_status_from_runtime(
            provider_name or "unknown",
            configured=provider_is_configured(provider),
            health_status=provider_health.get("status"),
        )
        profiles = getattr(session.config, "task_profiles", TaskProfiles())
        planner = TaskRoutePlanner(profiles, ProviderRouteRegistry({status.provider_id: status}))
        task_ids = tuple(sorted(profiles.profiles)) or ("assistant_chat",)
        return {
            "provider": {"id": status.provider_id, "status": status.status},
            "tasks": {
                task_id: planner.plan(
                    task_id,
                    default_model=self._active_model_for_session(session),
                    default_provider_id=status.provider_id,
                ).public_dict()
                for task_id in task_ids
            },
        }


def create_assistant_application(
    config_path=None,
    *,
    stream=False,
    stream_writer=None,
    debug_level=None,
    capability_registry: CapabilityRegistry | None = None,
    session_factory=AssistantSession,
    max_conversations: int = DEFAULT_MAX_CONVERSATIONS,
    retriever: MemoryRetriever | None = None,
    system_metrics_provider: SystemMetricsProvider | None = None,
    sandbox_status_provider: SandboxExecutionStatusProvider | None = None,
    provider: ChatProvider | None = None,
    provider_registry: ChatProviderRegistry | None = None,
    enable_native_web_tools: bool = False,
    enable_brave_web_search: bool = False,
    enable_tavily_web_search: bool = False,
    local_web_runtime_factory: Callable[[], object] | None = None,
    local_web_search_runtime_factory: Callable[[], object] | None = None,
    provider_process_gate_root: Path | str | None = None,
):
    """Create the standard Assistant Mode application for any presentation client."""
    if not isinstance(enable_native_web_tools, bool):
        raise TypeError("enable_native_web_tools must be a boolean")
    if not isinstance(enable_brave_web_search, bool):
        raise TypeError("enable_brave_web_search must be a boolean")
    if not isinstance(enable_tavily_web_search, bool):
        raise TypeError("enable_tavily_web_search must be a boolean")
    if enable_brave_web_search and enable_tavily_web_search:
        raise ValueError("select exactly one hosted web search provider")
    if local_web_runtime_factory is not None and not callable(local_web_runtime_factory):
        raise TypeError("local_web_runtime_factory must be callable or None")
    if local_web_search_runtime_factory is not None and not callable(local_web_search_runtime_factory):
        raise TypeError("local_web_search_runtime_factory must be callable or None")
    if provider_process_gate_root is not None:
        provider_process_gate_root = Path(provider_process_gate_root)
        if not provider_process_gate_root.is_absolute():
            raise ValueError("provider_process_gate_root must be absolute")
    if enable_native_web_tools and local_web_runtime_factory is None:
        from pipeline.tool_web_native import build_native_web_tool_runtime
        local_web_runtime_factory = build_native_web_tool_runtime
    if enable_brave_web_search and local_web_search_runtime_factory is None:
        from pipeline.tool_web_search_brave_native import create_brave_web_search_runtime
        local_web_search_runtime_factory = create_brave_web_search_runtime
    if enable_tavily_web_search and local_web_search_runtime_factory is None:
        from pipeline.tool_web_search_tavily_native import create_tavily_web_search_runtime
        local_web_search_runtime_factory = create_tavily_web_search_runtime
    config = load_config(config_path) if config_path else load_config()
    registry = capability_registry or build_core_capability_registry()
    manifest = registry.build_manifest()
    shared_retriever = retriever or DeterministicMemoryRetriever()
    persona_registry = getattr(config, "persona_registry", None)
    if persona_registry is None:
        persona_registry = PersonaRegistry((load_persona_package(config.persona_path),))
    active_persona_id = getattr(config, "active_persona_id", None) or load_persona_package(config.persona_path).persona_id
    active_persona = persona_registry.get(active_persona_id)
    if active_persona is None:
        raise ValueError("Configured active persona package was not found.")
    # Shared only within this application process, never persisted or mixed
    # with canonical user memory.  New UI/API sessions can select personas
    # without accidentally adopting another persona's runtime snapshot.
    persona_runtime_registry = PersonaRuntimeRegistry()
    installed_asset_packages = tuple(
        InstalledPersonaAssetPackage(
            package.asset_manifest
            or (BUILTIN_MURR_ASSET_MANIFEST if package.persona_id == "murr" else None),
            PROJECT_ROOT,
        )
        for package in persona_registry.packages()
        if package.asset_manifest is not None or package.persona_id == "murr"
    )
    if provider_registry is not None and provider is None:
        raise ValueError("provider_registry requires an explicit active provider")
    def make_session():
        kwargs = dict(
            policy=load_policy(config.policy_path),
            proposal_creator=upsert_assistant_memory_proposal,
            stream=stream,
            stream_writer=stream_writer,
            debug_level=debug_level,
            retriever=shared_retriever,
        )
        if provider is not None:
            kwargs["provider"] = provider
        if provider_registry is not None:
            kwargs["provider_registry"] = provider_registry
        if getattr(config, "persona_registry", None) is not None:
            kwargs["persona_registry"] = persona_registry
            kwargs["persona_runtime_registry"] = persona_runtime_registry
            persona = active_persona
        else:
            persona = load_persona(config.persona_path)
        return session_factory(
            config,
            persona,
            **kwargs,
        )

    initial_session = make_session()
    workload_gate = None
    if provider_process_gate_root is not None:
        provider_process_gate_root.mkdir(parents=True, exist_ok=True)
        provider_ids = tuple(initial_session.chat_provider_registry.provider_ids())
        if provider_ids:
            workload_gate = ProviderWorkloadGate(
                {provider_id: 1 for provider_id in provider_ids},
                process_gate=ProviderProcessGate(provider_process_gate_root),
            )
    return AssistantApplication(
        initial_session,
        capability_manifest=manifest,
        session_factory=make_session,
        max_conversations=max_conversations,
        retriever=shared_retriever,
        system_metrics_provider=system_metrics_provider or LocalSystemMetricsProvider(),
        sandbox_status_provider=sandbox_status_provider,
        persona_asset_resolver=PersonaAssetResolver(installed_asset_packages),
        local_web_runtime_factory=local_web_runtime_factory,
        local_web_search_runtime_factory=local_web_search_runtime_factory,
        workload_gate=workload_gate,
    )


__all__ = [
    "AssistantApplication",
    "AssistantResponse",
    "ConversationNotFoundError",
    "DEFAULT_CONVERSATION_ID",
    "DEFAULT_MAX_CONVERSATIONS",
    "DEFAULT_PROVIDER_PROCESS_GATE_ROOT",
    "create_assistant_application",
    "normalize_conversation_id",
]
