import sys
import tempfile
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.assistant import AssistantSession
from pipeline.command_help import detect_command_help


class AdventureCommandTests(unittest.TestCase):
    def _config(self):
        return type("Config", (), {
            "chat_model": "test-model", "domain": "personal", "max_session_messages": 4,
            "max_memories": 2, "memory_policy": "off", "debug_level": "off",
        })()

    def _session(self, root, calls):
        registry = AdventureRegistry(root, now=lambda: datetime(2026, 8, 15, tzinfo=UTC))
        return AssistantSession(
            self._config(), "Persona", policy="Policy", adventure_registry=registry,
            chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "unexpected"}},
            memory_loader=lambda **kwargs: [],
        )

    def test_commands_create_list_and_inspect_metadata_without_a_model_or_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            self.assertEqual("No adventure workspaces are registered.", session.respond("adventure list"))
            created = session.respond("adventure create Quiet Ember")
            self.assertIn("Created adventure workspace: Quiet Ember", created)
            self.assertIn("metadata-only", created)
            self.assertIn("Quiet Ember", session.respond("adventure list"))
            inspected = session.respond("adventure inspect quiet ember")
            self.assertIn("manifest only", inspected)
            self.assertEqual([], calls)
            self.assertEqual([], session.messages)
            self.assertEqual([], session.proposals)

    def test_duplicate_missing_and_invalid_commands_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            self.assertEqual("Usage: adventure create <title>", session.respond("adventure create"))
            self.assertEqual("Adventure workspace not found.", session.respond("adventure inspect missing"))
            session.respond("adventure create Quiet Ember")
            self.assertIn("was not created", session.respond("adventure create quiet ember"))
            self.assertEqual([], calls)

    def test_help_is_core_owned_and_explicit(self):
        help_payload = detect_command_help("How do I create an adventure?")
        self.assertIsNotNone(help_payload)
        self.assertIn("adventure create <title>", help_payload.render())

    def test_load_is_session_local_and_injects_only_metadata_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            self.assertIn("loaded: Quiet Ember", session.respond("adventure load Quiet Ember"))
            self.assertIn("metadata-only", session.respond("adventure status"))
            self.assertEqual(session.respond("adventure status"), session.respond("What is loaded?"))
            self.assertEqual("unexpected", session.respond("What is in the workspace?"))
            system_prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("MOUNTED ADVENTURE WORKSPACE", system_prompt)
            self.assertIn("no authoritative story events", system_prompt)
            self.assertFalse(session.roleplay_state.active)
            self.assertIn("unloaded: Quiet Ember", session.respond("adventure unload"))
            self.assertEqual("Adventure workspace: none loaded.", session.respond("adventure status"))


if __name__ == "__main__":
    unittest.main()
