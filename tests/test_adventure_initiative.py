import unittest

from pipeline.adventure_initiative import (
    AdventureInitiativeError, AdventureParticipant, AdventureParticipantMemoryPolicy,
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


if __name__ == "__main__":
    unittest.main()
