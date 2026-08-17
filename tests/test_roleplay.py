import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantSession
from pipeline.roleplay import RoleplaySessionState, detect_casual_roleplay_start


class RoleplaySessionTests(unittest.TestCase):
    def _config(self):
        return type("Config", (), {
            "chat_model": "test-model", "domain": "personal", "max_session_messages": 4,
            "max_memories": 2, "memory_policy": "conservative", "debug_level": "off",
        })()

    def test_state_is_explicit_bounded_and_non_persistent(self):
        state = RoleplaySessionState.inactive().begin("  Quiet   Ember ")
        self.assertTrue(state.active)
        self.assertEqual("Quiet Ember", state.title)
        self.assertEqual("session_ephemeral", state.public_dict()["storage"])
        self.assertFalse(state.end().active)
        with self.assertRaises(ValueError):
            RoleplaySessionState(active=False, title="not allowed")

    def test_casual_detection_accepts_only_clear_start_phrases(self):
        self.assertTrue(detect_casual_roleplay_start("Murr, let's roleplay."))
        self.assertTrue(detect_casual_roleplay_start("Let's go on an adventure!"))
        self.assertFalse(detect_casual_roleplay_start("I enjoy roleplay games."))
        self.assertFalse(detect_casual_roleplay_start("Could we roleplay someday?"))

    def test_begin_end_and_casual_entry_do_not_call_a_model(self):
        calls = []
        session = AssistantSession(
            self._config(), "Persona", chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "unused"}},
            memory_loader=lambda **kwargs: [],
        )
        session.messages.extend([{"role": "user", "content": "ordinary"}])
        self.assertIn("Roleplay mode started (Quiet Ember)", session.respond("roleplay begin Quiet Ember"))
        self.assertEqual([], session.messages)
        self.assertIn("active (Quiet Ember", session.respond("roleplay status"))
        self.assertIn("Roleplay mode ended", session.respond("roleplay end"))
        self.assertEqual("Roleplay mode: inactive.", session.respond("roleplay status"))
        self.assertIn("Roleplay mode started", session.respond("Murr, let's roleplay."))
        self.assertEqual([], calls)

    def test_active_roleplay_scopes_eligible_proposals_and_prompt_only_while_active(self):
        calls = []
        persisted = []

        def fake_chat(**kwargs):
            calls.append(kwargs)
            if len(calls) % 2 == 1:
                return {"message": {"content": "narration"}}
            return {"message": {"content": (
                '{"store": true, "subject": "User", "memory_type": "preference", '
                '"summary": "Likes starlight", "details": "", "importance": 0.8, '
                '"confidence": 0.8, "retention": "long_term", "domain": "personal", "source": "x"}'
            )}}

        session = AssistantSession(
            self._config(), "Persona", chat=fake_chat, memory_loader=lambda **kwargs: [],
            proposal_creator=lambda proposal, **kwargs: persisted.append((proposal, kwargs)) or {"proposal_id": 1, "action": "created"},
        )
        session.respond("roleplay begin Quiet Ember")
        self.assertEqual("narration", session.respond("I prefer starlight."))
        self.assertEqual("roleplay", persisted[-1][0]["visibility_scope"])
        self.assertIn("ACTIVE ROLEPLAY SESSION", calls[0]["messages"][0]["content"])
        self.assertIn("never expose numeric scores", calls[0]["messages"][0]["content"])
        self.assertIn("Roleplay session: active", session.context_stats())

        session.respond("roleplay end")
        self.assertEqual("narration", session.respond("I prefer quiet libraries."))
        self.assertNotIn("ACTIVE ROLEPLAY SESSION", calls[-2]["messages"][0]["content"])

    def test_explicit_remember_in_roleplay_inherits_scope(self):
        created = []
        session = AssistantSession(
            self._config(), "Persona", chat=lambda **kwargs: {"message": {"content": "unused"}},
            memory_loader=lambda **kwargs: [], memory_creator=lambda **kwargs: created.append(kwargs) or 1,
        )
        session.respond("roleplay begin")
        with patch("pipeline.assistant.assistant_public_id", return_value="M-001"):
            session.respond("remember this: Story fact")
        self.assertEqual("roleplay", created[-1]["visibility_scope"])

    def test_roleplay_hides_relationship_meter_values_from_normal_model_context(self):
        calls = []
        relationship = {
            "id": 9, "memory_type": "relationship_context", "summary": "Vespera trust level",
            "details": "Trust: 49/100. Comfort: 58 / 100.", "confidence": 0.9,
        }
        session = AssistantSession(
            self._config(), "Persona",
            chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "narration"}},
            memory_loader=lambda **kwargs: [relationship],
        )
        session.respond("roleplay begin Quiet Ember")
        self.assertEqual("narration", session.respond("How does Vespera feel about the player?"))
        prompt = calls[-1]["messages"][0]["content"]
        self.assertNotIn("49/100", prompt)
        self.assertNotIn("58 / 100", prompt)
        self.assertIn("qualitative internal state", prompt)

        session.respond("Show the relationship meter scores")
        self.assertIn("49/100", calls[-1]["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
