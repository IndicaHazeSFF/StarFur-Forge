"""Core-owned, noncanonical orchestration for one generated adventure turn.

The coordinator has one job: capture a safe mounted-workspace projection,
submit it to an explicitly injected candidate provider, and return validated
ordinary-event candidates tied to that captured origin.  It never stages or
commits an adventure event.  The session inbox performs the later stale-origin
check before a user may select a candidate.
"""

from __future__ import annotations

from pipeline.adventure_session import AdventureSessionState
from pipeline.adventure_participant import render_declared_participant_prompt_context
from pipeline.adventure_turn_context import AdventureTurnContextView
from pipeline.adventure_turn_generation import AdventureTurnGenerationRequest, AdventureTurnGenerationResult
from pipeline.adventure_turn_provider import (
    AdventureTurnCandidateProvider,
    AdventureTurnProviderError,
    validate_adventure_turn_provider_result,
)


class AdventureTurnCoordinatorError(RuntimeError):
    """Raised when an untrusted generated-turn proposal cannot be prepared."""

    def __init__(self, *, reason: str) -> None:
        super().__init__("adventure-turn candidate generation failed safely")
        self.reason = reason


class AdventureTurnCoordinator:
    """Explicit coordinator with no log, inbox, command, or provider ownership."""

    def __init__(self, provider: AdventureTurnCandidateProvider) -> None:
        if not isinstance(provider, AdventureTurnCandidateProvider):
            raise TypeError("adventure-turn coordinator provider is invalid")
        self._provider = provider

    def propose(
        self, session: AdventureSessionState, *, user_text: str, narrator_text: str = "",
        source_record_ids: tuple[str, ...] = (), task_id: str = "adventure_turn_generation",
        provider_name: str = "unconfigured", model_name: str | None = None,
    ) -> AdventureTurnGenerationResult:
        """Return validated candidates for a captured context, without any write.

        A caller must subsequently compare this result with its *current*
        mounted session before presentation.  That separate comparison makes a
        response stale if an authoritative event changed while the provider was
        running.
        """
        try:
            context = AdventureTurnContextView.from_session(session)
            roster = session.participant_roster
            participant_context = (
                render_declared_participant_prompt_context(roster)
                if roster is not None and roster.participants else ""
            )
            request = AdventureTurnGenerationRequest.from_context_view(
                context, user_text=user_text, narrator_text=narrator_text,
                participant_context=participant_context,
                source_record_ids=source_record_ids,
                task_id=task_id, provider_name=provider_name, model_name=model_name,
            )
            decoded = self._provider.propose(request)
            batch = validate_adventure_turn_provider_result(decoded)
        except AdventureTurnProviderError as error:
            raise AdventureTurnCoordinatorError(reason=error.reason) from error
        except (TypeError, ValueError) as error:
            raise AdventureTurnCoordinatorError(reason="context_invalid") from error
        return AdventureTurnGenerationResult(request, batch)


__all__ = ["AdventureTurnCoordinator", "AdventureTurnCoordinatorError"]
