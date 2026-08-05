import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession


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
        self.assertIn("injected into normal chat prompts", result)
        self.assertEqual(before, after)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()