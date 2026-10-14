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
from pipeline.providers import (
    ChatProviderOutputLimitError, StructuredChatCompletionProvider,
    normalize_structured_chat_completion,
)
from pipeline.task_routing import TaskRouteDecision, TaskRoutePlanner
from pipeline.provider_workload_gate import ProviderWorkloadGate


class RoutedTaskExecutionError(RuntimeError):
    """Raised when a route cannot safely become one provider request."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class _LeaseBoundResponseIterator:
    """Retain one workload lease until a streamed response ends or closes."""

    def __init__(self, response, release) -> None:
        self._response = response
        self._iterator = iter(response)
        self._release_callback = release
        self._released = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._iterator)
        except BaseException:
            self._release()
            raise

    def close(self) -> None:
        try:
            close = getattr(self._response, "close", None)
            if callable(close):
                close()
        finally:
            self._release()

    def _release(self) -> None:
        if self._released:
            return
        self._released = True
        callback = self._release_callback
        self._release_callback = None
        callback()


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
        result = {
            "requested_task_id": self.decision.requested_task_id,
            "selected_task_id": selected.task_id,
            "provider": selected.provider_id,
            "model": selected.profile.model,
            "fallback_used": self.decision.selected_index not in (None, 0),
            "outcome": "submitted",
        }
        if selected.profile.resource_profile is not None:
            result["resource_profile"] = selected.profile.resource_profile
        if selected.profile.model_keep_alive_seconds is not None:
            result["model_keep_alive_seconds"] = selected.profile.model_keep_alive_seconds
        return result


class RoutedChatExecutor:
    """Execute exactly one route-selected chat request, with no hidden retry."""

    def __init__(
        self, planner: TaskRoutePlanner, providers: ChatProviderRegistry,
        *, workload_gate: ProviderWorkloadGate | None = None,
    ) -> None:
        if not isinstance(planner, TaskRoutePlanner):
            raise TypeError("routed chat planner is invalid")
        if not isinstance(providers, ChatProviderRegistry):
            raise TypeError("routed chat provider registry is invalid")
        if workload_gate is not None and not isinstance(workload_gate, ProviderWorkloadGate):
            raise TypeError("routed chat workload gate is invalid")
        self._planner = planner
        self._providers = providers
        self._workload_gate = workload_gate

    @staticmethod
    def _thinking_kwargs(provider, profile):
        if profile.model_thinking is None:
            return {}
        if getattr(provider, "supports_model_thinking", False) is not True:
            raise RoutedTaskExecutionError(
                "selected provider does not support thinking control",
                reason="provider_thinking_control_unavailable",
            )
        return {"thinking": profile.model_thinking}

    def _acquire_workload_lease(self, decision: TaskRouteDecision):
        """Claim one optional process-local capacity lease before provider use."""
        selected = decision.selected
        if selected is None or self._workload_gate is None:
            return None
        admission = self._workload_gate.try_acquire(
            selected.provider_id, selected.profile.max_concurrent_requests or 1,
        )
        if not admission.lease:
            raise RoutedTaskExecutionError(
                "selected provider capacity is currently busy", reason="provider_concurrency_busy",
            )
        return admission.lease

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
        if (
            selected.profile.model_keep_alive_seconds is not None
            and getattr(provider, "supports_model_keep_alive_seconds", False) is not True
        ):
            raise RoutedTaskExecutionError(
                "selected provider does not support model residency control",
                reason="provider_residency_control_unavailable",
            )
        thinking_kwargs = self._thinking_kwargs(provider, selected.profile)
        lease = self._acquire_workload_lease(decision)
        try:
            kwargs = {
                "model": selected.profile.model,
                "options": dict(selected.profile.options) or None,
                "stream": stream,
                **thinking_kwargs,
            }
            if selected.profile.model_keep_alive_seconds is not None:
                kwargs["keep_alive_seconds"] = selected.profile.model_keep_alive_seconds
            response = provider.complete(messages, **kwargs)
            if (
                lease is not None
                and stream
                and not isinstance(response, Mapping)
                and hasattr(response, "__iter__")
            ):
                response = _LeaseBoundResponseIterator(
                    response,
                    lambda retained=lease: self._workload_gate.release(retained),
                )
                lease = None
        except Exception as error:
            raise RoutedTaskExecutionError("routed provider request failed", reason="provider_request_failed") from error
        finally:
            if lease is not None:
                self._workload_gate.release(lease)
        return RoutedChatExecution(decision, response)

    def execute_structured_planned(
        self,
        decision: TaskRouteDecision,
        messages,
        *,
        schema: Mapping[str, Any],
    ) -> RoutedChatExecution:
        """Submit one schema-constrained request without fallback or streaming."""
        if not isinstance(decision, TaskRouteDecision):
            raise TypeError("routed chat decision is invalid")
        if not isinstance(schema, Mapping) or not schema:
            raise TypeError("structured response schema is invalid")
        selected = decision.selected
        if selected is None:
            raise RoutedTaskExecutionError("no configured provider route is available", reason="route_unavailable")
        provider = self._providers.get(selected.provider_id)
        if provider is None:
            raise RoutedTaskExecutionError(
                "selected provider adapter is unavailable", reason="provider_adapter_unavailable",
            )
        if not isinstance(provider, StructuredChatCompletionProvider):
            raise RoutedTaskExecutionError(
                "selected provider does not support structured output",
                reason="provider_capability_unavailable",
            )
        if (
            selected.profile.model_keep_alive_seconds is not None
            and getattr(provider, "supports_model_keep_alive_seconds", False) is not True
        ):
            raise RoutedTaskExecutionError(
                "selected provider does not support model residency control",
                reason="provider_residency_control_unavailable",
            )
        thinking_kwargs = self._thinking_kwargs(provider, selected.profile)
        lease = self._acquire_workload_lease(decision)
        try:
            kwargs = {
                "schema": dict(schema),
                "model": selected.profile.model,
                "options": dict(selected.profile.options) or None,
                **thinking_kwargs,
            }
            if selected.profile.model_keep_alive_seconds is not None:
                kwargs["keep_alive_seconds"] = selected.profile.model_keep_alive_seconds
            response = normalize_structured_chat_completion(
                provider.complete_structured(messages, **kwargs),
            )
        except ChatProviderOutputLimitError as error:
            raise RoutedTaskExecutionError(
                "structured provider response reached its output limit",
                reason="provider_output_limit",
            ) from error
        except Exception as error:
            raise RoutedTaskExecutionError("routed provider request failed", reason="provider_request_failed") from error
        finally:
            if lease is not None:
                self._workload_gate.release(lease)
        return RoutedChatExecution(decision, response)


__all__ = ["RoutedChatExecution", "RoutedChatExecutor", "RoutedTaskExecutionError"]
