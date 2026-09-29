import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_initiative import AdventureParticipant, AdventureParticipantRoster, PersonaInitiativePolicy
from pipeline.adventure_participant_action_coordinator import (
    AdventureParticipantActionCoordinator,
    AdventureParticipantActionCoordinatorError,
)
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_session import AdventureSessionState


class _Provider:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def propose(self, request):
        self.requests.append(request)
        return self.response


class AdventureParticipantActionCoordinatorTests(unittest.TestCase):
    def _session(self, *, enabled=True):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        record = AdventureRegistry(directory.name, now=lambda: datetime(2026, 9, 29, tzinfo=UTC)).create("Quiet Ember")
        roster = AdventureParticipantRoster(record.adventure_id, (
            AdventureParticipant(
                "murr", "Murr", "persona", f"adventure:{record.adventure_id}:participant:murr",
                initiative_policy=PersonaInitiativePolicy(
                    enabled=enabled, allowed_triggers=("player_turn",), allowed_actions=("suggest",),
                ),
            ),
        ))
        event = AdventureEvent(1, "AE-000001", "discovery", "The crew finds a brass key.", None, "2026-09-29T00:00:00+00:00")
        return AdventureSessionState(record=record, event_count=1, context_events=(event,), participant_roster=roster)

    def test_coordinator_returns_only_exact_policy_bound_review_candidates(self):
        provider = _Provider({
            "schema_version": 1,
            "candidates": [{
                "participant_id": "murr", "action": "suggest",
                "summary": "Suggest inspecting the key before opening the hatch.", "confidence": 0.8,
            }],
        })
        proposal = AdventureParticipantActionCoordinator(provider).propose(
            self._session(), participant_id="MURR", trigger="player_turn",
            user_text="The crew pauses at the hatch.", turns_since_last_action=None, actions_this_turn=0,
        )

        self.assertEqual("murr", proposal.governed.participant.participant_id)
        self.assertEqual("TP-001", proposal.batch.candidates[0].candidate_id)
        self.assertEqual(1, len(provider.requests))
        self.assertFalse(hasattr(proposal, "event_id"))
        self.assertNotIn("participant:murr", provider.requests[0].messages()[1]["content"])

    def test_ineligible_or_cross_participant_output_fails_before_review(self):
        provider = _Provider({
            "schema_version": 1,
            "candidates": [{
                "participant_id": "rook", "action": "suggest", "summary": "Suggest waiting.", "confidence": 0.8,
            }],
        })
        coordinator = AdventureParticipantActionCoordinator(provider)
        with self.assertRaisesRegex(AdventureParticipantActionCoordinatorError, "failed safely") as disabled:
            coordinator.propose(
                self._session(enabled=False), participant_id="murr", trigger="player_turn",
                user_text="Wait.", turns_since_last_action=None, actions_this_turn=0,
            )
        self.assertEqual("policy_ineligible", disabled.exception.reason)
        self.assertEqual([], provider.requests)

        with self.assertRaisesRegex(AdventureParticipantActionCoordinatorError, "failed safely") as mismatch:
            coordinator.propose(
                self._session(), participant_id="murr", trigger="player_turn",
                user_text="Wait.", turns_since_last_action=None, actions_this_turn=0,
            )
        self.assertEqual("candidate_envelope_invalid", mismatch.exception.reason)


if __name__ == "__main__":
    unittest.main()
