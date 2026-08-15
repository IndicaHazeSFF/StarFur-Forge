import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession
from pipeline.persona_development import PersonaDevelopmentState


class PersonaInspectTests(unittest.TestCase):
    def test_persona_inspect_is_read_only_and_bounded(self):
        config = AssistantConfig(
            "test-model", Path("persona/default.md"), Path("config/assistant_policy.md"),
            "personal", 4, 2, "off", "off",
        )
        calls = []
        session = AssistantSession(
            config, "Persona", chat=lambda **kwargs: calls.append(kwargs),
            memory_loader=lambda **kwargs: [],
        )
        before = (list(session.messages), list(session.proposals), list(session.last_memory_ids))
        result = session.respond("persona inspect")
        after = (list(session.messages), list(session.proposals), list(session.last_memory_ids))
        self.assertIn("ID: default", result)
        self.assertIn("Display name: StarFur", result)
        self.assertIn("not displayed", result)
        self.assertIn("Derived behavior controls", result)
        self.assertIn("Persona-local development", result)
        self.assertIn("storage: restart-ephemeral", result)
        self.assertIn("behavior guidance is injected into normal chat prompts", result)
        self.assertEqual(before, after)
        self.assertEqual(calls, [])

    def test_persona_inspect_reports_only_bounded_development_counts(self):
        config = AssistantConfig(
            "test-model", Path("persona/default.md"), Path("config/assistant_policy.md"),
            "personal", 4, 2, "off", "off",
        )
        development = PersonaDevelopmentState.empty("default").record_interest(
            "Rust", observed_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        )
        session = AssistantSession(
            config, "Persona", chat=lambda **kwargs: None,
            memory_loader=lambda **kwargs: [], persona_development_state=development,
        )

        result = session.respond("persona inspect")

        self.assertIn("interests: 1", result)
        self.assertIn("verified skills: 0", result)
        self.assertIn("real-world relationships: 0", result)
        self.assertNotIn("Rust", result)


if __name__ == "__main__":
    unittest.main()
