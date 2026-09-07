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


class ChatProviderResponseError(ValueError):
    """Raised when an adapter result has no usable text completion."""


@dataclass(frozen=True)
class ChatCompletion:
    """Provider-neutral, text-only result handed to Core consumers.

    This deliberately retains no provider payload, token accounting, tool-call
    shape, or transport metadata.  Task-specific layers remain responsible for
    their own size limits and structured-output validation.
    """

    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("chat completion content must be text")


@dataclass(frozen=True)
class ChatStreamChunk:
    """One provider-neutral text fragment from an optional streamed result."""

    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("chat stream chunk content must be text")


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
    return ChatCompletion(content)


def normalize_chat_stream_chunk(value: object) -> ChatStreamChunk:
    """Normalize one optional streaming fragment into the Core text contract."""
    content = _raw_chat_content(value)
    if content is None:
        raise ChatProviderResponseError("chat provider stream chunk has no text content")
    return ChatStreamChunk(content)


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
    ) -> Any:
        """Return a provider response or a provider streaming iterator."""


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

    def __init__(self, client: Any):
        self._client = client

    def complete(self, messages, *, model=None, options=None, stream=False):
        kwargs = {"model": model, "messages": messages}
        if options:
            kwargs["options"] = dict(options)
        if stream:
            kwargs["stream"] = True
        return self._client.chat(**kwargs)

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

    def complete(self, messages, *, model=None, options=None, stream=False):
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

    def complete(self, messages, *, model=None, options=None, stream=False):
        kwargs = {"model": model, "messages": messages}
        if options:
            kwargs["options"] = dict(options)
        if stream:
            kwargs["stream"] = True
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
    "CallableChatProvider", "ChatCompletion", "ChatCompletionProvider", "ChatMessages", "ChatProvider",
    "ChatProviderResponseError", "ChatStreamChunk", "DisabledChatProvider",
    "OllamaChatProvider", "normalize_chat_completion", "normalize_chat_stream_chunk",
    "provider_health_snapshot", "provider_is_configured",
]
