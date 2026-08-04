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
from pipeline.db import upsert_assistant_memory_proposal


class AssistantApplication:
    """Shared application facade around a single Assistant Mode session."""

    def __init__(self, session: AssistantSession):
        self.session = session
        self._lock = threading.RLock()

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


def create_assistant_application(
    config_path=None,
    *,
    stream=False,
    stream_writer=None,
    debug_level=None,
    session_factory=AssistantSession,
):
    """Create the standard Assistant Mode application for any presentation client."""
    config = load_config(config_path) if config_path else load_config()
    session = session_factory(
        config,
        load_persona(config.persona_path),
        policy=load_policy(config.policy_path),
        proposal_creator=upsert_assistant_memory_proposal,
        stream=stream,
        stream_writer=stream_writer,
        debug_level=debug_level,
    )
    return AssistantApplication(session)


__all__ = ["AssistantApplication", "create_assistant_application"]
