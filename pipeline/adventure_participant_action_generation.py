"""Provider-neutral request contract for one governed participant action.

The request is constructed only after a participant's bounded adventure view
and exact initiative policy have been supplied.  It does not call a provider,
retain dynamic action history, stage a candidate, or write any adventure state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from pipeline.adventure_initiative import AdventureInitiativeError, InitiativeDecision, evaluate_initiative
from pipeline.adventure_participant import AdventureParticipantView
from pipeline.adventure_participant_action import (
    AdventureParticipantActionCandidateBatch,
    MAX_PARTICIPANT_ACTION_CANDIDATES,
)


MAX_PARTICIPANT_ACTION_INPUT_CHARACTERS = 4_000


class AdventureParticipantActionGenerationError(ValueError):
    """Raised when a governed participant action request cannot be prepared."""


def _new_generation_id() -> str:
    return f"TPG-{uuid4().hex}"


def _normalize_generation_id(value: object) -> str:
    if not isinstance(value, str) or len(value) != 36 or not value.startswith("TPG-"):
        raise AdventureParticipantActionGenerationError("participant action generation identifier is invalid")
    suffix = value[4:]
    if any(character not in "0123456789abcdef" for character in suffix):
        raise AdventureParticipantActionGenerationError("participant action generation identifier is invalid")
    return value


def _bounded_text(value: object) -> str:
    if not isinstance(value, str):
        raise AdventureParticipantActionGenerationError("participant action input is invalid")
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_PARTICIPANT_ACTION_INPUT_CHARACTERS:
        raise AdventureParticipantActionGenerationError("participant action input is invalid")
    return normalized


@dataclass(frozen=True)
class AdventureParticipantActionGenerationRequest:
    """One policy-eligible, bounded, provider-untrusted action proposal request."""

    participant_view: AdventureParticipantView
    trigger: str
    decision: InitiativeDecision
    user_text: str
    generation_id: str = field(default_factory=_new_generation_id)

    def __post_init__(self) -> None:
        if not isinstance(self.participant_view, AdventureParticipantView):
            raise TypeError("participant action generation view is invalid")
        if not isinstance(self.trigger, str) or not self.trigger:
            raise AdventureParticipantActionGenerationError("participant action trigger is invalid")
        if not isinstance(self.decision, InitiativeDecision) or not self.decision.allowed:
            raise AdventureParticipantActionGenerationError("participant action is not eligible for generation")
        object.__setattr__(self, "user_text", _bounded_text(self.user_text))
        object.__setattr__(self, "generation_id", _normalize_generation_id(self.generation_id))

    @classmethod
    def from_view(
        cls, view: AdventureParticipantView, *, trigger: str, user_text: str,
        turns_since_last_action: int | None, actions_this_turn: int,
        generation_id: str | None = None,
    ) -> "AdventureParticipantActionGenerationRequest":
        """Evaluate the declared policy before rendering any provider input."""
        if not isinstance(view, AdventureParticipantView):
            raise TypeError("participant action generation view is invalid")
        try:
            decision = evaluate_initiative(
                view.participant.initiative_policy,
                trigger=trigger,
                turns_since_last_action=turns_since_last_action,
                actions_this_turn=actions_this_turn,
            )
        except AdventureInitiativeError as error:
            raise AdventureParticipantActionGenerationError("participant action eligibility is invalid") from error
        values: dict[str, object] = {
            "participant_view": view,
            "trigger": trigger,
            "decision": decision,
            "user_text": user_text,
        }
        if generation_id is not None:
            values["generation_id"] = generation_id
        return cls(**values)

    def messages(self) -> tuple[dict[str, str], dict[str, str]]:
        """Render one safe participant-view input and a closed candidate schema."""
        allowed_actions = ", ".join(self.participant_view.participant.initiative_policy.allowed_actions)
        system = (
            "You may propose at most one bounded possible adventure-participant action. "
            "Return JSON only, exactly as "
            '{"schema_version":1,"candidates":[{"participant_id":"...","action":"...",'
            '"summary":"...","confidence":0.0}]}. '
            f"Return at most {MAX_PARTICIPANT_ACTION_CANDIDATES} candidates, all for participant "
            f"{self.participant_view.participant.participant_id!r}. Allowed action kinds: {allowed_actions}. "
            "If no action is appropriate, return exactly {\"schema_version\":1,\"candidates\":[]}. "
            "Do not write narrative, an event, state, memory, transcript, command, permission, "
            "or hidden reasoning. Output is untrusted and cannot perform an action."
        )
        source = "\n\n".join((
            self.participant_view.render(),
            f"TRIGGER (Core-supplied policy label): {self.trigger}",
            "USER TURN TEXT (untrusted source):\n" + self.user_text,
        ))
        return ({"role": "system", "content": system}, {"role": "user", "content": source})


@dataclass(frozen=True)
class AdventureParticipantActionGenerationResult:
    """Trusted Core wrapper joining one request to already-parsed candidates."""

    request: AdventureParticipantActionGenerationRequest
    batch: AdventureParticipantActionCandidateBatch

    def __post_init__(self) -> None:
        if not isinstance(self.request, AdventureParticipantActionGenerationRequest):
            raise TypeError("participant action generation request is invalid")
        if not isinstance(self.batch, AdventureParticipantActionCandidateBatch):
            raise TypeError("participant action generation batch is invalid")


__all__ = [
    "AdventureParticipantActionGenerationError", "AdventureParticipantActionGenerationRequest",
    "AdventureParticipantActionGenerationResult", "MAX_PARTICIPANT_ACTION_INPUT_CHARACTERS",
]
