"""Explicit routed chat execution over Core-injected provider adapters.

This module joins a pure route plan to one already-registered chat provider. It
does not inspect prompts, construct providers, probe health, retry, fall back
after a request failure, persist telemetry, or mutate session/adventure state.
Those policies stay with a later Core integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pipeline.provider_registry import ChatProviderRegistry
from pipeline.task_routing import TaskRouteDecision, TaskRoutePlanner


class RoutedTaskExecutionError(RuntimeError):
    """Raised when a route cannot safely become one provider request."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class RoutedChatExecution:
    """One bounded audit handle for an explicit completed provider request."""

    decision: TaskRouteDecision
    response: Any

    @property
    def provider_id(self) -> str:
        selected = self.decision.selected
        if selected is None:  # Defensive: construction is private to executor.
            raise RuntimeError("routed execution has no selected provider")
        return selected.provider_id

    @property
    def task_id(self) -> str:
        selected = self.decision.selected
        if selected is None:
            raise RuntimeError("routed execution has no selected task")
        return selected.task_id

    def public_dict(self) -> dict[str, object]:
        """Return bounded execution metadata without exposing the response."""
        selected = self.decision.selected
        if selected is None:
            raise RuntimeError("routed execution has no selected provider")
        return {
            "requested_task_id": self.decision.requested_task_id,
            "selected_task_id": selected.task_id,
            "provider": selected.provider_id,
            "model": selected.profile.model,
            "fallback_used": self.decision.selected_index not in (None, 0),
            "outcome": "submitted",
        }


class RoutedChatExecutor:
    """Execute exactly one route-selected chat request, with no hidden retry."""

    def __init__(self, planner: TaskRoutePlanner, providers: ChatProviderRegistry) -> None:
        if not isinstance(planner, TaskRoutePlanner):
            raise TypeError("routed chat planner is invalid")
        if not isinstance(providers, ChatProviderRegistry):
            raise TypeError("routed chat provider registry is invalid")
        self._planner = planner
        self._providers = providers

    def execute(
        self, task_id: object, messages, *, default_model: str,
        default_provider_id: str, base_options: Mapping[str, int | float] | None = None,
        stream: bool = False,
    ) -> RoutedChatExecution:
        """Plan and submit one request to one registered chat provider.

        A selected fallback task is chosen only from the declarative plan before
        a request begins. If the chosen provider raises, that failure is
        reported to Core; this boundary never silently invokes another model.
        """
        decision = self.plan(
            task_id,
            default_model=default_model,
            default_provider_id=default_provider_id,
            base_options=base_options,
        )
        return self.execute_planned(decision, messages, stream=stream)

    def plan(
        self, task_id: object, *, default_model: str,
        default_provider_id: str, base_options: Mapping[str, int | float] | None = None,
    ) -> TaskRouteDecision:
        """Return a pure route decision before any lifecycle or provider call."""
        return self._planner.plan(
            task_id,
            default_model=default_model,
            default_provider_id=default_provider_id,
            base_options=base_options,
        )

    def execute_planned(self, decision: TaskRouteDecision, messages, *, stream: bool = False) -> RoutedChatExecution:
        """Submit one already-planned route without replanning or fallback."""
        if not isinstance(decision, TaskRouteDecision):
            raise TypeError("routed chat decision is invalid")
        selected = decision.selected
        if selected is None:
            raise RoutedTaskExecutionError("no configured provider route is available", reason="route_unavailable")
        provider = self._providers.get(selected.provider_id)
        if provider is None:
            raise RoutedTaskExecutionError(
                "selected provider adapter is unavailable", reason="provider_adapter_unavailable",
            )
        try:
            response = provider.complete(
                messages,
                model=selected.profile.model,
                options=dict(selected.profile.options) or None,
                stream=stream,
            )
        except Exception as error:
            raise RoutedTaskExecutionError("routed provider request failed", reason="provider_request_failed") from error
        return RoutedChatExecution(decision, response)


__all__ = ["RoutedChatExecution", "RoutedChatExecutor", "RoutedTaskExecutionError"]
