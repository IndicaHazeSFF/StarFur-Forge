"""Presentation-neutral application boundary for Assistant Mode.

``AssistantApplication`` is intentionally thin: it owns one stateful
``AssistantSession`` and serializes requests from terminal and web clients.
The session remains responsible for commands, retrieval, prompting, proposal
handling, and turn diagnostics.
"""

from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Callable, Iterator

from pipeline.assistant import AssistantSession, load_config, load_persona, load_policy
from pipeline.capabilities import CapabilityManifest, CapabilityRegistry, build_core_capability_registry
from pipeline.db import upsert_assistant_memory_proposal
from pipeline.document_annotation import DocumentProposalAnnotator
from pipeline.document_intake import PreparedDocument, extract_document_memory_candidates_resilient


class AssistantApplication:
    """Shared application facade around a single Assistant Mode session."""

    def __init__(
        self,
        session: AssistantSession,
        *,
        capability_manifest: CapabilityManifest | None = None,
        proposal_creator=upsert_assistant_memory_proposal,
    ):
        self.session = session
        self.capability_manifest = capability_manifest or build_core_capability_registry().build_manifest()
        setter = getattr(session, "set_capability_manifest", None)
        if callable(setter):
            setter(self.capability_manifest)
        self._lock = threading.RLock()
        self._proposal_creator = proposal_creator

    @property
    def active_model(self):
        return getattr(self.session, "active_model", None) or getattr(self.session.config, "chat_model", "unknown")

    @contextmanager
    def _streaming(self, stream_writer: Callable[[str], None] | None) -> Iterator[None]:
        """Temporarily route one request through a presentation stream writer."""
        if stream_writer is None:
            yield
            return
        old_stream = getattr(self.session, "stream", False)
        old_writer = getattr(self.session, "stream_writer", None)
        self.session.stream = True
        self.session.stream_writer = stream_writer
        try:
            yield
        finally:
            self.session.stream = old_stream
            self.session.stream_writer = old_writer

    def respond(self, user_text: str, *, stream_writer: Callable[[str], None] | None = None):
        """Run one chat or interactive-command request through the shared session."""
        with self._lock:
            with self._streaming(stream_writer):
                return self.session.respond(user_text)

    def context_stats(self):
        """Expose the session's bounded, read-only latest-turn diagnostics."""
        with self._lock:
            return self.session.context_stats()

    def annotate_document(self, document: PreparedDocument, *, annotator=None):
        """Return validated external-document candidates without persistence.

        This is intentionally separate from ``respond``: documents are source
        material rather than chat turns, and the result remains review-only.
        ``annotator`` is injectable so presentation/API tests never need Ollama.
        """
        with self._lock:
            if annotator is None:
                provider = getattr(self.session, "provider", None)
                if provider is None:
                    raise RuntimeError("Document annotation provider is unavailable.")
                annotator = DocumentProposalAnnotator(provider, self.active_model)
            lifecycle = getattr(self.session, "provider_lifecycle", None)
            if lifecycle is not None:
                lifecycle.begin_generation(stream=False, model=self.active_model)
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

    def runtime_diagnostics(self):
        """Return bounded provider/application diagnostics without probing services.

        This snapshot is intentionally observational: it reports configured
        provider/model and the already-recorded latest turn, but never calls a
        provider, reruns retrieval, or reads a database.
        """
        with self._lock:
            provider = getattr(self.session, "provider", None)
            provider_name = getattr(self.session, "_provider_name", None) or getattr(provider, "name", None)
            snapshot = getattr(self.session, "last_turn_diagnostics", None) or {}
            phase_timings = dict(snapshot.get("phase_timings") or {})
            latest_turn = None
            if snapshot:
                latest_turn = {
                    "status": snapshot.get("turn_status", "unknown"),
                    "completed": bool(snapshot.get("completed")),
                    "model": snapshot.get("model", self.active_model),
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
                    "active": self.active_model,
                    "startup": getattr(self.session.config, "chat_model", None),
                },
                "capabilities": {
                    "schema_version": manifest.schema_version,
                    "fingerprint": manifest.fingerprint,
                    "ids": [item.id for item in manifest.capabilities],
                },
                "session": {"latest_turn_available": latest_turn is not None},
                "lifecycle": getattr(self.session, "provider_lifecycle", None).public_dict() if getattr(self.session, "provider_lifecycle", None) is not None else None,
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
):
    """Create the standard Assistant Mode application for any presentation client."""
    config = load_config(config_path) if config_path else load_config()
    registry = capability_registry or build_core_capability_registry()
    manifest = registry.build_manifest()
    session = session_factory(
        config,
        load_persona(config.persona_path),
        policy=load_policy(config.policy_path),
        proposal_creator=upsert_assistant_memory_proposal,
        stream=stream,
        stream_writer=stream_writer,
        debug_level=debug_level,
    )
    return AssistantApplication(session, capability_manifest=manifest)


__all__ = ["AssistantApplication", "create_assistant_application"]
