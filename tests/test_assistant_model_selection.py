import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession


class AssistantModelSelectionTests(unittest.TestCase):
    def config(self, *, policy="off"):
        return AssistantConfig(
            "qwen3:8b", Path("persona/default.md"), Path("config/assistant_policy.md"),
            "personal", 8, 2, policy, "off",
        )

    def test_model_list_is_stable_marks_active_and_does_not_call_chat(self):
        chat_calls = []
        session = AssistantSession(
            self.config(), "Persona", chat=lambda **kwargs: chat_calls.append(kwargs),
            memory_loader=lambda **kwargs: [], policy="Policy",
            model_lister=lambda: {"models": [{"model": "zeta:latest"}, {"name": "Alpha:1b"}, {"model": "qwen3:8b"}]},
        )
        listed = session.respond("model list")
        self.assertEqual(
            listed,
            "Installed Ollama models:\n  Alpha:1b\n* qwen3:8b (active)\n  zeta:latest",
        )
        self.assertEqual(session.respond("model current"), "Active model: qwen3:8b")
        self.assertEqual(session.respond("list models"), listed)
        self.assertEqual(chat_calls, [])
        self.assertEqual(session.messages, [])
        self.assertEqual(session.proposals, [])

    def test_switch_routes_chat_and_proposal_to_new_active_model(self):
        calls = []
        responses = iter([
            {"message": {"content": "answer"}},
            {"message": {"content": '{"store": true, "subject": "User", "memory_type": "preference", "summary": "Likes tea", "details": "", "importance": 0.8, "confidence": 0.9, "retention": "long_term"}'}},
        ])
        session = AssistantSession(
            self.config(policy="conservative"), "Persona",
            chat=lambda **kwargs: calls.append(kwargs) or next(responses),
            memory_loader=lambda **kwargs: [], policy="Policy",
            model_lister=lambda: {"models": [{"model": "qwen3:8b"}, {"model": "llama3.1:8b"}]},
            proposal_creator=lambda proposal, **kwargs: {"proposal_id": 9, "action": "created"},
        )
        self.assertEqual(session.respond("model use LLAMA3.1:8B"), "Active model set to: llama3.1:8b")
        self.assertEqual(session.respond("I like tea"), "answer")
        self.assertEqual([call["model"] for call in calls], ["llama3.1:8b", "llama3.1:8b"])
        self.assertIn("Model: llama3.1:8b", session.context_stats())
        self.assertEqual(session.config.chat_model, "qwen3:8b")

    def test_context_stats_keeps_model_used_for_previous_turn(self):
        calls = []
        session = AssistantSession(
            self.config(), "Persona", chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: [], policy="Policy",
            model_lister=lambda: {"models": [{"model": "qwen3:8b"}, {"model": "other:latest"}]},
        )
        session.respond("hello")
        self.assertEqual(session.respond("model use other:latest"), "Active model set to: other:latest")
        self.assertIn("Model: qwen3:8b", session.respond("context stats"))
        session.respond("hello again")
        self.assertEqual([call["model"] for call in calls], ["qwen3:8b", "other:latest"])
        self.assertIn("Model: other:latest", session.context_stats())

    def test_unknown_unavailable_empty_and_repeated_selection_are_safe(self):
        base = self.config()
        session = AssistantSession(
            base, "Persona", chat=lambda **kwargs: {"message": {"content": "unused"}},
            memory_loader=lambda **kwargs: [], policy="Policy",
            model_lister=lambda: {"models": [{"model": "qwen3:8b"}]},
        )
        self.assertEqual(session.respond("model use missing:1b"), "Model not installed: missing:1b")
        self.assertEqual(session.active_model, "qwen3:8b")
        self.assertEqual(session.respond("model use qwen3:8b"), "Model is already active: qwen3:8b")
        self.assertEqual(session.messages, [])
        self.assertEqual(session.proposals, [])

        empty = AssistantSession(base, "Persona", chat=lambda **kwargs: None, memory_loader=lambda **kwargs: [], policy="Policy", model_lister=lambda: {"models": []})
        self.assertEqual(empty.respond("model list"), "No Ollama models are installed.")
        self.assertEqual(empty.respond("model use qwen3:8b"), "Model not installed: qwen3:8b")

        unavailable = AssistantSession(base, "Persona", chat=lambda **kwargs: None, memory_loader=lambda **kwargs: [], policy="Policy", model_lister=lambda: (_ for _ in ()).throw(ConnectionError("offline")))
        self.assertEqual(unavailable.respond("model list"), "Unable to list Ollama models: offline")


if __name__ == "__main__":
    unittest.main()