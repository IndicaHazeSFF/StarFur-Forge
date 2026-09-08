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
        self.assertIn("proposal scope <id> <scope|type-derived>", rendered)
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

    def test_routing_help_returns_the_read_only_control(self):
        payload = detect_command_help("How do I inspect routing?")
        self.assertEqual(payload.intent, "routing_status")
        self.assertEqual(("routing status", "routing probe"), payload.commands)

    def test_tool_help_describes_only_local_inert_controls(self):
        payload = detect_command_help("How do I use tools?")
        self.assertEqual(payload.intent, "local_tool_controls")
        rendered = payload.render()
        self.assertIn("tool propose sandbox.run <JSON arguments>", rendered)
        self.assertIn("tool approve <TI-id>", rendered)
        self.assertIn("Execution remains disabled", rendered)
        self.assertIn("Shared chat/OpenWebUI/API requests cannot grant", rendered)

    def test_adventure_state_help_returns_exact_core_commands(self):
        payload = detect_command_help("How do I set story state?")
        self.assertEqual(payload.intent, "adventure_registry")
        rendered = payload.render()
        self.assertIn("adventure state", rendered)
        self.assertIn("adventure state set <key>: <value>", rendered)
        self.assertIn("current_location", rendered)

    def test_adventure_retraction_help_returns_exact_core_command(self):
        payload = detect_command_help("How do I retract an adventure event?")
        self.assertEqual(payload.intent, "adventure_registry")
        self.assertIn("adventure retract <AE-######>: <reason>", payload.render())

    def test_adventure_checkpoint_help_returns_exact_core_commands(self):
        payload = detect_command_help("How do I create an adventure checkpoint?")
        self.assertEqual(payload.intent, "adventure_registry")
        self.assertIn("adventure checkpoint <label>", payload.render())
        self.assertIn("adventure checkpoints", payload.render())
        self.assertIn("adventure checkpoint inspect <checkpoint-id|label>", payload.render())

    def test_fresh_restart_help_returns_exact_core_command(self):
        payload = detect_command_help("How do I start a fresh adventure?")
        self.assertEqual(payload.intent, "adventure_registry")
        self.assertIn("adventure restart fresh <new title>", payload.render())

    def test_established_restart_help_returns_exact_core_command(self):
        payload = detect_command_help("How do I restart an adventure from a checkpoint?")
        self.assertEqual(payload.intent, "adventure_registry")
        self.assertIn("adventure restart established <checkpoint-id|label>: <new title>", payload.render())

    def test_existing_adventure_start_help_returns_exact_core_command(self):
        payload = detect_command_help("How do I begin a saved adventure?")
        self.assertEqual(payload.intent, "adventure_registry")
        self.assertIn("adventure begin <title>", payload.render())

    def test_adventure_relationship_help_returns_exact_core_commands(self):
        payload = detect_command_help("How do I set adventure relationships?")
        self.assertEqual(payload.intent, "adventure_registry")
        rendered = payload.render()
        self.assertIn("adventure relationships", rendered)
        self.assertIn("adventure relationship set <character> <dimension>: <value>", rendered)
        self.assertIn("Vespera trust: cautious", rendered)

    def test_adventure_knowledge_help_returns_exact_core_commands(self):
        payload = detect_command_help("How do I set character knowledge?")
        self.assertEqual(payload.intent, "adventure_registry")
        rendered = payload.render()
        self.assertIn("adventure knowledge", rendered)
        self.assertIn("adventure knowledge set <character> <knows|believes|uncertain>: <fact>", rendered)
        self.assertIn("Vespera believes: the hatch is trapped", rendered)

    def test_persona_help_returns_read_only_command(self):

        payload = detect_command_help("How do I inspect the persona?")

        self.assertEqual(payload.intent, "persona_inspection")

        self.assertIn("persona inspect", payload.render())

    def test_resident_action_help_is_exact_and_provider_free(self):
        payload = detect_command_help("How do I change what Murr is doing?")

        self.assertEqual(payload.intent, "resident_action")
        rendered = payload.render()
        self.assertIn("resident status", rendered)
        self.assertIn("resident action <idle|resting|reading|working|waiting|chatting|adventuring>", rendered)
        self.assertIn("resident action clear", rendered)
        self.assertIn("does not start work", rendered)

    def test_persona_asset_help_exposes_only_the_read_only_command(self):
        payload = detect_command_help("How do I inspect persona assets?")

        self.assertEqual(payload.intent, "persona_assets")
        self.assertEqual(payload.commands, ("persona assets",))
        self.assertIn("does not expose paths", payload.render())



    def test_memory_help_returns_real_memory_commands(self):
        payload = detect_command_help("How do I search memories?")
        self.assertEqual(payload.intent, "memory_controls")
        rendered = payload.render()
        self.assertIn("memory search <query>", rendered)
        self.assertIn("memory inspect <id>", rendered)
        self.assertIn("memory scope <id> <scope|type-derived>", rendered)

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
