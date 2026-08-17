import sys
import tempfile
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_events import AdventureEventLog
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
            self.assertIn("0 authoritative event(s)", session.respond("adventure status"))
            self.assertEqual(session.respond("adventure status"), session.respond("What is loaded?"))
            self.assertEqual("unexpected", session.respond("What is in the workspace?"))
            system_prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("MOUNTED ADVENTURE WORKSPACE", system_prompt)
            self.assertIn("no recorded authoritative adventure events", system_prompt)
            self.assertFalse(session.roleplay_state.active)
            self.assertIn("unloaded: Quiet Ember", session.respond("adventure unload"))
            self.assertEqual("Adventure workspace: none loaded.", session.respond("adventure status"))

    def test_load_reads_bounded_event_summaries_without_writing_or_calling_a_model(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            record = session.adventure_registry.resolve_title("Quiet Ember")
            log = AdventureEventLog(session.adventure_registry, record)
            for sequence in range(10):
                log.append("discovery", f"The crew discovers clue {sequence}.", details="Private event detail.")

            loaded = session.respond("adventure load Quiet Ember")
            self.assertIn("Loaded 10 authoritative event(s)", loaded)
            self.assertIn("10 authoritative event(s)", session.respond("adventure status"))
            displayed = session.respond("adventure events")
            self.assertIn("AE-000001", displayed)
            self.assertIn("AE-000010", displayed)
            self.assertNotIn("AE-000002", displayed)
            self.assertEqual([], calls)

            self.assertEqual("unexpected", session.respond("What was discovered?"))
            system_prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("RECENT AUTHORITATIVE ADVENTURE EVENTS", system_prompt)
            self.assertIn("clue 9", system_prompt)
            self.assertIn("clue 0", system_prompt)
            self.assertNotIn("clue 1", system_prompt)
            self.assertNotIn("Private event detail", system_prompt)
            self.assertIn(
                "10 authoritative event(s), 8 in bounded replay context; 0 current state fact(s); session-local mount",
                session.context_stats(),
            )

    def test_explicit_record_isolated_and_ordinary_chat_never_creates_events(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            self.assertIn("none loaded", session.respond("adventure record discovery: A signal appears."))
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            self.assertEqual("unexpected", session.respond("The crew finds a signal."))
            self.assertEqual("No authoritative adventure events are recorded for the loaded workspace.", session.respond("adventure events"))

            recorded = session.respond("adventure record discovery: The crew finds an old signal.")
            self.assertIn("AE-000001 [discovery]", recorded)
            self.assertIn("The crew finds an old signal.", session.respond("adventure events"))
            self.assertEqual("Usage: adventure record <event-type>: <summary>", session.respond("adventure record discovery"))
            self.assertIn("unsupported", session.respond("adventure record decoration: The ship is pretty."))
            self.assertEqual(1, session.adventure_session.event_count)
            self.assertEqual([], session.proposals)

    def test_resume_pause_and_end_are_exact_core_lifecycle_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            session.respond("adventure record discovery: The ship has a hidden deck.")
            session.respond("roleplay begin Quiet Ember")

            paused = session.respond("adventure pause")
            self.assertIn("Adventure paused: Quiet Ember", paused)
            self.assertIn("Roleplay mode ended", paused)
            self.assertFalse(session.adventure_session.active)
            self.assertFalse(session.roleplay_state.active)
            self.assertEqual([], calls)

            resumed = session.respond("adventure resume Quiet Ember")
            self.assertIn("Loaded 1 authoritative event(s)", resumed)
            self.assertFalse(session.roleplay_state.active)
            self.assertIn("hidden deck", session.respond("adventure events"))

            session.respond("roleplay begin")
            ended = session.respond("end story now")
            self.assertIn("Adventure session ended: Quiet Ember", ended)
            self.assertIn("Stored events were preserved", ended)
            self.assertFalse(session.adventure_session.active)
            self.assertFalse(session.roleplay_state.active)
            self.assertEqual("No active adventure or roleplay session is running.", session.respond("adventure end"))

    def test_explicit_story_state_is_event_backed_and_refreshed_in_context(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            self.assertEqual("No explicit authoritative story state is recorded for the loaded workspace.", session.respond("adventure state"))
            self.assertIn("AE-000001", session.respond("adventure state set location: bridge"))
            self.assertIn("location: bridge", session.respond("adventure state"))
            self.assertIn("AE-000002", session.respond("adventure state set location: engine room"))
            self.assertIn("location: engine room (AE-000002)", session.respond("adventure state"))
            self.assertEqual("Usage: adventure state set <key>: <value>", session.respond("adventure state set location"))
            self.assertIn("state key", session.respond("adventure state set Current Location: bridge"))
            self.assertEqual([], calls)

            self.assertEqual("unexpected", session.respond("Where is the crew?"))
            prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("CURRENT AUTHORITATIVE STORY STATE", prompt)
            self.assertIn("location: engine room", prompt)
            self.assertNotIn("location: bridge\n", prompt)
            self.assertIn("1 current state fact(s)", session.context_stats())


if __name__ == "__main__":
    unittest.main()
