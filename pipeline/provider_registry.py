"""Explicit in-process provider adapter registries with no configuration loader.

Registries are dependency-injection boundaries. They store already-constructed
provider adapters supplied by Core, never instantiate one from configuration,
perform health probes, or execute a request. Non-chat provider families remain
separate future registries rather than pretending to satisfy ``ChatProvider``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from pipeline.providers import ChatCompletionProvider
from pipeline.task_routing import normalize_provider_id


@dataclass(frozen=True)
class ChatProviderRegistration:
    """One stable Core-owned ID paired with an injected chat adapter."""

    provider_id: str
    provider: ChatCompletionProvider

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", normalize_provider_id(self.provider_id))
        # The executor needs only ``complete``.  Health probing and model
        # listing are separate, optional provider-owned boundaries, so requiring
        # the full runtime protocol here would reject otherwise valid injected
        # adapters (including legacy test/embedding adapters) before routing
        # can make its non-probing decision.
        if not callable(getattr(self.provider, "complete", None)):
            raise TypeError("registered chat provider must provide complete")


@dataclass(frozen=True)
class ChatProviderRegistry:
    """Immutable lookup for injected chat adapters only."""

    registrations: Mapping[str, ChatProviderRegistration] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized: dict[str, ChatProviderRegistration] = {}
        for key, registration in dict(self.registrations).items():
            provider_id = normalize_provider_id(key)
            if not isinstance(registration, ChatProviderRegistration):
                raise TypeError("chat provider registry entries are invalid")
            if registration.provider_id != provider_id:
                raise ValueError("chat provider registry key must match registration")
            normalized[provider_id] = registration
        object.__setattr__(self, "registrations", normalized)

    def get(self, provider_id: object) -> ChatCompletionProvider | None:
        registration = self.registrations.get(normalize_provider_id(provider_id))
        return None if registration is None else registration.provider

    def provider_ids(self) -> tuple[str, ...]:
        """Return stable registered IDs without exposing adapter internals."""
        return tuple(sorted(self.registrations))

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.registrations))


__all__ = ["ChatProviderRegistration", "ChatProviderRegistry"]
