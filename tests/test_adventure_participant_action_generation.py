import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_events import AdventureEvent
from pipeline.adventure_initiative import AdventureParticipant, PersonaInitiativePolicy
from pipeline.adventure_participant import AdventureParticipantView
from pipeline.adventure_participant_action_generation import (
    AdventureParticipantActionGenerationError,
    AdventureParticipantActionGenerationRequest,
)
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_session import AdventureSessionState


class AdventureParticipantActionGenerationTests(unittest.TestCase):
    def _view(self, *, enabled=True):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        record = AdventureRegistry(directory.name, now=lambda: datetime(2026, 9, 29, tzinfo=UTC)).create("Quiet Ember")
        participant = AdventureParticipant(
            "murr", "Murr", "persona", f"adventure:{record.adventure_id}:participant:murr",
            initiative_policy=PersonaInitiativePolicy(
                enabled=enabled, allowed_triggers=("player_turn",), allowed_actions=("suggest",),
            ),
        )
        event = AdventureEvent(1, "AE-000001", "discovery", "The crew finds a brass key.", None, "2026-09-29T00:00:00+00:00")
        return AdventureParticipantView.from_session(
            AdventureSessionState(record=record, event_count=1, context_events=(event,)), participant,
        )

    def test_request_uses_one_bounded_view_only_after_policy_allows_generation(self):
        request = AdventureParticipantActionGenerationRequest.from_view(
            self._view(), trigger="player_turn", user_text="The crew pauses at the hatch.",
            turns_since_last_action=None, actions_this_turn=0,
            generation_id="TPG-" + "a" * 32,
        )

        system, source = request.messages()
        self.assertIn("'murr'", system["content"])
        self.assertIn("Allowed action kinds: suggest", system["content"])
        self.assertIn("The crew finds a brass key.", source["content"])
        self.assertNotIn("memory_namespace", source["content"])
        self.assertNotIn("participant:murr", source["content"])
        self.assertEqual("TPG-" + "a" * 32, request.generation_id)

    def test_disabled_or_wrong_trigger_policy_fails_before_any_request(self):
        with self.assertRaisesRegex(AdventureParticipantActionGenerationError, "not eligible"):
            AdventureParticipantActionGenerationRequest.from_view(
                self._view(enabled=False), trigger="player_turn", user_text="Wait.",
                turns_since_last_action=None, actions_this_turn=0,
            )
        with self.assertRaisesRegex(AdventureParticipantActionGenerationError, "not eligible"):
            AdventureParticipantActionGenerationRequest.from_view(
                self._view(), trigger="idle_tick", user_text="Wait.",
                turns_since_last_action=None, actions_this_turn=0,
            )


if __name__ == "__main__":
    unittest.main()
