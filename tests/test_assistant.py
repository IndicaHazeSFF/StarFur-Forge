from pathlib import Path
import json
import sys
import tempfile
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantSession, load_config, load_persona


class AssistantTests(unittest.TestCase):
    def test_config_and_persona_are_file_backed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            persona = root / "persona.md"
            persona.write_text("A test persona.", encoding="utf-8")
            config = root / "assistant.json"
            config.write_text(json.dumps({
                "chat_model": "test-model",
                "persona_path": str(persona),
                "domain": "personal",
                "max_session_messages": 4,
                "max_memories": 2,
            }), encoding="utf-8")
            loaded = load_config(config)
            self.assertEqual(loaded.chat_model, "test-model")
            self.assertEqual(load_persona(loaded.persona_path), "A test persona.")

    def test_session_context_is_bounded_and_reads_active_memories(self):
        calls = []
        def fake_chat(**kwargs):
            calls.append(kwargs)
            return {"message": {"content": "response"}}
        config = type("Config", (), {
            "chat_model": "test-model",
            "domain": "personal",
            "max_session_messages": 4,
            "max_memories": 2,
        })()
        session = AssistantSession(
            config,
            "Persona text",
            chat=fake_chat,
            memory_loader=lambda **kwargs: [{"summary": "Likes foxes"}],
        )
        for text in ("one", "two", "three"):
            session.respond(text)
        self.assertLessEqual(len(session.messages), 4)
        self.assertIn("Persona text", calls[-1]["messages"][0]["content"])
        self.assertIn("Likes foxes", calls[-1]["messages"][0]["content"])
        self.assertEqual(calls[-1]["model"], "test-model")

    def test_failed_model_call_does_not_append_session_state(self):
        def failing_chat(**kwargs):
            raise RuntimeError("offline")
        config = type("Config", (), {
            "chat_model": "test-model",
            "domain": "personal",
            "max_session_messages": 4,
            "max_memories": 0,
        })()
        session = AssistantSession(config, "Persona", chat=failing_chat, memory_loader=lambda **kwargs: [])
        with self.assertRaises(RuntimeError):
            session.respond("hello")
        self.assertEqual(session.messages, [])

    def test_empty_model_output_is_not_committed(self):
        config = type("Config", (), {
            "chat_model": "test-model",
            "domain": "personal",
            "max_session_messages": 4,
            "max_memories": 0,
        })()
        session = AssistantSession(config, "Persona", chat=lambda **kwargs: {"message": {"content": ""}}, memory_loader=lambda **kwargs: [])
        with self.assertRaises(RuntimeError):
            session.respond("hello")
        self.assertEqual(session.messages, [])


if __name__ == "__main__":
    unittest.main()
