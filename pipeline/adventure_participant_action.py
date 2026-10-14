"""Strict, noncanonical action proposals for governed adventure participants.

This module is deliberately a contract boundary only.  It turns already
decoded provider-shaped data into bounded participant-action candidates, but
does not choose a participant, evaluate initiative, call a provider, stage an
event, write a transcript, or persist a result.  A later Core orchestration
slice must bind this contract to an exact declared roster and an eligible
initiative decision before an explicit review surface can expose it.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping

from pipeline.adventure_initiative import (
    INITIATIVE_ACTIONS,
    AdventureInitiativeError,
    AdventureParticipant,
    AdventureParticipantRoster,
    InitiativeDecision,
    evaluate_initiative,
)


PARTICIPANT_ACTION_CANDIDATE_SCHEMA_VERSION = 1
MAX_PARTICIPANT_ACTION_CANDIDATES = 4
MAX_PARTICIPANT_ACTION_SUMMARY_CHARACTERS = 600


class AdventureParticipantActionCandidateError(ValueError):
    """Raised when untrusted participant-action candidate data is invalid."""


def participant_action_candidate_json_schema() -> dict[str, object]:
    """Portable guidance schema; strict parsing remains authoritative."""
    return {
        "type": "object",
        "required": ["schema_version", "candidates"],
        "properties": {
            "schema_version": {"type": "integer"},
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["participant_id", "action", "summary", "confidence"],
                    "properties": {
                        "participant_id": {"type": "string"},
                        "action": {"type": "string"},
                        "summary": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                },
            },
        },
    }


def _bounded_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AdventureParticipantActionCandidateError(f"participant action {field} is invalid")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise AdventureParticipantActionCandidateError(f"participant action {field} is invalid")
    return normalized


@dataclass(frozen=True)
class AdventureParticipantActionCandidate:
    """One untrusted, noncanonical candidate action for a declared participant."""

    sequence: int
    candidate_id: str
    participant_id: str
    action: str
    summary: str
    confidence: float

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise AdventureParticipantActionCandidateError("participant action candidate sequence is invalid")
        if self.candidate_id != f"TP-{self.sequence:03d}":
            raise AdventureParticipantActionCandidateError("participant action candidate identifier is invalid")
        participant_id = _bounded_text(self.participant_id, field="participant identifier", maximum=96).casefold()
        action = _bounded_text(self.action, field="kind", maximum=32).casefold()
        if action not in INITIATIVE_ACTIONS:
            raise AdventureParticipantActionCandidateError("participant action kind is unsupported")
        summary = _bounded_text(self.summary, field="summary", maximum=MAX_PARTICIPANT_ACTION_SUMMARY_CHARACTERS)
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise AdventureParticipantActionCandidateError("participant action confidence is invalid")
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise AdventureParticipantActionCandidateError("participant action confidence is invalid")
        object.__setattr__(self, "participant_id", participant_id)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True)
class AdventureParticipantActionCandidateBatch:
    """A bounded untrusted action proposal batch with no write authority."""

    candidates: tuple[AdventureParticipantActionCandidate, ...]
    schema_version: int = PARTICIPANT_ACTION_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PARTICIPANT_ACTION_CANDIDATE_SCHEMA_VERSION:
            raise AdventureParticipantActionCandidateError("participant action schema is unsupported")
        if not isinstance(self.candidates, tuple) or len(self.candidates) > MAX_PARTICIPANT_ACTION_CANDIDATES:
            raise AdventureParticipantActionCandidateError("participant action candidate batch is invalid")
        if not all(isinstance(candidate, AdventureParticipantActionCandidate) for candidate in self.candidates):
            raise TypeError("participant action candidate batch is invalid")
        if [candidate.sequence for candidate in self.candidates] != list(range(1, len(self.candidates) + 1)):
            raise AdventureParticipantActionCandidateError("participant action candidate sequence is invalid")


@dataclass(frozen=True)
class GovernedParticipantActionBatch:
    """One policy-bound review batch, never authorization to perform an action."""

    participant: AdventureParticipant
    trigger: str
    decision: InitiativeDecision
    candidates: AdventureParticipantActionCandidateBatch

    def __post_init__(self) -> None:
        if not isinstance(self.participant, AdventureParticipant):
            raise TypeError("governed participant action requires an AdventureParticipant")
        if not isinstance(self.trigger, str) or not self.trigger:
            raise AdventureParticipantActionCandidateError("participant action trigger is invalid")
        if not isinstance(self.decision, InitiativeDecision):
            raise TypeError("governed participant action decision is invalid")
        if not isinstance(self.candidates, AdventureParticipantActionCandidateBatch):
            raise TypeError("governed participant action candidates are invalid")
        if not self.decision.allowed:
            raise AdventureParticipantActionCandidateError("participant action policy does not permit a proposal")
        if any(candidate.participant_id != self.participant.participant_id for candidate in self.candidates.candidates):
            raise AdventureParticipantActionCandidateError("participant action candidate targets a different participant")
        if any(candidate.action not in self.participant.initiative_policy.allowed_actions for candidate in self.candidates.candidates):
            raise AdventureParticipantActionCandidateError("participant action is not allowed by policy")


def bind_participant_action_candidates(
    batch: AdventureParticipantActionCandidateBatch,
    roster: AdventureParticipantRoster,
    *,
    participant_id: object,
    trigger: str,
    turns_since_last_action: int | None,
    actions_this_turn: int,
) -> GovernedParticipantActionBatch:
    """Bind parsed candidates to exact roster/policy eligibility without acting.

    The caller owns all dynamic counters.  This function deliberately does not
    keep action history or turn state, and a successful result is only a
    reviewable proposal batch—not a grant, confirmation, transcript, event,
    or scheduler instruction.
    """
    if not isinstance(batch, AdventureParticipantActionCandidateBatch):
        raise TypeError("participant action candidates are invalid")
    if not isinstance(roster, AdventureParticipantRoster):
        raise TypeError("participant action roster is invalid")
    try:
        participant = roster.resolve(participant_id)
        decision = evaluate_initiative(
            participant.initiative_policy,
            trigger=trigger,
            turns_since_last_action=turns_since_last_action,
            actions_this_turn=actions_this_turn,
        )
    except AdventureInitiativeError as error:
        raise AdventureParticipantActionCandidateError("participant action eligibility is invalid") from error
    return GovernedParticipantActionBatch(participant, trigger, decision, batch)


def parse_untrusted_participant_action_candidates(value: object) -> AdventureParticipantActionCandidateBatch:
    """Strictly parse model-shaped action candidates without granting authority."""
    if not isinstance(value, Mapping) or set(value) != {"schema_version", "candidates"}:
        raise AdventureParticipantActionCandidateError("participant action envelope fields are invalid")
    if value["schema_version"] != PARTICIPANT_ACTION_CANDIDATE_SCHEMA_VERSION or not isinstance(value["candidates"], list):
        raise AdventureParticipantActionCandidateError("participant action envelope is invalid")
    candidates = []
    for sequence, raw in enumerate(value["candidates"], 1):
        fields = {"participant_id", "action", "summary", "confidence"}
        if not isinstance(raw, Mapping) or set(raw) != fields:
            raise AdventureParticipantActionCandidateError("participant action candidate fields are invalid")
        candidates.append(AdventureParticipantActionCandidate(
            sequence=sequence,
            candidate_id=f"TP-{sequence:03d}",
            participant_id=raw["participant_id"],
            action=raw["action"],
            summary=raw["summary"],
            confidence=raw["confidence"],
        ))
    return AdventureParticipantActionCandidateBatch(tuple(candidates))


def render_participant_action_candidate_batch(batch: AdventureParticipantActionCandidateBatch) -> str:
    """Render explicit review text without describing a candidate as an action."""
    if not isinstance(batch, AdventureParticipantActionCandidateBatch):
        raise TypeError("participant action candidate batch is invalid")
    lines = ["Participant action candidates (untrusted; not performed or staged):"]
    if not batch.candidates:
        lines.append("(none; no participant action was proposed)")
    for candidate in batch.candidates:
        lines.extend((
            f"{candidate.candidate_id} {candidate.participant_id} [{candidate.action}]",
            f"  Proposed wording (untrusted): {json.dumps(candidate.summary)}",
            f"  Model-declared confidence (advisory): {candidate.confidence:.2f}",
        ))
    lines.append(
        "Review output alone cannot create a transcript, adventure event, memory, "
        "initiative record, or provider authority."
    )
    return "\n".join(lines)


__all__ = [
    "AdventureParticipantActionCandidate", "AdventureParticipantActionCandidateBatch",
    "AdventureParticipantActionCandidateError", "MAX_PARTICIPANT_ACTION_CANDIDATES",
    "MAX_PARTICIPANT_ACTION_SUMMARY_CHARACTERS", "PARTICIPANT_ACTION_CANDIDATE_SCHEMA_VERSION",
    "GovernedParticipantActionBatch", "bind_participant_action_candidates",
    "parse_untrusted_participant_action_candidates", "participant_action_candidate_json_schema",
    "render_participant_action_candidate_batch",
]
