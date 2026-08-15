"""Small, explicit provider interfaces for StarFur runtime capabilities.

Only chat is implemented here.  The boundary keeps provider-specific API calls
out of assistant orchestration while retaining a callable adapter for legacy
tests and integrations.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Protocol, runtime_checkable


ChatMessages = Iterable[Mapping[str, str]]


@runtime_checkable
class ChatProvider(Protocol):
    """A local or remote text-generation provider."""

    name: str

    def complete(
        self,
        messages: ChatMessages,
        *,
        model: str | None = None,
        options: Mapping[str, Any] | None = None,
        stream: bool = False,
    ) -> Any:
        """Return a provider response or a provider streaming iterator."""

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
