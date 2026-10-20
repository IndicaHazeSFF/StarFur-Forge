"""Provider-free contracts for active adventure participants."""

from __future__ import annotations

from dataclasses import dataclass, field


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
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 64:
                raise AdventureInitiativeError(f"{field} must be between 1 and 64")
        if not isinstance(self.retain_salient_events, bool):
            raise AdventureInitiativeError("retain_salient_events must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "max_context_facts": self.max_context_facts,
            "max_knowledge_facts": self.max_knowledge_facts,
            "retain_salient_events": self.retain_salient_events,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureParticipantMemoryPolicy":
        fields = {"max_context_facts", "max_knowledge_facts", "retain_salient_events"}
        if not isinstance(value, dict) or set(value) != fields:
            raise AdventureInitiativeError("participant memory policy is invalid")
        return cls(**value)


@dataclass(frozen=True)
class AdventureParticipant:
    """A governed participant whose memory is isolated to an adventure."""

    participant_id: str
    display_name: str
    kind: str
    memory_namespace: str
    memory_policy: AdventureParticipantMemoryPolicy = AdventureParticipantMemoryPolicy()
    initiative_policy: "PersonaInitiativePolicy" = field(default_factory=lambda: PersonaInitiativePolicy())

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
        if not isinstance(self.initiative_policy, PersonaInitiativePolicy):
            raise TypeError("initiative_policy must be PersonaInitiativePolicy")
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

    def to_dict(self) -> dict[str, object]:
        """Serialize package declarations, never their Core-derived namespaces."""
        return {
            "schema_version": 2,
            "participants": [
                {
                    "id": participant.participant_id,
                    "display_name": participant.display_name,
                    "kind": participant.kind,
                    "memory_policy": participant.memory_policy.to_dict(),
                    "initiative_policy": participant.initiative_policy.to_dict(),
                }
                for participant in self.participants
            ],
        }

    @classmethod
    def from_dict(cls, adventure_id: object, value: object) -> "AdventureParticipantRoster":
        """Validate package data and derive the only accepted memory namespaces."""
        fields = {"schema_version", "participants"}
        if not isinstance(value, dict) or set(value) != fields:
            raise AdventureInitiativeError("participant roster is invalid")
        version = value["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version not in {1, 2}:
            raise AdventureInitiativeError("participant roster is invalid")
        schema_version = value["schema_version"]
        entries = value["participants"]
        if not isinstance(entries, list) or len(entries) > 32:
            raise AdventureInitiativeError("participant roster entries are invalid")
        normalized_adventure_id = _bounded_text(
            adventure_id, field="adventure_id", maximum=96,
        ).casefold()
        participants = []
        for entry in entries:
            entry_fields = {"id", "display_name", "kind", "memory_policy"}
            if schema_version == 2:
                entry_fields.add("initiative_policy")
            if not isinstance(entry, dict) or set(entry) != entry_fields:
                raise AdventureInitiativeError("participant roster entry is invalid")
            participant_id = _bounded_text(entry["id"], field="participant_id", maximum=96).casefold()
            participants.append(AdventureParticipant(
                participant_id, entry["display_name"], entry["kind"],
                f"adventure:{normalized_adventure_id}:participant:{participant_id}",
                AdventureParticipantMemoryPolicy.from_dict(entry["memory_policy"]),
                PersonaInitiativePolicy.from_dict(entry["initiative_policy"])
                if schema_version == 2 else PersonaInitiativePolicy(),
            ))
        return cls(normalized_adventure_id, tuple(participants))


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
            if (not isinstance(values, tuple) or not 1 <= len(values) <= len(allowed)
                    or any(not isinstance(value, str) or value not in allowed for value in values)):
                raise AdventureInitiativeError(f"{field} contains an unsupported value")
            if len(set(values)) != len(values):
                raise AdventureInitiativeError(f"{field} must not repeat values")
        if isinstance(self.cooldown_turns, bool) or not isinstance(self.cooldown_turns, int) or not 0 <= self.cooldown_turns <= 100:
            raise AdventureInitiativeError("cooldown_turns must be between 0 and 100")
        if isinstance(self.max_actions_per_turn, bool) or not isinstance(self.max_actions_per_turn, int) or not 1 <= self.max_actions_per_turn <= 4:
            raise AdventureInitiativeError("max_actions_per_turn must be between 1 and 4")

    def to_dict(self) -> dict[str, object]:
        """Serialize policy declarations only; not dynamic initiative history."""
        return {
            "enabled": self.enabled,
            "allowed_triggers": list(self.allowed_triggers),
            "allowed_actions": list(self.allowed_actions),
            "cooldown_turns": self.cooldown_turns,
            "max_actions_per_turn": self.max_actions_per_turn,
            "requires_confirmation": self.requires_confirmation,
        }

    @classmethod
    def from_dict(cls, value: object) -> "PersonaInitiativePolicy":
        """Strictly parse package declarations without accepting runtime state."""
        fields = {
            "enabled", "allowed_triggers", "allowed_actions", "cooldown_turns",
            "max_actions_per_turn", "requires_confirmation",
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise AdventureInitiativeError("initiative policy is invalid")
        triggers = value["allowed_triggers"]
        actions = value["allowed_actions"]
        if not isinstance(triggers, list) or not isinstance(actions, list):
            raise AdventureInitiativeError("initiative policy is invalid")
        return cls(
            enabled=value["enabled"], allowed_triggers=tuple(triggers),
            allowed_actions=tuple(actions), cooldown_turns=value["cooldown_turns"],
            max_actions_per_turn=value["max_actions_per_turn"],
            requires_confirmation=value["requires_confirmation"],
        )


@dataclass(frozen=True)
class InitiativeDecision:
    allowed: bool
    reason: str


def evaluate_initiative(policy: PersonaInitiativePolicy, *, trigger: str,
                        turns_since_last_action: int | None, actions_this_turn: int) -> InitiativeDecision:
    """Check whether Core may offer one bounded initiative opportunity."""
    if not isinstance(policy, PersonaInitiativePolicy):
        raise TypeError("policy must be PersonaInitiativePolicy")
    if not isinstance(trigger, str) or trigger not in INITIATIVE_TRIGGERS:
        raise AdventureInitiativeError("initiative trigger is unsupported")
    if isinstance(actions_this_turn, bool) or not isinstance(actions_this_turn, int) or actions_this_turn < 0:
        raise AdventureInitiativeError("actions_this_turn must be non-negative")
    if turns_since_last_action is not None and (isinstance(turns_since_last_action, bool)
            or not isinstance(turns_since_last_action, int) or turns_since_last_action < 0):
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
