"""Noncanonical coordinator for one governed participant-action proposal.

This coordinator has no AssistantSession, command, inbox, event-log, or
provider-routing ownership.  It captures a bounded participant view from an
already mounted adventure, enforces declared policy before and after untrusted
output parsing, and returns a review-only result.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol, runtime_checkable

from pipeline.adventure_participant import AdventureParticipantView
from pipeline.adventure_participant_action import (
    AdventureParticipantActionCandidateBatch,
    AdventureParticipantActionCandidateError,
    GovernedParticipantActionBatch,
    bind_participant_action_candidates,
    parse_untrusted_participant_action_candidates,
)
from pipeline.adventure_participant_action_generation import (
    AdventureParticipantActionGenerationError,
    AdventureParticipantActionGenerationRequest,
    AdventureParticipantActionInputError,
)
from pipeline.adventure_session import AdventureSessionState
from pipeline.providers import ChatProviderOutputLimitError, normalize_structured_chat_completion


class AdventureParticipantActionCoordinatorError(RuntimeError):
    """Raised when participant-action generation fails before review."""

    def __init__(self, *, reason: str) -> None:
        super().__init__("participant action proposal failed safely")
        self.reason = reason


@runtime_checkable
class AdventureParticipantActionCandidateProvider(Protocol):
    """Minimal injected seam returning decoded, untrusted candidate data."""

    def propose(self, request: AdventureParticipantActionGenerationRequest) -> object:
        """Return a decoded untrusted action-candidate envelope."""


class CallableAdventureParticipantActionCandidateProvider:
    """Adapt one Core-owned completion callback to decoded action proposals."""

    def __init__(self, complete) -> None:
        if not callable(complete):
            raise TypeError("participant action completion callback must be callable")
        self._complete = complete

    def propose(self, request: AdventureParticipantActionGenerationRequest) -> object:
        if not isinstance(request, AdventureParticipantActionGenerationRequest):
            raise TypeError("participant action generation request is invalid")
        try:
            response = self._complete(request.messages())
            content = response if isinstance(response, str) else normalize_structured_chat_completion(response).content
            return json.loads(content)
        except ChatProviderOutputLimitError as error:
            raise AdventureParticipantActionCoordinatorError(reason="provider_output_limit") from error
        except AdventureParticipantActionInputError as error:
            raise AdventureParticipantActionCoordinatorError(reason="input_invalid") from error
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise AdventureParticipantActionCoordinatorError(reason="response_not_json") from error
        except AdventureParticipantActionCoordinatorError:
            raise
        except Exception as error:
            raise AdventureParticipantActionCoordinatorError(reason="provider_request_failed") from error


@dataclass(frozen=True)
class AdventureParticipantActionProposal:
    """A policy-bound, review-only participant-action proposal result."""

    request: AdventureParticipantActionGenerationRequest
    governed: GovernedParticipantActionBatch

    def __post_init__(self) -> None:
        if not isinstance(self.request, AdventureParticipantActionGenerationRequest):
            raise TypeError("participant action proposal request is invalid")
        if not isinstance(self.governed, GovernedParticipantActionBatch):
            raise TypeError("participant action proposal batch is invalid")
        if self.request.participant_view.participant != self.governed.participant:
            raise AdventureParticipantActionCoordinatorError(reason="participant_binding_mismatch")

    @property
    def batch(self) -> AdventureParticipantActionCandidateBatch:
        return self.governed.candidates


class AdventureParticipantActionCoordinator:
    """Build and parse one policy-bound action proposal without side effects."""

    def __init__(self, provider: AdventureParticipantActionCandidateProvider) -> None:
        if not isinstance(provider, AdventureParticipantActionCandidateProvider):
            raise TypeError("participant action coordinator provider is invalid")
        self._provider = provider

    def propose(
        self, session: AdventureSessionState, *, participant_id: object, trigger: str,
        user_text: str, turns_since_last_action: int | None, actions_this_turn: int,
    ) -> AdventureParticipantActionProposal:
        """Return a policy-bound review proposal, never a performed action."""
        if not isinstance(session, AdventureSessionState) or not session.active:
            raise AdventureParticipantActionCoordinatorError(reason="adventure_unmounted")
        roster = session.participant_roster
        if roster is None:
            raise AdventureParticipantActionCoordinatorError(reason="participant_roster_missing")
        try:
            participant = roster.resolve(participant_id)
            view = AdventureParticipantView.from_session(session, participant)
            request = AdventureParticipantActionGenerationRequest.from_view(
                view,
                trigger=trigger,
                user_text=user_text,
                turns_since_last_action=turns_since_last_action,
                actions_this_turn=actions_this_turn,
            )
            request.messages()  # Validate source framing/bytes before any injected provider seam.
            parsed = parse_untrusted_participant_action_candidates(self._provider.propose(request))
            governed = bind_participant_action_candidates(
                parsed,
                roster,
                participant_id=participant.participant_id,
                trigger=trigger,
                turns_since_last_action=turns_since_last_action,
                actions_this_turn=actions_this_turn,
            )
        except AdventureParticipantActionCoordinatorError:
            raise
        except AdventureParticipantActionInputError as error:
            raise AdventureParticipantActionCoordinatorError(reason="input_invalid") from error
        except AdventureParticipantActionGenerationError as error:
            raise AdventureParticipantActionCoordinatorError(reason="policy_ineligible") from error
        except AdventureParticipantActionCandidateError as error:
            raise AdventureParticipantActionCoordinatorError(reason="candidate_envelope_invalid") from error
        except Exception as error:
            raise AdventureParticipantActionCoordinatorError(reason="provider_request_failed") from error
        return AdventureParticipantActionProposal(request, governed)


__all__ = [
    "AdventureParticipantActionCandidateProvider", "AdventureParticipantActionCoordinator",
    "AdventureParticipantActionCoordinatorError", "AdventureParticipantActionProposal",
    "CallableAdventureParticipantActionCandidateProvider",
]
