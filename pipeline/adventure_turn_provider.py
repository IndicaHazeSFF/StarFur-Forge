"""Injectable, task-specific provider adapter for generated adventure candidates.

This boundary is intentionally dormant until an explicit future orchestration
path calls it.  It invokes no provider at construction time and has no access
to sessions, adventure logs, prompts beyond its supplied request, or writes.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from pipeline.adventure_turn_candidates import (
    AdventureTurnCandidateBatch,
    AdventureTurnCandidateError,
    parse_untrusted_adventure_turn_candidates,
)
from pipeline.adventure_turn_generation import AdventureTurnGenerationRequest
from pipeline.adventure_turn_mutation_candidates import (
    AdventureTurnMutationCandidateBatch,
    AdventureTurnMutationCandidateError,
    parse_untrusted_adventure_turn_mutation_candidates,
)
from pipeline.adventure_turn_mutation_generation import AdventureTurnMutationGenerationRequest
from pipeline.providers import ChatProvider


MAX_ADVENTURE_TURN_PROVIDER_RESPONSE_CHARACTERS = 16_000


class AdventureTurnProviderError(RuntimeError):
    """Raised when a provider response cannot become validated candidates."""

    def __init__(self, message: str, *, reason: str = "provider_error") -> None:
        super().__init__(message)
        self.reason = reason


@runtime_checkable
class AdventureTurnCandidateProvider(Protocol):
    """Task-specific provider interface returning decoded untrusted data."""

    def propose(self, request: AdventureTurnGenerationRequest) -> object:
        """Return one decoded, untrusted candidate envelope."""


@runtime_checkable
class AdventureTurnMutationCandidateProvider(Protocol):
    """Task-specific provider interface for decoded typed mutation proposals."""

    def propose(self, request: AdventureTurnMutationGenerationRequest) -> object:
        """Return one decoded, untrusted typed mutation candidate envelope."""


class CallableAdventureTurnCandidateProvider:
    """Adapt one Core-owned completion callback to the candidate protocol.

    The callback owns task-profile selection, lifecycle accounting, and any
    future routing.  This adapter only performs bounded response extraction and
    JSON decoding; it does not know an assistant session or event log.
    """

    def __init__(self, complete: Callable[[tuple[dict[str, str], dict[str, str]]], object]) -> None:
        if not callable(complete):
            raise TypeError("adventure-turn completion callback must be callable")
        self._complete = complete

    def propose(self, request: AdventureTurnGenerationRequest) -> object:
        if not isinstance(request, AdventureTurnGenerationRequest):
            raise TypeError("adventure-turn request is invalid")
        try:
            response = self._complete(request.messages())
            content = _response_content(response)
            return _parse_json_content(content)
        except AdventureTurnProviderError:
            raise
        except (TypeError, json.JSONDecodeError) as error:
            raise AdventureTurnProviderError(
                "adventure-turn provider response was not strict JSON", reason="response_not_json",
            ) from error
        except Exception as error:
            raise AdventureTurnProviderError("adventure-turn provider request failed", reason="provider_request_failed") from error


class CallableAdventureTurnMutationCandidateProvider:
    """Adapt a Core completion callback to the typed-mutation proposal protocol."""

    def __init__(self, complete: Callable[[tuple[dict[str, str], dict[str, str]]], object]) -> None:
        if not callable(complete):
            raise TypeError("adventure-turn mutation completion callback must be callable")
        self._complete = complete

    def propose(self, request: AdventureTurnMutationGenerationRequest) -> object:
        if not isinstance(request, AdventureTurnMutationGenerationRequest):
            raise TypeError("adventure-turn mutation request is invalid")
        try:
            response = self._complete(request.messages())
            return _parse_json_content(_response_content(response))
        except AdventureTurnProviderError:
            raise
        except (TypeError, json.JSONDecodeError) as error:
            raise AdventureTurnProviderError(
                "adventure-turn mutation provider response was not strict JSON", reason="response_not_json",
            ) from error
        except Exception as error:
            raise AdventureTurnProviderError(
                "adventure-turn mutation provider request failed", reason="provider_request_failed",
            ) from error


def validate_adventure_turn_provider_result(value: object) -> AdventureTurnCandidateBatch:
    """Turn decoded provider data into bounded candidates without side effects."""
    try:
        return parse_untrusted_adventure_turn_candidates(value)
    except (AdventureTurnCandidateError, TypeError, ValueError) as error:
        raise AdventureTurnProviderError(
            "adventure-turn provider returned an invalid candidate envelope", reason="candidate_envelope_invalid",
        ) from error


def validate_adventure_turn_mutation_provider_result(value: object) -> AdventureTurnMutationCandidateBatch:
    """Turn decoded data into typed proposals without staging or side effects."""
    try:
        return parse_untrusted_adventure_turn_mutation_candidates(value)
    except (AdventureTurnMutationCandidateError, TypeError, ValueError) as error:
        raise AdventureTurnProviderError(
            "adventure-turn mutation provider returned an invalid candidate envelope",
            reason="mutation_candidate_envelope_invalid",
        ) from error


class ChatAdventureTurnCandidateProvider:
    """Explicit adapter from the generic chat boundary to candidate proposals."""

    def __init__(
        self, provider: ChatProvider, *, model: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(provider, ChatProvider):
            raise TypeError("adventure-turn provider must satisfy ChatProvider")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise ValueError("adventure-turn model is invalid")
        if options is not None and not isinstance(options, Mapping):
            raise TypeError("adventure-turn generation options must be a mapping or None")
        self._provider = provider
        self._model = model.strip() if isinstance(model, str) else None
        self._options = dict(options) if options else None

    def propose(self, request: AdventureTurnGenerationRequest) -> object:
        if not isinstance(request, AdventureTurnGenerationRequest):
            raise TypeError("adventure-turn request is invalid")
        try:
            response = self._provider.complete(
                request.messages(), model=self._model, options=self._options, stream=False,
            )
        except Exception as error:
            raise AdventureTurnProviderError("adventure-turn provider request failed", reason="provider_request_failed") from error
        content = _response_content(response)
        try:
            return _parse_json_content(content)
        except (TypeError, json.JSONDecodeError) as error:
            raise AdventureTurnProviderError(
                "adventure-turn provider response was not strict JSON", reason="response_not_json",
            ) from error


class ChatAdventureTurnMutationCandidateProvider:
    """Explicit generic-chat adapter for the separate typed-mutation task."""

    def __init__(
        self, provider: ChatProvider, *, model: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(provider, ChatProvider):
            raise TypeError("adventure-turn mutation provider must satisfy ChatProvider")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise ValueError("adventure-turn mutation model is invalid")
        if options is not None and not isinstance(options, Mapping):
            raise TypeError("adventure-turn mutation generation options must be a mapping or None")
        self._provider = provider
        self._model = model.strip() if isinstance(model, str) else None
        self._options = dict(options) if options else None

    def propose(self, request: AdventureTurnMutationGenerationRequest) -> object:
        if not isinstance(request, AdventureTurnMutationGenerationRequest):
            raise TypeError("adventure-turn mutation request is invalid")
        try:
            response = self._provider.complete(
                request.messages(), model=self._model, options=self._options, stream=False,
            )
        except Exception as error:
            raise AdventureTurnProviderError(
                "adventure-turn mutation provider request failed", reason="provider_request_failed",
            ) from error
        try:
            return _parse_json_content(_response_content(response))
        except (TypeError, json.JSONDecodeError) as error:
            raise AdventureTurnProviderError(
                "adventure-turn mutation provider response was not strict JSON", reason="response_not_json",
            ) from error


def _response_content(response: object) -> str:
    if isinstance(response, Mapping):
        message = response.get("message")
        content = message.get("content") if isinstance(message, Mapping) else response.get("content")
    else:
        message = getattr(response, "message", None)
        content = getattr(message, "content", None)
    if not isinstance(content, str):
        raise AdventureTurnProviderError("adventure-turn provider response has no text content", reason="response_missing_content")
    if not content.strip():
        raise AdventureTurnProviderError("adventure-turn provider response is empty", reason="response_empty")
    if len(content) > MAX_ADVENTURE_TURN_PROVIDER_RESPONSE_CHARACTERS:
        raise AdventureTurnProviderError("adventure-turn provider response is too large", reason="response_too_large")
    return content


def _parse_json_content(content: str) -> object:
    """Parse only a direct JSON document, never a wrapper or prose fragment.

    Candidate output is an authority-sensitive boundary. Fences, preambles,
    suffixes, and multiple documents are rejected instead of being heuristically
    recovered, so provider formatting failures remain visible and retry-safe.
    """
    text = content.strip()
    if not text:
        raise json.JSONDecodeError("empty provider response", text, 0)
    return json.loads(text)


__all__ = [
    "AdventureTurnCandidateProvider", "AdventureTurnMutationCandidateProvider", "AdventureTurnProviderError",
    "CallableAdventureTurnCandidateProvider", "CallableAdventureTurnMutationCandidateProvider",
    "ChatAdventureTurnCandidateProvider", "ChatAdventureTurnMutationCandidateProvider",
    "MAX_ADVENTURE_TURN_PROVIDER_RESPONSE_CHARACTERS",
    "validate_adventure_turn_provider_result", "validate_adventure_turn_mutation_provider_result",
]
