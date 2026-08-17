import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession, load_config, validate_ollama_options


class AssistantModelOptionsTests(unittest.TestCase):
    def config(self, *, policy="off", options=None):
        return AssistantConfig(
            "qwen3:8b", Path("persona/default.md"), Path("config/assistant_policy.md"),
            "personal", 8, 2, policy, "off", options or {},
        )

    def test_config_loads_valid_options_and_preserves_empty_default(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "assistant.json"
            path.write_text(json.dumps({"ollama_options": {"temperature": 0.4, "top_k": 40, "top_p": 0.9, "seed": 420}}), encoding="utf-8")
            self.assertEqual(load_config(path).ollama_options, {"temperature": 0.4, "top_k": 40, "top_p": 0.9, "seed": 420})
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(load_config(path).ollama_options, {})

    def test_config_loads_bounded_document_review_ttl(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "assistant.json"
            path.write_text(json.dumps({"document_review_ttl_seconds": 3600}), encoding="utf-8")
            self.assertEqual(load_config(path).document_review_ttl_seconds, 3600)
            path.write_text(json.dumps({"document_review_ttl_seconds": 0}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "document_review_ttl_seconds"):
                load_config(path)

    def test_options_reject_unknown_or_invalid_values(self):
        with self.assertRaises(ValueError):
            validate_ollama_options({"banana": 1})
        with self.assertRaises(ValueError):
            validate_ollama_options({"temperature": -0.1})
        with self.assertRaises(ValueError):
            validate_ollama_options({"seed": True})

    def test_options_reach_chat_and_proposal_calls(self):
        calls = []
        responses = iter([
            {"message": {"content": "answer"}},
            {"message": {"content": json.dumps({
                "store": True, "subject": "User", "memory_type": "preference",
                "summary": "Likes tea", "details": "", "importance": 0.8,
                "confidence": 0.9, "retention": "long_term",
            })}},
        ])
        options = {"temperature": 0.4, "top_k": 40, "seed": 420}
        session = AssistantSession(
            self.config(policy="conservative", options=options), "Persona",
            chat=lambda **kwargs: calls.append(kwargs) or next(responses),
            memory_loader=lambda **kwargs: [], policy="Policy",
        )
        self.assertEqual(session.respond("I like tea"), "answer")
        self.assertEqual([call["options"] for call in calls], [options, options])
        self.assertIn("Generation options: seed=420, temperature=0.4, top_k=40", session.context_stats())

    def test_options_reach_proposal_repair_call(self):
        calls = []
        repaired = {
            "store": False, "subject": "User", "memory_type": "preference",
            "summary": "No durable memory", "details": "", "importance": 0.1,
            "confidence": 0.1, "retention": "session",
        }
        responses = iter([
            {"message": {"content": "answer"}},
            {"message": {"content": "{}"}},
            {"message": {"content": json.dumps(repaired)}},
        ])
        options = {"temperature": 0.4, "seed": 420}
        session = AssistantSession(
            self.config(policy="conservative", options=options), "Persona",
            chat=lambda **kwargs: calls.append(kwargs) or next(responses),
            memory_loader=lambda **kwargs: [], policy="Policy",
        )
        self.assertEqual(session.respond("I like tea"), "answer")
        self.assertEqual([call["options"] for call in calls], [options, options, options])
    def test_legacy_config_object_does_not_send_empty_options(self):
        config = type("Config", (), {
            "chat_model": "qwen3:8b", "domain": "personal",
            "max_session_messages": 8, "max_memories": 0,
            "memory_policy": "off", "debug_level": "off",
        })()
        calls = []
        session = AssistantSession(config, "Persona", chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "answer"}}, memory_loader=lambda **kwargs: [], policy="Policy")
        session.respond("hello")
        self.assertNotIn("options", calls[0])


if __name__ == "__main__":
    unittest.main()
