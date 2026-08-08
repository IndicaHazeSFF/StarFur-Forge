"""Presentation-neutral application boundary for Assistant Mode.

``AssistantApplication`` owns bounded, ephemeral ``AssistantSession`` objects
for presentation conversations. Canonical memory remains shared through the
existing domain-aware storage primitives; only recent messages, active model,
last-selected memories, and confirmation state are isolated per conversation.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
import re
import threading
from typing import Callable, Iterator

from pipeline.assistant import AssistantSession, load_config, load_persona, load_policy
from pipeline.capabilities import CapabilityManifest, CapabilityRegistry, build_core_capability_registry
from pipeline.db import upsert_assistant_memory_proposal
from pipeline.document_annotation import DocumentProposalAnnotator
from pipeline.document_intake import PreparedDocument, extract_document_memory_candidates_resilient


DEFAULT_CONVERSATION_ID = "default"
DEFAULT_MAX_CONVERSATIONS = 16
_CONVERSATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}\Z")


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
    ):
        if max_conversations <= 0:
            raise ValueError("max_conversations must be positive.")
        self.session = session
        self.capability_manifest = capability_manifest or build_core_capability_registry().build_manifest()
        self._lock = threading.RLock()
        self._proposal_creator = proposal_creator
        self._session_factory = session_factory
        self._max_conversations = max_conversations
        self._sessions = OrderedDict([(DEFAULT_CONVERSATION_ID, session)])
        self._attach_capability_manifest(session)

    def _attach_capability_manifest(self, session):
        setter = getattr(session, "set_capability_manifest", None)
        if callable(setter):
            setter(self.capability_manifest)

    def _session_for(self, conversation_id=None):
        """Return one ephemeral session, creating/evicting only non-default ones.

        This method is called while ``_lock`` is held. The legacy default
        session is retained permanently for CLI and clients that omit a key.
        Additional sessions are least-recently-used and never write session
        state to SQLite or Chroma when evicted.
        """
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
        self._attach_capability_manifest(session)
        self._sessions[key] = session
        self._evict_sessions_if_needed()
        return session

    def _evict_sessions_if_needed(self):
        """Keep only the configured number of non-default in-memory sessions."""
        while len(self._sessions) - 1 > self._max_conversations:
            key = next(key for key in self._sessions if key != DEFAULT_CONVERSATION_ID)
            del self._sessions[key]

    @staticmethod
    def _active_model_for_session(session):
        return getattr(session, "active_model", None) or getattr(session.config, "chat_model", "unknown")

    @property
    def active_model(self):
        return self.active_model_for()

    def active_model_for(self, conversation_id=None):
        with self._lock:
            return self._active_model_for_session(self._session_for(conversation_id))

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

    def respond(self, user_text: str, *, stream_writer: Callable[[str], None] | None = None, conversation_id=None):
        """Run one chat/command request through its bounded isolated session."""
        with self._lock:
            session = self._session_for(conversation_id)
            with self._streaming(session, stream_writer):
                return session.respond(user_text)

    def context_stats(self, *, conversation_id=None):
        """Expose the session's bounded, read-only latest-turn diagnostics."""
        with self._lock:
            return self._session_for(conversation_id).context_stats()

    def annotate_document(self, document: PreparedDocument, *, annotator=None):
        """Return validated external-document candidates without persistence.

        This is intentionally separate from ``respond``: documents are source
        material rather than chat turns, and the result remains review-only.
        ``annotator`` is injectable so presentation/API tests never need Ollama.
        """
        with self._lock:
            session = self._session_for()
            if annotator is None:
                provider = getattr(session, "provider", None)
                if provider is None:
                    raise RuntimeError("Document annotation provider is unavailable.")
                annotator = DocumentProposalAnnotator(provider, self._active_model_for_session(session))
            lifecycle = getattr(session, "provider_lifecycle", None)
            if lifecycle is not None:
                lifecycle.begin_generation(stream=False, model=self._active_model_for_session(session))
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
        with self._lock:
            proposal = candidate.proposal
            return self._proposal_creator(
                proposal,
                domain=proposal["domain"],
                source_reference=candidate.source_reference,
                observation_text=candidate.observation_text,
            )

    def runtime_diagnostics(self, *, conversation_id=None):
        """Return bounded provider/application diagnostics without probing services.

        This snapshot is intentionally observational: it reports configured
        provider/model and the already-recorded latest turn, but never calls a
        provider, reruns retrieval, or reads a database.
        """
        with self._lock:
            session = self._session_for(conversation_id)
            provider = getattr(session, "provider", None)
            provider_name = getattr(session, "_provider_name", None) or getattr(provider, "name", None)
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
                    "health": "not_probed",
                    "probe_performed": False,
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
):
    """Create the standard Assistant Mode application for any presentation client."""
    config = load_config(config_path) if config_path else load_config()
    registry = capability_registry or build_core_capability_registry()
    manifest = registry.build_manifest()
    def make_session():
        return session_factory(
            config,
            load_persona(config.persona_path),
            policy=load_policy(config.policy_path),
            proposal_creator=upsert_assistant_memory_proposal,
            stream=stream,
            stream_writer=stream_writer,
            debug_level=debug_level,
        )

    return AssistantApplication(
        make_session(),
        capability_manifest=manifest,
        session_factory=make_session,
        max_conversations=max_conversations,
    )


__all__ = [
    "AssistantApplication",
    "DEFAULT_CONVERSATION_ID",
    "DEFAULT_MAX_CONVERSATIONS",
    "create_assistant_application",
    "normalize_conversation_id",
]
