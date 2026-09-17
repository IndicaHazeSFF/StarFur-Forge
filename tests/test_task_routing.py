import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.task_profiles import TaskProfile, TaskProfiles
from pipeline.task_routing import (
    ProviderRouteRegistry,
    ProviderRouteStatus,
    TaskRoutePlanner,
    TaskRoutePlanningError,
    provider_route_status_from_runtime,
    task_required_capability,
)


class TaskRoutingTests(unittest.TestCase):
    def _planner(self, profiles, providers):
        return TaskRoutePlanner(TaskProfiles(profiles), ProviderRouteRegistry(providers))

    def test_plans_primary_routable_profile_without_provider_execution(self):
        planner = self._planner(
            {"assistant_chat": TaskProfile("assistant_chat", provider="Ollama", model="qwen3:8b")},
            {"ollama": ProviderRouteStatus("ollama", "unprobed")},
        )
        decision = planner.plan("assistant_chat", default_model="default", default_provider_id="ollama")
        self.assertEqual("routable", decision.status)
        self.assertEqual(0, decision.selected_index)
        self.assertEqual("ollama", decision.selected.provider_id)
        self.assertEqual("unprobed", decision.selected.provider_status)
        self.assertFalse(decision.public_dict()["fallback_used"])

    def test_public_route_candidates_expose_only_bounded_model_budgets(self):
        planner = self._planner(
            {"assistant_chat": TaskProfile(
                "assistant_chat", provider="ollama", model="qwen3:8b",
                context_size=4096, max_output_tokens=512,
            )},
            {"ollama": ProviderRouteStatus("ollama", "available")},
        )

        candidate = planner.plan(
            "assistant_chat", default_model="default", default_provider_id="ollama",
        ).public_dict()["candidates"][0]

        self.assertEqual("qwen3:8b", candidate["model"])
        self.assertEqual(4096, candidate["context_size"])
        self.assertEqual(512, candidate["max_output_tokens"])
        self.assertNotIn("messages", candidate)
        self.assertNotIn("prompt", candidate)

    def test_public_route_budget_values_are_clamped_to_safe_bounds(self):
        planner = self._planner(
            {"assistant_chat": TaskProfile(
                "assistant_chat", provider="ollama", model="qwen3:8b",
                context_size=2_000_000, max_output_tokens=2_000_001,
            )},
            {"ollama": ProviderRouteStatus("ollama", "available")},
        )

        candidate = planner.plan(
            "assistant_chat", default_model="default", default_provider_id="ollama",
        ).public_dict()["candidates"][0]

        self.assertEqual(1_000_000, candidate["context_size"])
        self.assertEqual(1_000_000, candidate["max_output_tokens"])

    def test_uses_configured_fallback_when_primary_provider_is_unavailable(self):
        planner = self._planner(
            {
                "document_annotation": TaskProfile(
                    "document_annotation", provider="ollama", fallback_task="assistant_chat",
                ),
                "assistant_chat": TaskProfile("assistant_chat", provider="hosted"),
            },
            {
                "ollama": ProviderRouteStatus("ollama", "unavailable"),
                "hosted": ProviderRouteStatus("hosted", "available"),
            },
        )
        decision = planner.plan("document_annotation", default_model="default", default_provider_id="ollama")
        self.assertEqual("routable", decision.status)
        self.assertEqual(1, decision.selected_index)
        self.assertEqual("assistant_chat", decision.selected.task_id)
        self.assertTrue(decision.public_dict()["fallback_used"])
        self.assertEqual("provider_unavailable", decision.candidates[0].reason)

    def test_rejects_cycles_and_unconfigured_fallbacks_without_guessing(self):
        cyclic = self._planner(
            {
                "assistant_chat": TaskProfile("assistant_chat", fallback_task="document_annotation"),
                "document_annotation": TaskProfile("document_annotation", fallback_task="assistant_chat"),
            },
            {"ollama": ProviderRouteStatus("ollama", "available")},
        )
        with self.assertRaisesRegex(TaskRoutePlanningError, "loop"):
            cyclic.plan("assistant_chat", default_model="default", default_provider_id="ollama")

        dangling = self._planner(
            {"assistant_chat": TaskProfile("assistant_chat", fallback_task="coding")},
            {"ollama": ProviderRouteStatus("ollama", "available")},
        )
        with self.assertRaisesRegex(TaskRoutePlanningError, "not configured"):
            dangling.plan("assistant_chat", default_model="default", default_provider_id="ollama")

    def test_unavailable_or_capability_incompatible_routes_fail_closed(self):
        planner = self._planner(
            {"assistant_chat": TaskProfile("assistant_chat", provider="image")},
            {"image": ProviderRouteStatus("image", "available", frozenset({"image_generation"}))},
        )
        decision = planner.plan("assistant_chat", default_model="default", default_provider_id="image")
        self.assertEqual("unavailable", decision.status)
        self.assertIsNone(decision.selected)
        self.assertEqual("capability_unsupported", decision.candidates[0].reason)

    def test_runtime_status_mapping_never_claims_unprobed_or_missing_provider_is_healthy(self):
        self.assertEqual(
            "unprobed",
            provider_route_status_from_runtime(
                "ollama", configured=True, health_status="not_probed",
            ).status,
        )
        self.assertEqual(
            "unavailable",
            provider_route_status_from_runtime(
                "ollama", configured=False, health_status="healthy",
            ).status,
        )
        self.assertEqual(
            "unprobed",
            provider_route_status_from_runtime(
                "ollama", configured=True, health_status="not_probed", lifecycle_state="error",
            ).status,
        )
        self.assertEqual(
            "unprobed",
            provider_route_status_from_runtime(
                "ollama", configured=True, health_status="unsupported",
            ).status,
        )

    def test_task_capability_is_core_owned_and_unknown_tasks_are_not_guessed(self):
        self.assertEqual("chat", task_required_capability("adventure_turn_generation"))
        self.assertEqual("chat", task_required_capability("research_claim_generation"))
        self.assertEqual("vision", task_required_capability("vision"))
        self.assertEqual("image_generation", task_required_capability("image_generation"))
        with self.assertRaisesRegex(TaskRoutePlanningError, "no provider-routing capability"):
            task_required_capability("retrieval_evaluation")


if __name__ == "__main__":
    unittest.main()
