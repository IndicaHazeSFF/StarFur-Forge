import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.command_help import detect_command_help


class CommandHelpTests(unittest.TestCase):
    def test_proposal_help_is_exact_and_id_aware(self):
        payload = detect_command_help("How do I view new memory proposals? And how do I approve proposals?")
        self.assertEqual(payload.intent, "proposal_review")
        rendered = payload.render()
        self.assertIn("proposal list", rendered)
        self.assertIn("proposal inspect <id>", rendered)
        self.assertIn("proposal approve <id>", rendered)
        self.assertIn("proposal reject <id>", rendered)
        self.assertIn("approve all", rendered)

    def test_context_help_returns_only_the_real_command(self):
        payload = detect_command_help("How do I show context diagnostics?")
        self.assertEqual(payload.intent, "context_diagnostics")
        self.assertIn("context stats", payload.render())

    def test_model_help_returns_real_model_commands(self):
        payload = detect_command_help("How do I select a model?")
        self.assertEqual(payload.intent, "model_selection")
        rendered = payload.render()
        self.assertIn("model list", rendered)
        self.assertIn("model current", rendered)
        self.assertIn("model use <model-name>", rendered)

    def test_persona_help_returns_read_only_command(self):

        payload = detect_command_help("How do I inspect the persona?")

        self.assertEqual(payload.intent, "persona_inspection")

        self.assertIn("persona inspect", payload.render())



    def test_memory_help_returns_real_memory_commands(self):
        payload = detect_command_help("How do I search memories?")
        self.assertEqual(payload.intent, "memory_controls")
        rendered = payload.render()
        self.assertIn("memory search <query>", rendered)
        self.assertIn("memory inspect <id>", rendered)

    def test_natural_memory_help_variants_are_core_owned(self):
        for query in (
            "How do I make you forget a memory?",
            "How do I remove a memory?",
            "How do I see pending memories for approval?",
        ):
            with self.subTest(query=query):
                payload = detect_command_help(query)
                self.assertIsNotNone(payload)
                expected = "memory_controls" if "forget" in query.lower() or "remove" in query.lower() else "proposal_review"
                self.assertEqual(payload.intent, expected)
                self.assertNotIn("reset our conversation", payload.render())

    def test_normal_conversation_is_not_intercepted(self):
        self.assertIsNone(detect_command_help("Murr, what can you do?"))
        self.assertIsNone(detect_command_help("What do you remember about rice?"))

    def test_alias_normalization_is_deterministic(self):
        first = detect_command_help("How can I review your new memories?").render()
        second = detect_command_help("how can i review your new memories").render()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()