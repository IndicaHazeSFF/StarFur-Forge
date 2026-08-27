"""Provider-free contracts for active adventure participants."""

from __future__ import annotations

from dataclasses import dataclass


class AdventureInitiativeError(ValueError):
    """Raised when an initiative or participant contract is invalid."""


INITIATIVE_TRIGGERS = frozenset({"player_turn", "idle_tick", "world_event", "relationship_change"})
INITIATIVE_ACTIONS = frozenset({"observe", "speak", "suggest", "move", "investigate", "assist", "decline"})
PARTICIPANT_KINDS = frozenset({"persona", "npc"})


def _bounded_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise AdventureInitiativeError(f"{field} must be text")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise AdventureInitiativeError(f"{field} is invalid")
    return normalized


@dataclass(frozen=True)
class AdventureParticipantMemoryPolicy:
    """Bounded memory view for one persona or NPC in one adventure."""

    max_context_facts: int = 16
    max_knowledge_facts: int = 16
    retain_salient_events: bool = True

    def __post_init__(self) -> None:
        for field in ("max_context_facts", "max_knowledge_facts"):
            value = getattr(self, field)
            if not isinstance(value, int) or not 1 <= value <= 64:
                raise AdventureInitiativeError(f"{field} must be between 1 and 64")
        if not isinstance(self.retain_salient_events, bool):
            raise AdventureInitiativeError("retain_salient_events must be boolean")


@dataclass(frozen=True)
class AdventureParticipant:
    """A governed participant whose memory is isolated to an adventure."""

    participant_id: str
    display_name: str
    kind: str
    memory_namespace: str
    memory_policy: AdventureParticipantMemoryPolicy = AdventureParticipantMemoryPolicy()

    def __post_init__(self) -> None:
        participant_id = _bounded_text(self.participant_id, field="participant_id", maximum=96).casefold()
        display_name = _bounded_text(self.display_name, field="display_name", maximum=96)
        kind = _bounded_text(self.kind, field="kind", maximum=16).casefold()
        namespace = _bounded_text(self.memory_namespace, field="memory_namespace", maximum=160)
        if kind not in PARTICIPANT_KINDS:
            raise AdventureInitiativeError("participant kind is unsupported")
        if not namespace.startswith("adventure:"):
            raise AdventureInitiativeError("participant memory must be adventure-scoped")
        if not isinstance(self.memory_policy, AdventureParticipantMemoryPolicy):
            raise TypeError("memory_policy must be AdventureParticipantMemoryPolicy")
        object.__setattr__(self, "participant_id", participant_id)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "memory_namespace", namespace)


@dataclass(frozen=True)
class AdventureParticipantRoster:
    """A validated adventure-local participant set with no persistence or I/O."""

    adventure_id: str
    participants: tuple[AdventureParticipant, ...]

    def __post_init__(self) -> None:
        adventure_id = _bounded_text(self.adventure_id, field="adventure_id", maximum=96).casefold()
        if not isinstance(self.participants, tuple) or len(self.participants) > 32:
            raise AdventureInitiativeError("participant roster must contain at most 32 participants")
        if not all(isinstance(participant, AdventureParticipant) for participant in self.participants):
            raise TypeError("participant roster requires AdventureParticipants")
        identifiers = [participant.participant_id for participant in self.participants]
        if len(identifiers) != len(set(identifiers)):
            raise AdventureInitiativeError("participant roster identifiers must be unique")
        expected_prefix = f"adventure:{adventure_id}:participant:"
        if any(not participant.memory_namespace.startswith(expected_prefix) for participant in self.participants):
            raise AdventureInitiativeError("participant roster memory namespace does not match adventure")
        object.__setattr__(self, "adventure_id", adventure_id)
        object.__setattr__(self, "participants", tuple(sorted(self.participants, key=lambda item: item.participant_id)))

    def resolve(self, participant_id: object) -> AdventureParticipant:
        """Resolve one exact normalized participant ID without fuzzy matching."""
        identifier = _bounded_text(participant_id, field="participant_id", maximum=96).casefold()
        for participant in self.participants:
            if participant.participant_id == identifier:
                return participant
        raise AdventureInitiativeError("adventure participant was not found")


@dataclass(frozen=True)
class PersonaInitiativePolicy:
    """Explicit permission and pacing limits for a persona's initiative."""

    enabled: bool = False
    allowed_triggers: tuple[str, ...] = ("player_turn", "world_event")
    allowed_actions: tuple[str, ...] = ("observe", "speak", "suggest", "assist", "decline")
    cooldown_turns: int = 1
    max_actions_per_turn: int = 1
    requires_confirmation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool) or not isinstance(self.requires_confirmation, bool):
            raise AdventureInitiativeError("initiative flags must be boolean")
        for field, allowed in (("allowed_triggers", INITIATIVE_TRIGGERS), ("allowed_actions", INITIATIVE_ACTIONS)):
            values = getattr(self, field)
            if not isinstance(values, tuple) or not values or any(value not in allowed for value in values):
                raise AdventureInitiativeError(f"{field} contains an unsupported value")
            if len(set(values)) != len(values):
                raise AdventureInitiativeError(f"{field} must not repeat values")
        if not isinstance(self.cooldown_turns, int) or not 0 <= self.cooldown_turns <= 100:
            raise AdventureInitiativeError("cooldown_turns must be between 0 and 100")
        if not isinstance(self.max_actions_per_turn, int) or not 1 <= self.max_actions_per_turn <= 4:
            raise AdventureInitiativeError("max_actions_per_turn must be between 1 and 4")


@dataclass(frozen=True)
class InitiativeDecision:
    allowed: bool
    reason: str


def evaluate_initiative(policy: PersonaInitiativePolicy, *, trigger: str,
                        turns_since_last_action: int | None, actions_this_turn: int) -> InitiativeDecision:
    """Check whether Core may offer one bounded initiative opportunity."""
    if not isinstance(policy, PersonaInitiativePolicy):
        raise TypeError("policy must be PersonaInitiativePolicy")
    if trigger not in INITIATIVE_TRIGGERS:
        raise AdventureInitiativeError("initiative trigger is unsupported")
    if not isinstance(actions_this_turn, int) or actions_this_turn < 0:
        raise AdventureInitiativeError("actions_this_turn must be non-negative")
    if turns_since_last_action is not None and (not isinstance(turns_since_last_action, int) or turns_since_last_action < 0):
        raise AdventureInitiativeError("turns_since_last_action must be non-negative or None")
    if not policy.enabled:
        return InitiativeDecision(False, "initiative disabled")
    if trigger not in policy.allowed_triggers:
        return InitiativeDecision(False, "trigger not allowed")
    if actions_this_turn >= policy.max_actions_per_turn:
        return InitiativeDecision(False, "per-turn action limit reached")
    if turns_since_last_action is not None and turns_since_last_action < policy.cooldown_turns:
        return InitiativeDecision(False, "cooldown active")
    return InitiativeDecision(True, "eligible for bounded initiative proposal")


__all__ = ["AdventureInitiativeError", "AdventureParticipant", "AdventureParticipantMemoryPolicy", "AdventureParticipantRoster",
           "INITIATIVE_ACTIONS", "INITIATIVE_TRIGGERS", "InitiativeDecision", "PARTICIPANT_KINDS",
           "PersonaInitiativePolicy", "evaluate_initiative"]
