import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.capabilities import Capability, CapabilityManifest, CapabilityRegistry, build_core_capability_registry
from pipeline.assistant import AssistantSession


class CapabilityRegistryTests(unittest.TestCase):
    def test_core_manifest_is_stable_structured_and_covers_current_assistant_controls(self):
        manifest = build_core_capability_registry().build_manifest()
        payload = manifest.public_dict()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(
            [capability["id"] for capability in payload["capabilities"]],
            sorted(capability["id"] for capability in payload["capabilities"]),
        )
        self.assertIn("assistant.memory.proposals", [capability["id"] for capability in payload["capabilities"]])
        self.assertIn("assistant.roleplay_session", [capability["id"] for capability in payload["capabilities"]])
        self.assertEqual(manifest.get("assistant.model_selection").user_controls[0], "model list")
        self.assertIn("context stats", manifest.get("assistant.context_diagnostics").user_controls)
        self.assertEqual(manifest.get("assistant.memory.proposals").state, "requires_confirmation")
        self.assertEqual(manifest.fingerprint, build_core_capability_registry().build_manifest().fingerprint)



    def test_proposal_controls_include_required_ids(self):
        controls = build_core_capability_registry().build_manifest().get("assistant.memory.proposals").user_controls
        self.assertIn("proposal inspect <id>", controls)
        self.assertIn("proposal approve <id>", controls)
        self.assertIn("proposal reject <id>", controls)

    def test_registry_rejects_duplicate_or_invalid_definitions(self):
        capability = Capability(
            id="test.example",
            title="Example",
            category="test",
            summary="A test capability.",
            details="It exists to validate the registry.",
        )
        registry = CapabilityRegistry((capability,))

        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(capability)
        with self.assertRaisesRegex(ValueError, "Invalid capability id"):
            Capability("Not valid", "Title", "test", "Summary", "Details")
        with self.assertRaisesRegex(ValueError, "known"):
            registry.build_manifest(states={"missing.capability": "disabled"})

    def test_runtime_state_projection_is_immutable_and_does_not_change_definition(self):
        registry = CapabilityRegistry((
            Capability("test.example", "Example", "test", "Summary", "Details"),
        ))
        initial = registry.build_manifest()
        projected = registry.build_manifest(states={"test.example": "experimental"})

        self.assertEqual(initial.get("test.example").state, "available")
        self.assertEqual(projected.get("test.example").state, "experimental")
        self.assertNotEqual(initial.fingerprint, projected.fingerprint)

    def test_explicit_capability_questions_receive_core_context_but_normal_chat_does_not(self):
        config = type("Config", (), {
            "chat_model": "test", "domain": "personal", "max_session_messages": 4,
            "max_memories": 0, "memory_policy": "off", "debug_level": "off", "ollama_options": {},
        })()
        captured = []

        def chat(**kwargs):
            captured.append(kwargs["messages"])
            return {"message": {"content": "answer"}}

        session = AssistantSession(
            config,
            "Persona",
            policy="Engine policy",
            chat=chat,
            memory_loader=lambda **kwargs: [],
            capability_manifest=build_core_capability_registry().build_manifest(),
        )
        session.respond("What can you do?")
        capability_prompt = captured[-1][0]["content"]
        self.assertIn("CURRENT STARFUR CAPABILITIES", capability_prompt)
        self.assertIn("selected active assistant memories", capability_prompt)
        self.assertIn("not unrestricted access", capability_prompt)
        self.assertIn("Repeat registered user controls exactly", capability_prompt)
        self.assertIn("rather than inventing contents", capability_prompt)
        self.assertIn("Memory proposals and review", capability_prompt)
        self.assertIn("Runtime model selection", capability_prompt)
        self.assertIn("assistant.memory.proposals", session.last_turn_diagnostics["selected_capability_ids"])

        session.respond("Tell me a short joke.")
        self.assertNotIn("CURRENT STARFUR CAPABILITIES", captured[-1][0]["content"])
        self.assertEqual(session.last_turn_diagnostics["selected_capability_ids"], [])

    def test_named_capability_question_selects_only_matching_core_entry(self):
        manifest = build_core_capability_registry().build_manifest()
        selected = manifest.select_for_query("How do memory proposals work?")
        review_selected = manifest.select_for_query("How do I review your new memories?")

        self.assertEqual([capability.id for capability in selected], ["assistant.memory.proposals"])
        self.assertEqual([capability.id for capability in review_selected], ["assistant.memory.proposals"])
        roleplay_selected = manifest.select_for_query("How do I start roleplay?")
        self.assertEqual([capability.id for capability in roleplay_selected], ["assistant.roleplay_session"])
    def test_manifest_rejects_unstable_order_and_duplicate_ids(self):
        first = Capability("test.a", "A", "test", "Summary", "Details")
        second = Capability("test.b", "B", "test", "Summary", "Details")

        with self.assertRaisesRegex(ValueError, "ordered"):
            CapabilityManifest(1, (second, first))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            CapabilityManifest(1, (first, first))


if __name__ == "__main__":
    unittest.main()
