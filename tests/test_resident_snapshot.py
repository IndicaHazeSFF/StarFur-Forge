import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.resident_snapshot import ResidentSnapshot, derive_resident_activity


class ResidentSnapshotTests(unittest.TestCase):
    def test_activity_priority_is_deterministic_and_provider_safe(self):
        self.assertEqual(derive_resident_activity(
            provider_lifecycle={"state": "streaming"}, provider_configured=True,
            adventure_turn_active=True, ordinary_candidate_count=1,
            mutation_candidate_count=0, roleplay_active=True, adventure_mounted=True,
        ), "streaming")
        self.assertEqual(derive_resident_activity(
            provider_lifecycle={"state": "idle"}, provider_configured=True,
            adventure_turn_active=True, ordinary_candidate_count=1,
            mutation_candidate_count=0, roleplay_active=True, adventure_mounted=True,
        ), "reviewing_candidates")
        self.assertEqual(derive_resident_activity(
            provider_lifecycle=None, provider_configured=False,
            adventure_turn_active=False, ordinary_candidate_count=0,
            mutation_candidate_count=0, roleplay_active=False, adventure_mounted=False,
        ), "provider_unavailable")
        self.assertEqual(derive_resident_activity(
            provider_lifecycle=None, provider_configured=False,
            adventure_turn_active=False, ordinary_candidate_count=0,
            mutation_candidate_count=0, roleplay_active=False, adventure_mounted=False,
            explicit_resident_action=True,
        ), "idle")

    def test_public_payload_excludes_sensitive_and_unbounded_inputs(self):
        snapshot = ResidentSnapshot(
            conversation_id="dashboard-a",
            persona={"persona_id": "murr", "display_name": "Murr", "resident_action": {"kind": "idle"}, "static_identity": "secret prompt"},
            provider={"name": "Ollama", "configured": True, "health": "ready", "raw_payload": "secret"},
            lifecycle={"state": "idle", "error": "private failure", "transition_count": 3},
            system_metrics={"status": "partial", "platform": "linux", "cpu": {"logical_cores": 8, "secret": "no"}, "memory": {"total_bytes": 10, "available_bytes": 5}, "storage": {}, "gpu": {"status": "unavailable", "raw": "no"}},
            capability_ids=("assistant.chat",),
            adventure={"mounted": True, "title": "Quiet Ember", "hidden_resource": "ammo=9"},
            roleplay={"active": True, "title": "Quiet Ember"},
            turn={"active": True, "staged_count": 2, "drafts": ["private"], "last_task_routes": [{
                "requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat",
                "provider": "ollama", "model": "qwen3:8b", "fallback_used": False, "outcome": "submitted",
                "raw_provider_output": "private",
            }, {
                "requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat",
                "provider": "ollama", "model": "qwen3:8b", "fallback_used": False,
                "outcome": "provider_concurrency_busy",
            }, {"requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat", "provider": "ollama", "model": "x" * 257, "fallback_used": False, "outcome": "submitted"}]},
            candidates={"ordinary_count": 1, "mutation_count": 0, "body": "private"},
            routing={
                "configured_task_count": 4, "routable_task_count": 3,
                "unavailable_task_count": 1, "tasks": {"private": "no"},
                "raw_provider_payload": "private",
            },
            focus_mode={"enabled": True, "task_names": ["private"], "monitoring": "private"},
            sandbox_execution={
                "schema_version": 1, "configured": True, "host_status": "unsupported",
                "supervisor_status": "unavailable", "execution_status": "unavailable",
                "reason": "host_unsupported", "endpoint": "private-pipe",
                "principal": "private-user", "key_id": "private-key",
            },
            tool_activity={
                "schema_version": 1, "total_count": 2,
                "pending_review_count": 1, "approved_count": 0,
                "queued_count": 0, "running_count": 0,
                "terminal_count": 1, "invocation_ids": ["TI-private"],
                "grant_ids": ["TG-private"], "arguments": "private",
            },
        )

        payload = snapshot.public_dict()

        self.assertEqual(payload["activity"], "reviewing_candidates")
        self.assertEqual(payload["persona"], {"persona_id": "murr", "display_name": "Murr", "resident_action": {"kind": "idle"}})
        self.assertNotIn("raw_payload", payload["provider"])
        self.assertNotIn("error", payload["lifecycle"])
        self.assertNotIn("secret", payload["system_metrics"]["cpu"])
        self.assertNotIn("raw", payload["system_metrics"]["gpu"])
        self.assertNotIn("hidden_resource", payload["adventure"])
        self.assertNotIn("drafts", payload["adventure_turn"])
        self.assertEqual("assistant_chat", payload["adventure_turn"]["last_task_routes"][0]["requested_task_id"])
        self.assertEqual(2, len(payload["adventure_turn"]["last_task_routes"]))
        self.assertNotIn("raw_provider_output", payload["adventure_turn"]["last_task_routes"][0])
        self.assertEqual("provider_concurrency_busy", payload["adventure_turn"]["last_task_routes"][1]["outcome"])
        self.assertNotIn("body", payload["candidate_inbox"])
        self.assertEqual(payload["routing"], {
            "configured_task_count": 4, "routable_task_count": 3,
            "unavailable_task_count": 1, "storage": "session_ephemeral",
        })
        self.assertEqual(payload["focus_mode"], {
            "enabled": True, "storage": "session_ephemeral",
        })
        self.assertNotIn("task_names", payload["focus_mode"])
        self.assertNotIn("monitoring", payload["focus_mode"])
        self.assertEqual(payload["sandbox_execution"], {
            "schema_version": 1, "configured": True, "host_status": "unsupported",
            "supervisor_status": "unavailable", "execution_status": "unavailable",
            "reason": "host_unsupported", "storage": "presentation_ephemeral",
        })
        self.assertNotIn("endpoint", payload["sandbox_execution"])
        self.assertNotIn("principal", payload["sandbox_execution"])
        self.assertNotIn("key_id", payload["sandbox_execution"])
        self.assertEqual(payload["tool_activity"], {
            "schema_version": 1, "total_count": 2,
            "pending_review_count": 1, "approved_count": 0,
            "queued_count": 0, "running_count": 0,
            "terminal_count": 1, "storage": "session_ephemeral",
        })
        self.assertNotIn("invocation_ids", payload["tool_activity"])
        self.assertNotIn("grant_ids", payload["tool_activity"])
        self.assertNotIn("arguments", payload["tool_activity"])

    def test_explicit_resident_action_keeps_zero_provider_presentation_available(self):
        snapshot = ResidentSnapshot(
            conversation_id="zero-provider", persona={"persona_id": "murr", "resident_action": {"kind": "reading"}},
            provider={"configured": False}, lifecycle=None, system_metrics={}, capability_ids=(),
            adventure={"mounted": False}, roleplay={"active": False}, turn={"active": False},
            candidates={"ordinary_count": 0, "mutation_count": 0},
            routing={},
        )

        self.assertEqual(snapshot.activity, "idle")
        self.assertEqual(snapshot.public_dict()["provider"], {"configured": False})
        self.assertEqual(snapshot.public_dict()["focus_mode"], {
            "enabled": False, "storage": "session_ephemeral",
        })
        self.assertEqual(snapshot.public_dict()["sandbox_execution"]["reason"], "not_configured")


if __name__ == "__main__":
    unittest.main()
