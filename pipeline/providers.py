"""Small, explicit provider interfaces for StarFur runtime capabilities.

Only chat is implemented here.  The boundary keeps provider-specific API calls
out of assistant orchestration while retaining a callable adapter for legacy
tests and integrations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol, runtime_checkable


ChatMessages = Iterable[Mapping[str, str]]
CHAT_FINISH_REASONS = frozenset({"stop", "length", "unknown"})


def _validate_finish_reason(value) -> None:
    if value is not None and (not isinstance(value, str) or value not in CHAT_FINISH_REASONS):
        raise ValueError("chat finish reason is invalid")


class ChatProviderResponseError(ValueError):
    """Raised when an adapter result has no usable text completion."""


class ChatProviderOutputLimitError(ChatProviderResponseError):
    """A reported output limit, with no partial content or provider payload."""

    def __init__(self) -> None:
        super().__init__("structured response reached its output limit")


@dataclass(frozen=True)
class ChatCompletion:
    """Provider-neutral text and bounded completion status for Core consumers.

    This retains only text and an optional closed completion reason, never
    provider payload, thinking text, token accounting, or tool-call data.
    Task-specific layers remain responsible for size limits and validation.
    """

    content: str
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("chat completion content must be text")
        _validate_finish_reason(self.finish_reason)


@dataclass(frozen=True)
class ChatStreamChunk:
    """One provider-neutral text fragment from an optional streamed result."""

    content: str
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("chat stream chunk content must be text")
        _validate_finish_reason(self.finish_reason)


def _raw_chat_content(value: object) -> str | None:
    """Extract the one supported text field without preserving raw output."""
    if isinstance(value, (ChatCompletion, ChatStreamChunk)):
        return value.content
    if isinstance(value, Mapping):
        message = value.get("message")
        content = message.get("content") if isinstance(message, Mapping) else value.get("content")
    else:
        message = getattr(value, "message", None)
        content = getattr(message, "content", None) if message is not None else getattr(value, "content", None)
    return content if isinstance(content, str) else None


def normalize_chat_completion(value: object) -> ChatCompletion:
    """Normalize one complete adapter result into the Core text contract."""
    content = _raw_chat_content(value)
    if content is None:
        raise ChatProviderResponseError("chat provider response has no text content")
    return ChatCompletion(content, value.finish_reason if isinstance(value, (ChatCompletion, ChatStreamChunk)) else None)


def normalize_chat_stream_chunk(value: object) -> ChatStreamChunk:
    """Normalize one optional streaming fragment into the Core text contract."""
    content = _raw_chat_content(value)
    if content is None:
        raise ChatProviderResponseError("chat provider stream chunk has no text content")
    return ChatStreamChunk(content, value.finish_reason if isinstance(value, (ChatCompletion, ChatStreamChunk)) else None)


def normalize_structured_chat_completion(value: object) -> ChatCompletion:
    """Reject provider-reported truncation before any structured task parser.

    Only the typed adapter seam supplies completion status. Raw dictionaries
    cannot supply trusted terminal metadata, and unreported status stays unknown.
    Complete-looking JSON is still ineligible when the adapter reports length.
    """
    completion = normalize_chat_completion(value)
    if completion.finish_reason == "length":
        raise ChatProviderOutputLimitError()
    return completion


def provider_is_configured(provider: object) -> bool:
    """Return whether Core may route work to an adapter.

    A disabled adapter preserves the resident runtime without pretending that
    an LLM is configured. Existing adapters remain configured by default.
    """
    return provider is not None and getattr(provider, "configured", True) is not False


def provider_health_snapshot(provider: object) -> dict[str, object]:
    """Run one bounded, non-generating provider health probe.

    The result is caller-owned ephemeral state. It deliberately retains only
    availability metadata, never a provider payload or exception object.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    probe = getattr(provider, "probe_health", None)
    if not callable(probe):
        return {
            "status": "unsupported", "probe_performed": True,
            "checked_at": checked_at, "model_count": None,
            "error": "Provider health probing is unavailable.",
        }
    try:
        response = probe()
    except NotImplementedError as error:
        return {
            "status": "unsupported", "probe_performed": True,
            "checked_at": checked_at, "model_count": None, "error": str(error)[:300],
        }
    except Exception as error:
        return {
            "status": "unavailable", "probe_performed": True,
            "checked_at": checked_at, "model_count": None, "error": str(error)[:300],
        }
    models = response.get("models") if isinstance(response, dict) else getattr(response, "models", None)
    return {
        "status": "healthy", "probe_performed": True,
        "checked_at": checked_at,
        "model_count": len(models) if isinstance(models, (list, tuple)) else None,
        "error": None,
    }


@runtime_checkable
class ChatCompletionProvider(Protocol):
    """The minimum text-generation capability required for one routed task."""

    def complete(
        self,
        messages: ChatMessages,
        *,
        model: str | None = None,
        options: Mapping[str, Any] | None = None,
        stream: bool = False,
        keep_alive_seconds: int | None = None,
    ) -> Any:
        """Return a provider response or a provider streaming iterator."""


@runtime_checkable
class StructuredChatCompletionProvider(Protocol):
    """Optional provider capability for one complete JSON-schema result.

    Core owns the schema and still validates the returned text itself. Merely
    implementing this protocol does not grant a provider authority, select a
    task route, permit fallback, or make the response trustworthy.

    An adapter may use an interruptible streaming transport internally, but it
    must return one complete provider-neutral result to Core. Transport
    fragments never cross this seam.
    """

    def complete_structured(
        self,
        messages: ChatMessages,
        *,
        schema: Mapping[str, Any],
        model: str | None = None,
        options: Mapping[str, Any] | None = None,
        keep_alive_seconds: int | None = None,
    ) -> Any:
        """Return one provider response constrained by a Core-owned schema."""


