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
import re
import threading
from time import perf_counter
from typing import Callable, Iterator

from pipeline.assistant import PROJECT_ROOT, AssistantSession, load_config, load_persona, load_policy
from pipeline.capabilities import CapabilityManifest, CapabilityRegistry, build_core_capability_registry
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
from pipeline.persona_asset_resolver import InstalledPersonaAssetPackage, PersonaAssetResolver
from pipeline.persona_assets import BUILTIN_MURR_ASSET_MANIFEST
from pipeline.persona_registry import PersonaRegistry, load_persona_package
from pipeline.persona_runtime import PersonaRuntimeRegistry
from pipeline.provider_registry import ChatProviderRegistry
from pipeline.providers import ChatProvider, provider_health_snapshot, provider_is_configured
from pipeline.resident_presentation import ResidentPresentationPlan
from pipeline.resident_snapshot import ResidentSnapshot
from pipeline.system_metrics import LocalSystemMetricsProvider, NullSystemMetricsProvider, SystemMetricsProvider, SystemMetricsSnapshot


DEFAULT_CONVERSATION_ID = "default"
DEFAULT_MAX_CONVERSATIONS = 16
_CONVERSATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")
_ROUTE_TRACE_ID_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_ROUTE_TRACE_OUTCOMES = frozenset({
    "submitted", "completed", "route_unavailable", "provider_adapter_unavailable",
    "provider_request_failed", "provider_stream_failed", "provider_stream_cancelled",
})


@dataclass
class _SessionSlot:
    """One bounded ephemeral session plus its request-serialization state."""

    session: AssistantSession
    lock: threading.RLock
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
        bounded.append({
            "requested_task_id": requested,
            "selected_task_id": selected,
            "provider": provider,
            "model": model,
            "fallback_used": fallback_used,
            "outcome": outcome,
        })
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
        persona_asset_resolver: PersonaAssetResolver | None = None,
    ):
        if max_conversations <= 0:
            raise ValueError("max_conversations must be positive.")
        self.session = session
        self.retriever = retriever or getattr(session, "retriever", None)
        self.system_metrics_provider = system_metrics_provider or NullSystemMetricsProvider()
        if not callable(getattr(self.system_metrics_provider, "snapshot", None)):
            raise TypeError("system_metrics_provider must provide a callable snapshot method.")
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
        self._sessions = OrderedDict([
            (DEFAULT_CONVERSATION_ID, _SessionSlot(session, threading.RLock())),
        ])
        self._initialize_provider_health(session)
        self._attach_capability_manifest(session)
        self._attach_retriever(session)

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
        # Do not evict here.  A newly created slot is not yet request-pinned,
        # so eviction at this point can select and remove the very slot this
        # method is about to return when older conversations are busy.
        slot = _SessionSlot(session, threading.RLock())
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

    def respond(
        self,
        user_text: str,
        *,
        stream_writer: Callable[[str], None] | None = None,
        conversation_id=None,
        external_document_context=None,
    ):
        """Run one chat/command request through its bounded isolated session."""
        with self._locked_session_for(conversation_id) as session:
            with self._streaming(session, stream_writer):
                if external_document_context is None:
                    return session.respond(user_text)
                return session.respond(user_text, external_document_context=external_document_context)

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
        with self._locked_existing_session_for(conversation_id) as session:
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
            if annotator is None:
                provider, profile = self._document_annotation_route(
                    session, TASK_DOCUMENT_ANNOTATION,
                )
                profiles = getattr(session.config, "task_profiles", TaskProfiles())
                primary = DocumentProposalAnnotator(
                    provider,
                    profile.model,
                    options=profile.options,
                    max_output_tokens=profile.options.get("num_predict", 1024),
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
                    _, fallback_profile = self._document_annotation_route(
                        session, TASK_DOCUMENT_ANNOTATION_FALLBACK,
                    )
                    annotator = FailoverDocumentProposalAnnotator(
                        primary,
                        DocumentProposalAnnotator(
                            provider,
                            fallback_profile.model,
                            options=fallback_profile.options,
                            max_output_tokens=fallback_profile.options.get("num_predict", 1024),
                        ),
                    )
                    max_attempts = annotator.max_attempts
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
        return provider, selected.profile

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
                latest_turn = {
                    "status": snapshot.get("turn_status", "unknown"),
                    "completed": bool(snapshot.get("completed")),
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
    provider: ChatProvider | None = None,
    provider_registry: ChatProviderRegistry | None = None,
):
    """Create the standard Assistant Mode application for any presentation client."""
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

    return AssistantApplication(
        make_session(),
        capability_manifest=manifest,
        session_factory=make_session,
        max_conversations=max_conversations,
        retriever=shared_retriever,
        system_metrics_provider=system_metrics_provider or LocalSystemMetricsProvider(),
        persona_asset_resolver=PersonaAssetResolver(installed_asset_packages),
    )


__all__ = [
    "AssistantApplication",
    "ConversationNotFoundError",
    "DEFAULT_CONVERSATION_ID",
    "DEFAULT_MAX_CONVERSATIONS",
    "create_assistant_application",
    "normalize_conversation_id",
]
