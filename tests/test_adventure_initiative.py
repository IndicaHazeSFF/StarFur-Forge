import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_initiative import (
    AdventureInitiativeError, AdventureParticipant, AdventureParticipantMemoryPolicy, AdventureParticipantRoster,
    PersonaInitiativePolicy, evaluate_initiative,
)


class AdventureInitiativeTests(unittest.TestCase):
    def test_participant_memory_is_bounded_and_adventure_scoped(self):
        participant = AdventureParticipant(
            "Murr", "Murr", "persona", "adventure:quiet-ember:participant:murr",
            AdventureParticipantMemoryPolicy(max_context_facts=12, max_knowledge_facts=8),
        )
        self.assertEqual("murr", participant.participant_id)
        self.assertEqual(12, participant.memory_policy.max_context_facts)
        with self.assertRaisesRegex(AdventureInitiativeError, "adventure-scoped"):
            AdventureParticipant("rook", "Rook", "npc", "persona:rook")

    def test_disabled_policy_and_cooldown_are_explainable(self):
        disabled = evaluate_initiative(PersonaInitiativePolicy(), trigger="player_turn", turns_since_last_action=None, actions_this_turn=0)
        self.assertEqual((False, "initiative disabled"), (disabled.allowed, disabled.reason))
        decision = evaluate_initiative(PersonaInitiativePolicy(enabled=True, cooldown_turns=2), trigger="player_turn", turns_since_last_action=1, actions_this_turn=0)
        self.assertEqual((False, "cooldown active"), (decision.allowed, decision.reason))

    def test_enabled_policy_allows_one_bounded_proposal(self):
        policy = PersonaInitiativePolicy(enabled=True, cooldown_turns=1, max_actions_per_turn=1)
        decision = evaluate_initiative(policy, trigger="world_event", turns_since_last_action=1, actions_this_turn=0)
        self.assertTrue(decision.allowed)
        limited = evaluate_initiative(policy, trigger="world_event", turns_since_last_action=3, actions_this_turn=1)
        self.assertFalse(limited.allowed)

    def test_roster_is_exactly_adventure_scoped_and_resolves_without_guessing(self):
        roster = AdventureParticipantRoster("quiet-ember", (
            AdventureParticipant("Murr", "Murr", "persona", "adventure:quiet-ember:participant:murr"),
            AdventureParticipant("rook", "Rook", "npc", "adventure:quiet-ember:participant:rook"),
        ))
        self.assertEqual(["murr", "rook"], [item.participant_id for item in roster.participants])
        self.assertEqual("murr", roster.resolve("MURR").participant_id)
        with self.assertRaisesRegex(AdventureInitiativeError, "not found"):
            roster.resolve("mu")
        with self.assertRaisesRegex(AdventureInitiativeError, "does not match adventure"):
            AdventureParticipantRoster("quiet-ember", (
                AdventureParticipant("murr", "Murr", "persona", "adventure:other:participant:murr"),
            ))

    def test_roster_manifest_round_trip_derives_namespaces_instead_of_accepting_them(self):
        roster = AdventureParticipantRoster("quiet-ember", (
            AdventureParticipant("Murr", "Murr", "persona", "adventure:quiet-ember:participant:murr"),
            AdventureParticipant("rook", "Rook", "npc", "adventure:quiet-ember:participant:rook"),
        ))
        serialized = roster.to_dict()
        self.assertNotIn("memory_namespace", serialized["participants"][0])
        self.assertEqual(roster, AdventureParticipantRoster.from_dict("QUIET-EMBER", serialized))
        serialized["participants"][0]["memory_namespace"] = "persona:murr"
        with self.assertRaisesRegex(AdventureInitiativeError, "entry is invalid"):
            AdventureParticipantRoster.from_dict("quiet-ember", serialized)

    def test_roster_v2_round_trips_policy_while_v1_loads_disabled_default(self):
        enabled = PersonaInitiativePolicy(
            enabled=True, allowed_triggers=("player_turn",), allowed_actions=("speak", "suggest"),
            cooldown_turns=2, max_actions_per_turn=1, requires_confirmation=True,
        )
        roster = AdventureParticipantRoster("quiet-ember", (
            AdventureParticipant(
                "murr", "Murr", "persona", "adventure:quiet-ember:participant:murr",
                initiative_policy=enabled,
            ),
        ))

        serialized = roster.to_dict()
        self.assertEqual(2, serialized["schema_version"])
        self.assertEqual(enabled, AdventureParticipantRoster.from_dict("quiet-ember", serialized).participants[0].initiative_policy)

        legacy = {
            "schema_version": 1,
            "participants": [{
                "id": "murr", "display_name": "Murr", "kind": "persona",
                "memory_policy": AdventureParticipantMemoryPolicy().to_dict(),
            }],
        }
        self.assertFalse(AdventureParticipantRoster.from_dict("quiet-ember", legacy).participants[0].initiative_policy.enabled)

    def test_policy_rejects_runtime_or_unknown_manifest_fields(self):
        payload = PersonaInitiativePolicy().to_dict()
        payload["turns_since_last_action"] = 0
        with self.assertRaisesRegex(AdventureInitiativeError, "initiative policy is invalid"):
            PersonaInitiativePolicy.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
