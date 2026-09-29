import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_participant_action import (
    AdventureParticipantActionCandidateError,
    bind_participant_action_candidates,
    parse_untrusted_participant_action_candidates,
    render_participant_action_candidate_batch,
)
from pipeline.adventure_initiative import AdventureParticipant, AdventureParticipantRoster, PersonaInitiativePolicy


class AdventureParticipantActionCandidateTests(unittest.TestCase):
    def test_closed_candidate_batch_is_noncanonical_and_rendered_for_review(self):
        batch = parse_untrusted_participant_action_candidates({
            "schema_version": 1,
            "candidates": [{
                "participant_id": "MURR",
                "action": "suggest",
                "summary": "Suggest checking the hatch mechanism first.",
                "confidence": 0.8,
            }],
        })

        self.assertEqual("TP-001", batch.candidates[0].candidate_id)
        self.assertEqual("murr", batch.candidates[0].participant_id)
        rendered = render_participant_action_candidate_batch(batch)
        self.assertIn("not performed or staged", rendered)
        self.assertIn("cannot create a transcript, adventure event, memory", rendered)

    def test_unknown_fields_actions_and_unbounded_summaries_fail_closed(self):
        for candidate in (
            {"participant_id": "murr", "action": "hack", "summary": "No.", "confidence": 0.5},
            {"participant_id": "murr", "action": "speak", "summary": "x" * 601, "confidence": 0.5},
            {"participant_id": "murr", "action": "speak", "summary": "Hello.", "confidence": 0.5, "authority": "yes"},
        ):
            with self.assertRaises(AdventureParticipantActionCandidateError):
                parse_untrusted_participant_action_candidates({"schema_version": 1, "candidates": [candidate]})

    def test_empty_batch_is_valid_but_never_means_silence_was_performed(self):
        batch = parse_untrusted_participant_action_candidates({"schema_version": 1, "candidates": []})
        self.assertIn("no participant action was proposed", render_participant_action_candidate_batch(batch))

    def test_binding_requires_exact_eligible_roster_member_and_allowed_action(self):
        policy = PersonaInitiativePolicy(
            enabled=True, allowed_triggers=("player_turn",), allowed_actions=("suggest",),
        )
        roster = AdventureParticipantRoster("quiet-ember", (
            AdventureParticipant(
                "murr", "Murr", "persona", "adventure:quiet-ember:participant:murr",
                initiative_policy=policy,
            ),
        ))
        batch = parse_untrusted_participant_action_candidates({
            "schema_version": 1,
            "candidates": [{
                "participant_id": "murr", "action": "suggest",
                "summary": "Suggest examining the latch.", "confidence": 0.7,
            }],
        })

        governed = bind_participant_action_candidates(
            batch, roster, participant_id="MURR", trigger="player_turn",
            turns_since_last_action=None, actions_this_turn=0,
        )
        self.assertTrue(governed.decision.allowed)
        self.assertEqual("murr", governed.participant.participant_id)

        with self.assertRaisesRegex(AdventureParticipantActionCandidateError, "policy does not permit"):
            bind_participant_action_candidates(
                batch, roster, participant_id="murr", trigger="idle_tick",
                turns_since_last_action=None, actions_this_turn=0,
            )
        wrong_target = parse_untrusted_participant_action_candidates({
            "schema_version": 1,
            "candidates": [{
                "participant_id": "rook", "action": "suggest",
                "summary": "Suggest examining the latch.", "confidence": 0.7,
            }],
        })
        with self.assertRaisesRegex(AdventureParticipantActionCandidateError, "different participant"):
            bind_participant_action_candidates(
                wrong_target, roster, participant_id="murr", trigger="player_turn",
                turns_since_last_action=None, actions_this_turn=0,
            )


if __name__ == "__main__":
    unittest.main()
