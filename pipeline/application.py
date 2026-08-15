"""Presentation-neutral application boundary for Assistant Mode.

``AssistantApplication`` owns bounded, ephemeral ``AssistantSession`` objects
for presentation conversations. Canonical memory remains shared through the
existing domain-aware storage primitives; only recent messages, active model,
last-selected memories, and confirmation state are isolated per conversation.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import threading
from typing import Callable, Iterator

from pipeline.assistant import AssistantSession, load_config, load_persona, load_policy
from pipeline.capabilities import CapabilityManifest, CapabilityRegistry, build_core_capability_registry
from pipeline.db import upsert_assistant_memory_proposal
from pipeline.document_annotation import DocumentProposalAnnotator
from pipeline.document_intake import PreparedDocument, extract_document_memory_candidates_resilient
from pipeline.retrieval import DeterministicMemoryRetriever, MemoryRetriever
from pipeline.task_profiles import TASK_DOCUMENT_ANNOTATION, TaskProfiles, provider_matches
from pipeline.persona_registry import PersonaRegistry, load_persona_package
from pipeline.persona_runtime import PersonaRuntimeRegistry


DEFAULT_CONVERSATION_ID = "default"
DEFAULT_MAX_CONVERSATIONS = 16
_CONVERSATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")


@dataclass
class _SessionSlot:
    """One bounded ephemeral session plus its request-serialization state."""

    session: AssistantSession
    lock: threading.RLock
    active_requests: int = 0


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
    ):
        if max_conversations <= 0:
            raise ValueError("max_conversations must be positive.")
        self.session = session
        self.retriever = retriever or getattr(session, "retriever", None)
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

    @staticmethod
    def _model_count_from_probe(response):
        models = response.get("models") if isinstance(response, dict) else getattr(response, "models", None)
        return len(models) if isinstance(models, (list, tuple)) else None

    def _probe_provider_for_session(self, session):
        """Run one explicit non-generating provider probe and retain its result."""
        provider = getattr(session, "provider", None)
        checked_at = datetime.now(timezone.utc).isoformat()
        probe = getattr(provider, "probe_health", None)
        if not callable(probe):
            snapshot = {
                "status": "unsupported",
                "probe_performed": True,
                "checked_at": checked_at,
                "model_count": None,
                "error": "Provider health probing is unavailable.",
            }
        else:
            try:
                response = probe()
            except NotImplementedError as error:
                snapshot = {
                    "status": "unsupported",
                    "probe_performed": True,
                    "checked_at": checked_at,
                    "model_count": None,
                    "error": str(error)[:300],
                }
            except Exception as error:
                snapshot = {
                    "status": "unavailable",
                    "probe_performed": True,
                    "checked_at": checked_at,
                    "model_count": None,
                    "error": str(error)[:300],
                }
            else:
                snapshot = {
                    "status": "healthy",
                    "probe_performed": True,
                    "checked_at": checked_at,
                    "model_count": self._model_count_from_probe(response),
                    "error": None,
                }
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
            return self._session_slot_for(conversation_id).session

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
        self._sessions[key] = _SessionSlot(session, threading.RLock())
        self._evict_sessions_if_needed()
        return self._sessions[key]

    def _evict_sessions_if_needed(self):
        """Keep only the configured number of non-default in-memory sessions."""
        while len(self._sessions) - 1 > self._max_conversations:
            evictable_key = next(
                (
                    key for key, slot in self._sessions.items()
                    if key != DEFAULT_CONVERSATION_ID and slot.active_requests == 0
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
        with self._locked_session_for(conversation_id) as session:
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

    def annotate_document(self, document: PreparedDocument, *, annotator=None):
        """Return validated external-document candidates without persistence.

        This is intentionally separate from ``respond``: documents are source
        material rather than chat turns, and the result remains review-only.
        ``annotator`` is injectable so presentation/API tests never need Ollama.
        """
        with self._locked_session_for() as session:
            if annotator is None:
                provider = getattr(session, "provider", None)
                if provider is None:
                    raise RuntimeError("Document annotation provider is unavailable.")
                profiles = getattr(session.config, "task_profiles", TaskProfiles())
                profile = profiles.resolve(
                    TASK_DOCUMENT_ANNOTATION,
                    default_model=self._active_model_for_session(session),
                    base_options={},
                )
                if not provider_matches(profile.provider, getattr(provider, "name", None)):
                    raise RuntimeError(
                        f"Task profile {TASK_DOCUMENT_ANNOTATION!r} requires provider {profile.provider!r}; "
                        f"active provider is {getattr(provider, 'name', 'unknown')!r}."
                    )
                annotator = DocumentProposalAnnotator(
                    provider,
                    profile.model,
                    options=profile.options,
                    max_output_tokens=profile.options.get("num_predict", 1024),
                )
            lifecycle = getattr(session, "provider_lifecycle", None)
            if lifecycle is not None:
                lifecycle.begin_generation(stream=False, model=getattr(annotator, "model", self._active_model_for_session(session)))
            try:
                result = extract_document_memory_candidates_resilient(document, annotator)
            except Exception as error:
                if lifecycle is not None:
                    lifecycle.fail(error)
                raise
            if lifecycle is not None:
                lifecycle.finish()
            return result

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
                    "phase_timings": phase_timings,
                }
            manifest = self.capability_manifest
            return {
                "status": "ready" if provider is not None else "provider_unavailable",
                "provider": {
                    "name": provider_name or "unknown",
                    "configured": provider is not None,
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
    def make_session():
        kwargs = dict(
            policy=load_policy(config.policy_path),
            proposal_creator=upsert_assistant_memory_proposal,
            stream=stream,
            stream_writer=stream_writer,
            debug_level=debug_level,
            retriever=shared_retriever,
        )
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
    )


__all__ = [
    "AssistantApplication",
    "DEFAULT_CONVERSATION_ID",
    "DEFAULT_MAX_CONVERSATIONS",
    "create_assistant_application",
    "normalize_conversation_id",
]
