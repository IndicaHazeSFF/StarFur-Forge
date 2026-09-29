"""Provider-free orchestration for one portable enum resource candidate batch."""

from __future__ import annotations

from pipeline.adventure_session import AdventureSessionState
from pipeline.adventure_turn_context import AdventureTurnContextView
from pipeline.adventure_turn_provider import AdventureTurnProviderError, AdventureTurnResourceCandidateProvider
from pipeline.adventure_turn_resource_candidates import parse_untrusted_adventure_turn_resource_candidates
from pipeline.adventure_turn_resource_generation import (
    AdventureTurnResourceGenerationRequest,
    AdventureTurnResourceGenerationResult,
)
from pipeline.adventure_turn_resource_policy import AdventureTurnResourcePolicyView


class AdventureTurnResourceCoordinatorError(RuntimeError):
    def __init__(self, *, reason: str) -> None:
        super().__init__("adventure-turn resource candidate generation failed safely")
        self.reason = reason


class AdventureTurnResourceCoordinator:
    def __init__(self, provider: AdventureTurnResourceCandidateProvider) -> None:
        if not isinstance(provider, AdventureTurnResourceCandidateProvider):
            raise TypeError("adventure-turn resource coordinator provider is invalid")
        self._provider = provider

    def propose(self, session: AdventureSessionState, *, user_text: str, narrator_text: str = "",
                source_record_ids: tuple[str, ...] = (), provider_name: str = "unconfigured",
                model_name: str | None = None) -> AdventureTurnResourceGenerationResult:
        try:
            context = AdventureTurnContextView.from_session(session)
            policy = AdventureTurnResourcePolicyView.from_session(session)
            request = AdventureTurnResourceGenerationRequest.from_context_view(
                context, policy, user_text=user_text, narrator_text=narrator_text,
                source_record_ids=source_record_ids, provider_name=provider_name, model_name=model_name,
            )
            batch = parse_untrusted_adventure_turn_resource_candidates(self._provider.propose(request), policy)
        except AdventureTurnProviderError as error:
            raise AdventureTurnResourceCoordinatorError(reason=error.reason) from error
        except (TypeError, ValueError) as error:
            raise AdventureTurnResourceCoordinatorError(reason="resource_context_invalid") from error
        return AdventureTurnResourceGenerationResult(request, batch)


__all__ = ["AdventureTurnResourceCoordinator", "AdventureTurnResourceCoordinatorError"]
