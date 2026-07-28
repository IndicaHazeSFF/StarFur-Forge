from pathlib import Path
import json
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantSession, load_config, load_persona, load_policy
from pipeline import assistant as assistant_module


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

    def test_explicit_commands_use_crud_and_soft_forget(self):
        created = []
        updated = []
        config = type("Config", (), {"chat_model": "test", "domain": "personal", "max_session_messages": 4, "max_memories": 2, "memory_policy": "off"})()
        session = AssistantSession(config, "Persona", chat=lambda **kwargs: {"message": {"content": "unused"}}, memory_creator=lambda **kwargs: created.append(kwargs) or 7, memory_searcher=lambda *args, **kwargs: [{"id": 7}], memory_updater=lambda *args, **kwargs: updated.append((args, kwargs)))
        self.assertIn("Remembered", session.respond("remember this: I prefer foxes"))
        self.assertEqual(created[0]["source"], "explicit:user")
        self.assertIn("Forgotten", session.respond("forget this: foxes"))
        self.assertEqual(updated[0][1]["status"], "forgotten")

    def test_proposals_are_validated_and_not_persisted(self):
        calls = []
        config = type("Config", (), {"chat_model": "test", "domain": "personal", "max_session_messages": 4, "max_memories": 0, "memory_policy": "conservative", "debug_level": "verbose"})()
        def fake_chat(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {"message": {"content": "answer"}}
            return {"message": {"content": "{\"store\": true, \"subject\": \"User\", \"memory_type\": \"preference\", \"summary\": \"Likes foxes\", \"importance\": 0.8, \"confidence\": 0.9, \"retention\": \"long_term\", \"domain\": \"personal\", \"source\": \"conversation\"}"}}
        creator = lambda **kwargs: (_ for _ in ()).throw(AssertionError("automatic persistence"))
        session = AssistantSession(config, "Persona", chat=fake_chat, memory_creator=creator, memory_loader=lambda **kwargs: [])
        self.assertEqual(session.respond("I really like foxes"), "answer")
        self.assertEqual(len(session.proposals), 1)
        self.assertTrue(session.proposals[0]["store"])
        self.assertEqual(session.proposals[0]["source"], "assistant_turn_proposal")
        self.assertEqual(session.proposals[0]["domain"], "personal")
        events = [event["event"] for event in session.trace.events]
        self.assertIn("proposal_request", events)
        request = next(event for event in session.trace.events if event["event"] == "proposal_request")
        self.assertIn("USER FACTUAL INPUT", request["messages"][1]["content"])
        self.assertIn("project_context", request["messages"][0]["content"])
        self.assertIn("proposal_response", events)
        self.assertIn("proposal_validation", events)

    def test_invalid_proposal_does_not_break_turn(self):
        config = type("Config", (), {"chat_model": "test", "domain": "personal", "max_session_messages": 4, "max_memories": 0, "memory_policy": "conservative", "debug_level": "verbose"})()
        calls = iter([
            {"message": {"content": "answer"}},
            {"message": {"content": "{\"store\": true, \"subject\": \"User\", \"memory_type\": \"bogus\", \"summary\": \"bad\", \"importance\": 1, \"confidence\": 1, \"retention\": \"long_term\", \"domain\": \"personal\", \"source\": \"test\"}"}},
        ])
        session = AssistantSession(config, "Persona", chat=lambda **kwargs: next(calls), memory_loader=lambda **kwargs: [])
        self.assertEqual(session.respond("hello"), "answer")
        self.assertEqual(len(session.proposals), 0)
        self.assertIn("proposal_error", [event["event"] for event in session.trace.events])

    def test_debug_trace_records_memory_context_and_model(self):
        config = type("Config", (), {"chat_model": "test", "domain": "personal", "max_session_messages": 4, "max_memories": 1, "memory_policy": "off", "debug_level": "verbose"})()
        session = AssistantSession(
            config,
            "Persona",
            chat=lambda **kwargs: {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: [{"summary": "Murr project"}],
        )
        session.respond("What am I building?")
        events = [event["event"] for event in session.trace.events]
        self.assertIn("memory_lookup", events)
        self.assertIn("context_assembly", events)
        self.assertIn("model_request", events)
        self.assertIn("model_response", events)
        rendered = session.trace.render()
        self.assertIn("Murr project", rendered)
        self.assertIn("What am I building?", rendered)

    def test_debug_off_emits_no_trace(self):
        config = type("Config", (), {"chat_model": "test", "domain": "personal", "max_session_messages": 4, "max_memories": 0, "memory_policy": "off"})()
        session = AssistantSession(config, "Persona", chat=lambda **kwargs: {"message": {"content": "answer"}}, memory_loader=lambda **kwargs: [])
        session.respond("hello")
        self.assertEqual(session.trace.render(), "")

    def test_engine_policy_is_separate_from_persona_and_grounding_is_explicit(self):
        config = type("Config", (), {"chat_model": "test", "domain": "personal", "max_session_messages": 4, "max_memories": 1, "memory_policy": "off", "debug_level": "verbose"})()
        session = AssistantSession(
            config,
            "Persona-only style",
            policy="Answer directly. Retrieved memory is factual context.",
            chat=lambda **kwargs: {"message": {"content": "grounded answer"}},
            memory_loader=lambda **kwargs: [{"summary": "Building a two-dimensional memory system"}],
        )
        session.respond("What am I building?")
        prompt = session.trace.events[2]["messages"][0]["content"]
        self.assertIn("Persona-only style", prompt)
        self.assertIn("Answer directly", prompt)
        self.assertIn("Building a two-dimensional memory system", prompt)

    def test_policy_allows_persona_after_grounded_answer(self):
        policy = load_policy()
        self.assertIn("Answer the user's actual question accurately and directly.", policy)
        self.assertIn("preserve the persona's natural warmth", policy)
        self.assertIn("must not replace, contradict, bury, or overwhelm", policy)

    def test_proposal_notice_only_appears_for_new_proposal(self):
        class FakeSession:
            def __init__(self, *args, **kwargs):
                self.proposals = [{"store": True, "summary": "old"}]
                self.trace = type("Trace", (), {"emit": lambda self, output: None})()
            def respond(self, text):
                return "ok"
        config = type("Config", (), {"persona_path": Path("persona/default.md"), "policy_path": Path("config/assistant_policy.md")})()
        inputs = iter(["proposal list", "quit"])
        output = []
        with patch.object(assistant_module, "load_config", return_value=config), patch.object(assistant_module, "load_persona", return_value="persona"), patch.object(assistant_module, "load_policy", return_value="policy"), patch.object(assistant_module, "AssistantSession", FakeSession):
            assistant_module.run_interactive(input_fn=lambda prompt: next(inputs), output_fn=output.append)
        self.assertFalse(any("Memory proposal available" in line for line in output))

if __name__ == "__main__":
    unittest.main()
