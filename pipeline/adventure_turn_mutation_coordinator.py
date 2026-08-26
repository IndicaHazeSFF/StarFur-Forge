"""Core-owned, noncanonical orchestration for generated typed mutations.

This mirrors ordinary-event orchestration but has a separate request, provider,
and parser contract.  It captures a sanitized projection and returns validated
typed candidates only; a session inbox performs the later stale-origin check,
and a separate Core policy bridge decides whether any selection is staged.
"""

from __future__ import annotations

from pipeline.adventure_session import AdventureSessionState
from pipeline.adventure_turn_context import AdventureTurnContextView
from pipeline.adventure_turn_mutation_generation import (
    AdventureTurnMutationGenerationRequest,
    AdventureTurnMutationGenerationResult,
)
from pipeline.adventure_turn_provider import (
    AdventureTurnMutationCandidateProvider,
    AdventureTurnProviderError,
    validate_adventure_turn_mutation_provider_result,
)


class AdventureTurnMutationCoordinatorError(RuntimeError):
    """Raised when untrusted typed proposals cannot be prepared safely."""

    def __init__(self, *, reason: str) -> None:
        super().__init__("adventure-turn mutation candidate generation failed safely")
        self.reason = reason


class AdventureTurnMutationCoordinator:
    """Explicit coordinator with no log, inbox, command, or provider ownership."""

    def __init__(self, provider: AdventureTurnMutationCandidateProvider) -> None:
        if not isinstance(provider, AdventureTurnMutationCandidateProvider):
            raise TypeError("adventure-turn mutation coordinator provider is invalid")
        self._provider = provider

    def propose(
        self, session: AdventureSessionState, *, user_text: str, narrator_text: str = "",
        source_record_ids: tuple[str, ...] = (), provider_name: str = "unconfigured",
        model_name: str | None = None,
    ) -> AdventureTurnMutationGenerationResult:
        """Return validated typed candidates from a captured context, without any write."""
        try:
            context = AdventureTurnContextView.from_session(session)
            request = AdventureTurnMutationGenerationRequest.from_context_view(
                context, user_text=user_text, narrator_text=narrator_text,
                source_record_ids=source_record_ids,
                provider_name=provider_name, model_name=model_name,
            )
            decoded = self._provider.propose(request)
            batch = validate_adventure_turn_mutation_provider_result(decoded)
        except AdventureTurnProviderError as error:
            raise AdventureTurnMutationCoordinatorError(reason=error.reason) from error
        except (TypeError, ValueError) as error:
            raise AdventureTurnMutationCoordinatorError(reason="context_invalid") from error
        return AdventureTurnMutationGenerationResult(request, batch)


__all__ = ["AdventureTurnMutationCoordinator", "AdventureTurnMutationCoordinatorError"]