@runtime_checkable
class ChatProvider(ChatCompletionProvider, Protocol):
    """A chat adapter with optional model discovery and health probing."""

    name: str

    def list_models(self) -> Any:
        """Return the provider's installed/available model response."""

    def probe_health(self) -> Any:
        """Perform one provider-owned, read-only availability probe."""


class OllamaChatProvider:
    """Thin adapter over the supported Ollama Python client API."""

    name = "Ollama"
    supports_model_keep_alive_seconds = True
    supports_model_thinking = True

    def __init__(self, client: Any):
        self._client = client

    @staticmethod
    def _thinking_kwargs(thinking):
        if thinking is None:
            return {}
        if not isinstance(thinking, bool):
            raise ValueError("thinking control must be a boolean")
        return {"think": thinking}

    @staticmethod
    def _finish_reason(response):
        reason = response.get("done_reason") if isinstance(response, Mapping) else getattr(response, "done_reason", None)
        if reason is None or reason == "":
            return None
        return reason if isinstance(reason, str) and reason in {"stop", "length"} else "unknown"

    @classmethod
    def _stream(cls, response):
        try:
            for chunk in response:
                # Metadata and thinking-only fragments carry no answer text.
                yield ChatStreamChunk(_raw_chat_content(chunk) or "", cls._finish_reason(chunk))
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    def complete(self, messages, *, model=None, options=None, stream=False, keep_alive_seconds=None, thinking=None):
        kwargs = {"model": model, "messages": messages}
        kwargs.update(self._thinking_kwargs(thinking))
        if options:
            kwargs["options"] = dict(options)
        if stream:
            kwargs["stream"] = True
        if keep_alive_seconds is not None:
            kwargs["keep_alive"] = keep_alive_seconds
        response = self._client.chat(**kwargs)
        if stream and not isinstance(response, Mapping) and hasattr(response, "__iter__"):
            return self._stream(response)
        return ChatCompletion(normalize_chat_completion(response).content, self._finish_reason(response))

    def complete_structured(self, messages, *, schema, model=None, options=None, keep_alive_seconds=None, thinking=None):
        # Ollama's opaque non-streaming call can hold the CLI inside one socket
        # read until the entire schema result is complete.  Consume its
        # streaming transport here instead so Ctrl+C can close the response.
        # Core still receives one complete JSON text result and independently
        # validates it; transport fragments never become candidate data.
        kwargs = {
            "model": model,
            "messages": messages,
            "format": dict(schema),
            "stream": True,
        }
        kwargs.update(self._thinking_kwargs(thinking))
        if options:
            kwargs["options"] = dict(options)
        if keep_alive_seconds is not None:
            kwargs["keep_alive"] = keep_alive_seconds
        response = self._client.chat(**kwargs)
        if isinstance(response, Mapping) or not hasattr(response, "__iter__"):
            reason = self._finish_reason(response)
            if reason == "length":
                raise ChatProviderOutputLimitError()
            return ChatCompletion(normalize_chat_completion(response).content, reason)
        parts: list[str] = []
        reason = None
        try:
            for chunk in response:
                reason = self._finish_reason(chunk) or reason
                try:
                    content = normalize_chat_stream_chunk(chunk).content
                except ChatProviderResponseError:
                    # Ollama may finish with a metadata-only chunk.
                    content = ""
                if content:
                    parts.append(content)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        if reason == "length":
            raise ChatProviderOutputLimitError()
        return ChatCompletion("".join(parts), reason)

    def list_models(self):
        return self._client.list()

    def probe_health(self):
        """Use Ollama's supported model-list call as a non-generating probe."""
        return self.list_models()


class DisabledChatProvider:
    """Explicit non-generating adapter for zero-provider resident mode."""

    name = "disabled"
    configured = False

    def __init__(self, reason: str = "Chat generation is disabled by configuration.") -> None:
        self._reason = str(reason)[:300]

    def complete(self, messages, *, model=None, options=None, stream=False, keep_alive_seconds=None):
        raise RuntimeError(self._reason)

    def list_models(self):
        raise RuntimeError(self._reason)

    def probe_health(self):
        raise RuntimeError(self._reason)


class CallableChatProvider:
    """Compatibility adapter for the existing injected chat callable surface."""

    name = "custom chat client"

    def __init__(self, chat: Callable[..., Any], *, model_lister: Callable[[], Any] | None = None):
        self._chat = chat
        self._model_lister = model_lister

    def complete(self, messages, *, model=None, options=None, stream=False, keep_alive_seconds=None):
        kwargs = {"model": model, "messages": messages}
        if options:
            kwargs["options"] = dict(options)
        if stream:
            kwargs["stream"] = True
        if keep_alive_seconds is not None:
            kwargs["keep_alive"] = keep_alive_seconds
        return self._chat(**kwargs)

    def list_models(self):
        if self._model_lister is None:
            raise RuntimeError("Model listing is unavailable for this chat provider.")
        return self._model_lister()

    def probe_health(self):
        """Compatibility providers can probe only when they expose listing."""
        if self._model_lister is None:
            raise NotImplementedError("Health probing is unavailable for this chat provider.")
        return self._model_lister()


__all__ = [
    "CallableChatProvider", "CHAT_FINISH_REASONS", "ChatCompletion", "ChatCompletionProvider", "ChatMessages", "ChatProvider",
    "ChatProviderResponseError", "ChatProviderOutputLimitError", "ChatStreamChunk", "DisabledChatProvider",
    "OllamaChatProvider", "StructuredChatCompletionProvider", "normalize_chat_completion", "normalize_chat_stream_chunk",
    "normalize_structured_chat_completion",
    "provider_health_snapshot", "provider_is_configured",
]
