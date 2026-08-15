import sys
import types
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.persona_visibility import (
    EXPLICIT_MEMORY_SCOPES,
    MEMORY_SCOPES,
    SharedMemoryVisibilityPolicy,
    evaluate_shared_memory_visibility,
    evaluate_shared_memory_scope_visibility,
    memory_scope_for_record,
    memory_scope_for_type,
)
from pipeline.persona_registry import load_persona_packages
from pipeline.assistant import AssistantConfig, AssistantSession


class SharedMemoryVisibilityPolicyTests(unittest.TestCase):
    def test_default_policy_is_backward_compatible(self):
        decision = evaluate_shared_memory_visibility(SharedMemoryVisibilityPolicy("Murr"), 0.0)

        self.assertEqual("murr", decision.persona_id)
        self.assertTrue(decision.visible)
        self.assertEqual(0.0, decision.knowledge_confidence)
        self.assertIn("meets", decision.reason)

    def test_threshold_is_inclusive_and_hides_lower_confidence(self):
        policy = SharedMemoryVisibilityPolicy("nova", 0.70)
        at_threshold = evaluate_shared_memory_visibility(policy, 0.70)
        below_threshold = evaluate_shared_memory_visibility(policy, 0.699)

        self.assertTrue(at_threshold.visible)
        self.assertEqual(0.70, at_threshold.knowledge_confidence)
        self.assertFalse(below_threshold.visible)
        self.assertIsNone(below_threshold.knowledge_confidence)
        self.assertIn("below", below_threshold.reason)

    def test_public_result_is_deterministic_and_explainable(self):
        policy = SharedMemoryVisibilityPolicy("neutral", 0.80)
        first = evaluate_shared_memory_visibility(policy, 0.95).public_dict()
        second = evaluate_shared_memory_visibility(policy, 0.95).public_dict()

        self.assertEqual(first, second)
        self.assertEqual("source confidence 0.950 meets persona threshold 0.800", first["reason"])
        self.assertEqual(0.95, first["knowledge_confidence"])

    def test_invalid_policy_and_confidence_values_are_rejected(self):
        with self.assertRaises(ValueError):
            SharedMemoryVisibilityPolicy("not a persona")
        with self.assertRaises(ValueError):
            SharedMemoryVisibilityPolicy("murr", 1.01)
        with self.assertRaises(ValueError):
            evaluate_shared_memory_visibility(SharedMemoryVisibilityPolicy("murr"), -0.1)
        with self.assertRaises(TypeError):
            evaluate_shared_memory_visibility(SharedMemoryVisibilityPolicy("murr"), True)
        with self.assertRaises(TypeError):
            SharedMemoryVisibilityPolicy("murr", allowed_memory_scopes="project")

    def test_existing_memory_types_have_conservative_scope_mapping(self):
        self.assertEqual(("personal", "preference", "project", "relationship", "roleplay", "routine"), MEMORY_SCOPES)
        self.assertIn("roleplay", EXPLICIT_MEMORY_SCOPES)
        self.assertEqual("project", memory_scope_for_type("project_context"))
        self.assertEqual("relationship", memory_scope_for_type("relationship_context"))
        self.assertIsNone(memory_scope_for_type("roleplay"))
        self.assertIsNone(memory_scope_for_type(None))

    def test_explicit_scope_overrides_type_fallback_without_prose_inference(self):
        self.assertEqual("roleplay", memory_scope_for_record("preference", "roleplay"))
        self.assertEqual("preference", memory_scope_for_record("preference"))
        policy = SharedMemoryVisibilityPolicy("murr", allowed_memory_scopes=("roleplay",))
        self.assertTrue(evaluate_shared_memory_scope_visibility(policy, "preference", "roleplay").visible)
        self.assertFalse(evaluate_shared_memory_scope_visibility(policy, "preference").visible)
        with self.assertRaises(ValueError):
            memory_scope_for_record("preference", "sensitive")

    def test_scope_decision_is_unrestricted_by_default_and_fail_closed_when_configured(self):
        unrestricted = SharedMemoryVisibilityPolicy("murr")
        restricted = SharedMemoryVisibilityPolicy("nova", allowed_memory_scopes=("project", "routine"))

        self.assertTrue(evaluate_shared_memory_scope_visibility(unrestricted, "personal_fact").visible)
        allowed = evaluate_shared_memory_scope_visibility(restricted, "project_context")
        rejected = evaluate_shared_memory_scope_visibility(restricted, "relationship_context")
        unmapped = evaluate_shared_memory_scope_visibility(restricted, "future_type")
        self.assertTrue(allowed.visible)
        self.assertEqual("project", allowed.memory_scope)
        self.assertFalse(rejected.visible)
        self.assertIn("not allowed", rejected.reason)
        self.assertFalse(unmapped.visible)
        self.assertIn("no approved scope mapping", unmapped.reason)

    def test_persona_package_configuration_carries_a_validated_threshold(self):
        with self.subTest("configured threshold"):
            registry = load_persona_packages(
                Path(__file__).resolve().parents[1] / "persona" / "default.md",
                [{
                    "persona_id": "murr",
                    "display_name": "Murr",
                    "persona_path": Path(__file__).resolve().parents[1] / "persona" / "default.md",
                    "minimum_shared_memory_confidence": 0.72,
                    "allowed_memory_scopes": ["project", "routine"],
                }],
            )
            policy = registry.get("murr").shared_memory_visibility_policy
            self.assertEqual(0.72, policy.minimum_shared_memory_confidence)
            self.assertEqual(("project", "routine"), policy.allowed_memory_scopes)
        with self.subTest("invalid configuration"):
            with self.assertRaises(ValueError):
                load_persona_packages(
                    Path(__file__).resolve().parents[1] / "persona" / "default.md",
                    [{
                        "persona_id": "murr",
                        "display_name": "Murr",
                        "persona_path": Path(__file__).resolve().parents[1] / "persona" / "default.md",
                        "minimum_shared_memory_confidence": 1.1,
                    }],
                )

    def test_active_persona_filters_shared_retrieval_and_exposes_bounded_diagnostics(self):
        root = Path(__file__).resolve().parents[1]
        specs = [{
            "persona_id": "murr",
            "display_name": "Murr",
            "persona_path": root / "persona" / "default.md",
            "minimum_shared_memory_confidence": 0.8,
        }]
        registry = load_persona_packages(root / "persona" / "default.md", specs)
        model_calls = []
        session = AssistantSession(
            AssistantConfig("test-model", root / "persona" / "default.md", root / "config" / "assistant_policy.md", "personal", 4, 4, "off", "off"),
            registry.get("murr"),
            persona_registry=registry,
            chat=lambda **kwargs: model_calls.append(kwargs) or {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: [
                {"id": 1, "summary": "Allowed fact", "confidence": 0.9},
                {"id": 2, "summary": "Hidden fact", "confidence": 0.6},
            ],
            policy="Policy",
        )

        self.assertEqual("answer", session.respond("recall my facts"))
        self.assertIn("Allowed fact", model_calls[-1]["messages"][0]["content"])
        self.assertNotIn("Hidden fact", model_calls[-1]["messages"][0]["content"])
        self.assertEqual([1], session.last_memory_ids)
        stats = session.context_stats()
        self.assertIn("Shared-memory visibility: murr, threshold 0.80; 1/2 visible", stats)
        self.assertIn("Hidden memory IDs: M-002", stats)
        self.assertIn("M-002 confidence=0.600 hidden", stats)
        self.assertEqual("no_match", session.explain_memory("hidden")["status"])

    def test_active_persona_scope_filter_preserves_only_allowed_memory_types(self):
        root = Path(__file__).resolve().parents[1]
        specs = [{
            "persona_id": "nova",
            "display_name": "Nova",
            "persona_path": root / "persona" / "nova.md",
            "allowed_memory_scopes": ["project"],
        }]
        registry = load_persona_packages(root / "persona" / "nova.md", specs)
        model_calls = []
        session = AssistantSession(
            AssistantConfig("test-model", root / "persona" / "nova.md", root / "config" / "assistant_policy.md", "personal", 4, 4, "off", "off"),
            registry.get("nova"),
            persona_registry=registry,
            chat=lambda **kwargs: model_calls.append(kwargs) or {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: [
                {"id": 1, "summary": "Project fact", "memory_type": "project_context", "confidence": 0.9},
                {"id": 2, "summary": "Personal hardware", "memory_type": "personal_fact", "confidence": 1.0},
            ],
            policy="Policy",
        )

        session.respond("recall information")
        self.assertIn("Project fact", model_calls[-1]["messages"][0]["content"])
        self.assertNotIn("Personal hardware", model_calls[-1]["messages"][0]["content"])
        self.assertEqual([1], session.last_memory_ids)
        stats = session.context_stats()
        self.assertIn("Hidden memory IDs: M-002", stats)
        self.assertIn("scope: personal (denied)", stats)
        self.assertEqual("no_match", session.explain_memory("hardware")["status"])

    def test_active_persona_uses_explicit_scope_before_type_fallback(self):
        root = Path(__file__).resolve().parents[1]
        specs = [{
            "persona_id": "murr",
            "display_name": "Murr",
            "persona_path": root / "persona" / "default.md",
            "allowed_memory_scopes": ["roleplay"],
        }]
        registry = load_persona_packages(root / "persona" / "default.md", specs)
        model_calls = []
        session = AssistantSession(
            AssistantConfig("test-model", root / "persona" / "default.md", root / "config" / "assistant_policy.md", "personal", 4, 4, "off", "off"),
            registry.get("murr"),
            persona_registry=registry,
            chat=lambda **kwargs: model_calls.append(kwargs) or {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: [
                {"id": 1, "summary": "Explicit story memory", "memory_type": "preference", "visibility_scope": "roleplay", "confidence": 0.9},
                {"id": 2, "summary": "Ordinary preference", "memory_type": "preference", "confidence": 0.9},
            ],
            policy="Policy",
        )

        session.respond("recall information")
        self.assertIn("Explicit story memory", model_calls[-1]["messages"][0]["content"])
        self.assertNotIn("Ordinary preference", model_calls[-1]["messages"][0]["content"])
        self.assertIn("scope: roleplay (allowed)", session.context_stats())
