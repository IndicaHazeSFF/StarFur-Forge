import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession
from pipeline.persona_attention import select_persona_attention
from pipeline.persona_development import PersonaDevelopmentState


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


class PersonaAttentionTests(unittest.TestCase):
    def _state(self):
        state = PersonaDevelopmentState.empty("default")
        state = state.record_interest("Rust programming", observed_at=NOW, strength=0.7)
        state = state.record_interest("Pixel art", observed_at=NOW, strength=0.4)
        return state.record_verified_skill("Python", verified_at=NOW, strength=0.9)

    def test_direct_interest_overlap_is_deterministic_and_bounded(self):
        state = self._state()
        first = select_persona_attention(
            "Could you compare Rust programming approaches?", state, as_of=NOW,
        )
        second = select_persona_attention(
            "Could you compare Rust programming approaches?", state, as_of=NOW,
        )
        self.assertEqual(first, second)
        self.assertEqual(first.persona_id, "default")
        self.assertEqual([item.concept for item in first.items], ["Rust programming"])
        self.assertIn("matched interest token(s): programming, rust", first.items[0].reasons)

    def test_unrelated_interest_and_verified_skill_are_not_selected(self):
        selected = select_persona_attention("Explain a router reset.", self._state(), as_of=NOW)
        self.assertEqual(selected.items, ())

    def test_decay_and_limit_affect_only_current_attention_snapshot(self):
        state = self._state()
        initial = select_persona_attention("Rust and pixel art", state, as_of=NOW, limit=1)
        later = select_persona_attention(
            "Rust and pixel art", state, as_of=NOW + timedelta(days=180), limit=1,
        )
        self.assertEqual(len(initial.items), 1)
        self.assertEqual(len(later.items), 1)
        self.assertLess(later.items[0].effective_confidence, initial.items[0].effective_confidence)
        self.assertEqual(len(state.interests), 2)

    def test_assistant_injects_only_matching_interest_and_reports_its_size(self):
        calls = []
        config = AssistantConfig(
            "test-model", Path("persona/default.md"), Path("config/assistant_policy.md"),
            "personal", 6, 2, "off", "off",
        )
        active_state = PersonaDevelopmentState.empty("default").record_interest(
            "Rust programming", observed_at=datetime.now(timezone.utc), strength=0.7,
        )
        session = AssistantSession(
            config, "Persona", policy="Policy", memory_loader=lambda **kwargs: [],
            chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "answer"}},
            persona_development_state=active_state,
        )
        self.assertEqual(session.respond("Talk about Rust programming."), "answer")
        matching_prompt = calls[-1]["messages"][0]["content"]
        self.assertIn("PERSONA ATTENTION", matching_prompt)
        self.assertIn("Rust programming", matching_prompt)
        self.assertNotIn("Pixel art", matching_prompt)
        self.assertIn("Persona attention:", session.context_stats())

        self.assertEqual(session.respond("Explain a router reset."), "answer")
        self.assertNotIn("PERSONA ATTENTION", calls[-1]["messages"][0]["content"])

    def test_mismatched_persona_development_namespace_is_rejected(self):
        config = AssistantConfig(
            "test-model", Path("persona/default.md"), Path("config/assistant_policy.md"),
            "personal", 6, 2, "off", "off",
        )
        with self.assertRaisesRegex(ValueError, "persona_id"):
            AssistantSession(
                config, "Persona", policy="Policy", memory_loader=lambda **kwargs: [],
                chat=lambda **kwargs: {"message": {"content": "answer"}},
                persona_development_state=PersonaDevelopmentState.empty("other"),
            )


if __name__ == "__main__":
    unittest.main()
