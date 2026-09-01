import sys
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.application import AssistantApplication, create_assistant_application
from pipeline.document_intake import DocumentAnnotationExecution, prepare_document_text
from pipeline.persona_registry import PersonaRegistry, load_persona_package
from pipeline.system_metrics import SystemMetricsSnapshot


class FakeConfig:
    chat_model = "fake:latest"
    persona_path = Path("persona.md")
    policy_path = Path("policy.md")


class FakeSession:
    def __init__(self, config=None, *args, **kwargs):
        self.config = config or FakeConfig()
        self.active_model = "fake:latest"
        self.stream = False
        self.stream_writer = None
        self.calls = []
        self.messages = []
        self.last_memory_ids = []
        self.pending_bulk_approval = None

    def respond(self, text):
        self.calls.append((text, self.stream))
        self.messages.append({"role": "user", "content": text})
        if self.stream and self.stream_writer:
            self.stream_writer("chunk")
        return "answer"

    def context_stats(self):
        return "stats"


class FailingSession(FakeSession):
    def respond(self, text):
        self.calls.append((text, self.stream))
        raise RuntimeError("expected failure")


class BlockingSession(FakeSession):
    def __init__(self, started, release, config=None):
        super().__init__(config=config)
        self.started = started
        self.release = release

    def respond(self, text):
        self.calls.append((text, self.stream))
        self.started.set()
        if not self.release.wait(2):
            raise RuntimeError("test response was not released")
        self.messages.append({"role": "user", "content": text})
        return "answer"


class SequentialBlockingSession(FakeSession):
    def __init__(self, started_events, release_events, config=None):
        super().__init__(config=config)
        self.started_events = started_events
        self.release_events = release_events
        self._call_lock = threading.Lock()

    def respond(self, text):
        with self._call_lock:
            index = len(self.calls)
            self.calls.append((text, self.stream))
        self.started_events[index].set()
        if not self.release_events[index].wait(2):
            raise RuntimeError("test response was not released")
        self.messages.append({"role": "user", "content": text})
        return "answer"


class HealthyProvider:
    name = "healthy fake"

    def __init__(self):
        self.probe_calls = 0

    def probe_health(self):
        self.probe_calls += 1
        return {"models": [{"name": "one"}, {"name": "two"}]}


class UnavailableProvider:
    name = "unavailable fake"

    def probe_health(self):
        raise RuntimeError("provider is offline")


class AssistantApplicationTests(unittest.TestCase):
    def test_respond_delegates_and_preserves_normal_session_streaming(self):
        session = FakeSession()
        app = AssistantApplication(session)

        self.assertEqual(app.respond("hello"), "answer")

        self.assertEqual(session.calls, [("hello", False)])
        self.assertFalse(session.stream)
        self.assertIsNone(session.stream_writer)
        self.assertEqual(app.active_model, "fake:latest")

    def test_request_scoped_streaming_is_restored_after_response(self):
        session = FakeSession()
        app = AssistantApplication(session)
        chunks = []

        self.assertEqual(app.respond("stream", stream_writer=chunks.append), "answer")

        self.assertEqual(chunks, ["chunk"])
        self.assertEqual(session.calls, [("stream", True)])
        self.assertFalse(session.stream)
        self.assertIsNone(session.stream_writer)

    def test_request_scoped_streaming_is_restored_after_error(self):
        session = FailingSession()
        app = AssistantApplication(session)

        with self.assertRaisesRegex(RuntimeError, "expected failure"):
            app.respond("stream", stream_writer=lambda text: None)

        self.assertFalse(session.stream)
        self.assertIsNone(session.stream_writer)

    def test_context_stats_delegates_without_a_turn(self):
        self.assertEqual(AssistantApplication(FakeSession()).context_stats(), "stats")

    def test_persona_runtime_snapshot_is_read_only_and_bounded(self):
        class Runtime:
            def public_dict(self):
                return {"persona_id": "murr", "storage": "restart_ephemeral"}

        session = FakeSession()
        session.persona_runtime_state = Runtime()
        app = AssistantApplication(session)

        result = app.persona_runtime_snapshot()

        self.assertEqual(result, {
            "object": "starfur.persona_runtime",
            "available": True,
            "persona": {"persona_id": "murr", "storage": "restart_ephemeral"},
        })
        self.assertEqual(session.calls, [])

    def test_persona_runtime_snapshot_is_compatible_with_legacy_sessions(self):
        session = FakeSession()
        app = AssistantApplication(session)

        self.assertEqual(app.persona_runtime_snapshot(), {
            "object": "starfur.persona_runtime", "available": False, "persona": None,
        })

    def test_resident_snapshot_is_read_only_and_summary_only(self):
        class Runtime:
            def public_dict(self):
                return {"persona_id": "murr", "display_name": "Murr", "static_identity": "hidden"}

        class Lifecycle:
            def public_dict(self):
                return {"state": "idle", "error": "hidden", "transition_count": 2}

        class Adventure:
            def public_dict(self):
                return {"mounted": True, "title": "Quiet Ember", "hidden_resource": "ammo"}

        class Roleplay:
            def public_dict(self):
                return {"active": True, "title": "Quiet Ember", "storage": "session_ephemeral"}

        class Turn:
            active = True
            drafts = (object(), object())

        class Inbox:
            active = True
            batch = type("Batch", (), {"candidates": (object(),)})()

        session = FakeSession()
        session.persona_runtime_state = Runtime()
        session.provider = type("Provider", (), {"name": "fake"})()
        session.provider_lifecycle = Lifecycle()
        session.adventure_session = Adventure()
        session.roleplay_state = Roleplay()
        session.adventure_turn = Turn()
        session.adventure_turn_candidate_inbox = Inbox()
        session.adventure_turn_mutation_candidate_inbox = Inbox()
        class Metrics:
            def snapshot(self):
                return SystemMetricsSnapshot("partial", platform_name="test", cpu_logical_cores=4)

        app = AssistantApplication(session, system_metrics_provider=Metrics())

        result = app.resident_snapshot()

        self.assertEqual(result["object"], "starfur.resident_snapshot")
        self.assertEqual(result["conversation"]["id"], "default")
        self.assertEqual(result["activity"], "reviewing_candidates")
        self.assertEqual(result["adventure_turn"], {"active": True, "staged_count": 2})
        self.assertEqual(result["candidate_inbox"]["ordinary_count"], 1)
        self.assertEqual(result["presentation"]["animation_slot"], "resident.murr.reviewing")
        self.assertEqual(result["system_metrics"]["cpu"]["logical_cores"], 4)
        self.assertNotIn("static_identity", result["persona"])
        self.assertNotIn("error", result["lifecycle"])
        self.assertNotIn("hidden_resource", result["adventure"])
        self.assertEqual(session.calls, [])

    def test_application_isolates_ephemeral_state_per_conversation(self):
        default = FakeSession()
        created = []

        def make_session():
            session = FakeSession()
            created.append(session)
            return session

        app = AssistantApplication(default, session_factory=make_session, max_conversations=2)
        app.respond("first turn", conversation_id="chat-a")
        app.respond("second turn", conversation_id="chat-b")
        app.respond("another a turn", conversation_id="chat-a")

        session_a, session_b = created
        session_a.active_model = "model-a"
        session_a.last_memory_ids = ["M-001"]
        session_a.pending_bulk_approval = {"proposal": "P-001"}

        self.assertEqual(default.calls, [])
        self.assertEqual([call[0] for call in session_a.calls], ["first turn", "another a turn"])
        self.assertEqual([call[0] for call in session_b.calls], ["second turn"])
        self.assertEqual(session_b.active_model, "fake:latest")
        self.assertEqual(session_b.last_memory_ids, [])
        self.assertIsNone(session_b.pending_bulk_approval)
        self.assertEqual(app.active_model_for("chat-a"), "model-a")
        self.assertEqual(app.active_model_for("chat-b"), "fake:latest")

    def test_application_evicts_only_bounded_nondefault_conversations(self):
        default = FakeSession()
        created = []

        def make_session():
            session = FakeSession()
            created.append(session)
            return session

        app = AssistantApplication(default, session_factory=make_session, max_conversations=1)
        app.respond("one", conversation_id="chat-one")
        app.respond("two", conversation_id="chat-two")
        app.respond("one again", conversation_id="chat-one")

        self.assertEqual(len(created), 3)
        self.assertEqual(default.calls, [])
        self.assertEqual([call[0] for call in created[-1].calls], ["one again"])

    def test_independent_conversations_do_not_wait_on_each_others_response(self):
        starts = [threading.Event(), threading.Event()]
        releases = [threading.Event(), threading.Event()]
        created = []

        def make_session():
            session = BlockingSession(starts[len(created)], releases[len(created)])
            created.append(session)
            return session

        app = AssistantApplication(FakeSession(), session_factory=make_session)
        first = threading.Thread(target=app.respond, args=("first",), kwargs={"conversation_id": "chat-a"})
        second = threading.Thread(target=app.respond, args=("second",), kwargs={"conversation_id": "chat-b"})
        first.start()
        self.assertTrue(starts[0].wait(0.5))
        second.start()
        try:
            self.assertTrue(starts[1].wait(0.5))
        finally:
            for release in releases:
                release.set()
            first.join(2)
            second.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())

    def test_same_conversation_remains_serialized_while_response_is_active(self):
        started = [threading.Event(), threading.Event()]
        releases = [threading.Event(), threading.Event()]
        created = []

        def make_session():
            session = SequentialBlockingSession(started, releases)
            created.append(session)
            return session

        app = AssistantApplication(FakeSession(), session_factory=make_session)
        first = threading.Thread(target=app.respond, args=("first",), kwargs={"conversation_id": "chat-a"})
        second = threading.Thread(target=app.respond, args=("second",), kwargs={"conversation_id": "chat-a"})
        first.start()
        self.assertTrue(started[0].wait(0.5))
        second.start()
        try:
            self.assertFalse(started[1].wait(0.15))
            releases[0].set()
            self.assertTrue(started[1].wait(0.5))
        finally:
            for release in releases:
                release.set()
            first.join(2)
            second.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual([call[0] for call in created[0].calls], ["first", "second"])

    def test_application_rejects_invalid_conversation_identifiers(self):
        app = AssistantApplication(FakeSession(), session_factory=FakeSession)

        with self.assertRaisesRegex(ValueError, "Conversation identifier"):
            app.respond("hello", conversation_id="not/a/session")

    def test_document_annotation_is_serialized_review_only_and_injectable(self):
        session = FakeSession()

        class RecordingLifecycle:
            def __init__(self):
                self.events = []

            def begin_generation(self, *, stream, model):
                self.events.append(("begin", stream, model))

            def finish(self):
                self.events.append(("finish",))

            def fail(self, error):
                self.events.append(("fail", str(error)))

        lifecycle = RecordingLifecycle()
        session.provider_lifecycle = lifecycle
        app = AssistantApplication(session)
        document = prepare_document_text(
            "Roger prefers tea.", "notes.md", domain="personal",
        )
        seen = []

        def annotator(chunk):
            seen.append(chunk.chunk_id)
            return {"proposals": [{
                "store": True,
                "subject": "Roger",
                "memory_type": "preference",
                "summary": "Roger prefers tea.",
                "details": None,
                "importance": 0.6,
                "confidence": 0.9,
                "retention": "long_term",
            }]}

        annotation = app.annotate_document(document, annotator=annotator)
        candidates = annotation.candidates

        self.assertEqual(seen, [document.chunks[0].chunk_id])
        self.assertEqual(candidates[0].proposal["source"], "external_document_annotation")
        self.assertEqual(session.calls, [])
        self.assertEqual(lifecycle.events, [("begin", False, "fake:latest"), ("finish",)])

    def test_document_annotation_adds_elapsed_time_to_bounded_execution_accounting(self):
        class TimedAnnotator:
            def __call__(self, _chunk):
                return {"proposals": []}

            def execution_summary(self):
                return DocumentAnnotationExecution("phi4-mini:latest", 1, "qwen3:8b", 0)

        app = AssistantApplication(FakeSession())
        document = prepare_document_text("No durable facts.", "notes.md", domain="personal")
        with patch("pipeline.application.perf_counter", side_effect=(10.0, 11.25)):
            result = app.annotate_document(document, annotator=TimedAnnotator())
        self.assertEqual("phi4-mini:latest", result.execution.primary_model)
        self.assertEqual(1250.0, result.execution.elapsed_ms)

    def test_document_proposal_handoff_uses_existing_writer_with_original_provenance(self):
        writes = []

        def proposal_creator(proposal, *, domain, source_reference, observation_text):
            writes.append({
                "proposal": proposal,
                "domain": domain,
                "source_reference": source_reference,
                "observation_text": observation_text,
            })
            return {"proposal_id": 41, "action": "created", "evidence_count": 1}

        app = AssistantApplication(FakeSession(), proposal_creator=proposal_creator)
        document = prepare_document_text("Roger prefers tea.", "notes.md", domain="personal")
        candidate = app.annotate_document(document, annotator=lambda _chunk: {"proposals": [{
            "store": True,
            "subject": "Roger",
            "memory_type": "preference",
            "summary": "Roger prefers tea.",
            "details": None,
            "importance": 0.6,
            "confidence": 0.9,
            "retention": "long_term",
        }]}).candidates[0]

        result = app.create_document_pending_proposal(candidate)

        self.assertEqual(result["proposal_id"], 41)
        self.assertEqual(writes[0]["domain"], "personal")
        self.assertRegex(
            writes[0]["source_reference"],
            rf"^{candidate.chunk_id}:candidate:[0-9a-f]{{64}}$",
        )
        self.assertEqual(writes[0]["observation_text"], "Roger prefers tea.")
        self.assertEqual(writes[0]["proposal"]["source"], "external_document_annotation")
    def test_runtime_diagnostics_are_bounded_and_do_not_probe_provider(self):
        session = FakeSession()
        app = AssistantApplication(session)
        snapshot = app.runtime_diagnostics()
        self.assertEqual(snapshot["status"], "provider_unavailable")
        self.assertEqual(snapshot["provider"]["health"], "not_probed")
        self.assertFalse(snapshot["provider"]["probe_performed"])
        self.assertEqual(snapshot["model"]["active"], "fake:latest")
        self.assertIsNone(snapshot["latest_turn"])
        self.assertTrue(snapshot["capabilities"]["ids"])
        self.assertIsNone(snapshot["lifecycle"])
        self.assertEqual("unavailable", snapshot["routing"]["provider"]["status"])
        self.assertEqual("unavailable", snapshot["routing"]["tasks"]["assistant_chat"]["status"])

    def test_runtime_diagnostics_include_passive_provider_route_preview(self):
        session = FakeSession()
        session.provider = HealthyProvider()
        app = AssistantApplication(session)

        snapshot = app.runtime_diagnostics()

        self.assertEqual("unprobed", snapshot["routing"]["provider"]["status"])
        chat = snapshot["routing"]["tasks"]["assistant_chat"]
        self.assertEqual("routable", chat["status"])
        self.assertEqual("unprobed", chat["candidates"][0]["provider_status"])

    def test_runtime_diagnostics_expose_only_bounded_completed_turn_route_trace(self):
        session = FakeSession()
        session.last_turn_diagnostics = {
            "turn_status": "completed", "completed": True,
            "model": "qwen3:8b", "provider": "Ollama",
            "response_characters": 12, "response_latency_ms": 24.0,
            "time_to_first_token_ms": None, "proposal_outcome": "skipped",
            "task_routes": [{
                "requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat",
                "provider": "ollama", "model": "qwen3:8b",
                "fallback_used": False, "outcome": "submitted",
            }],
        }
        snapshot = AssistantApplication(session).runtime_diagnostics()

        self.assertEqual([{
            "requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat",
            "provider": "ollama", "model": "qwen3:8b",
            "fallback_used": False, "outcome": "submitted",
        }], snapshot["latest_turn"]["task_routes"])

    def test_runtime_diagnostics_drop_malformed_or_unbounded_turn_route_trace_data(self):
        session = FakeSession()
        session.last_turn_diagnostics = {
            "task_routes": [
                {"requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat", "provider": "ollama", "model": "qwen3:8b", "fallback_used": False, "outcome": "submitted"},
                {"requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat", "provider": "ollama", "model": "x" * 257, "fallback_used": False, "outcome": "submitted", "raw_provider_output": "must not leak"},
                {"requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat", "provider": "ollama", "model": "qwen3:8b", "fallback_used": "no", "outcome": "submitted"},
            ],
        }
        snapshot = AssistantApplication(session).runtime_diagnostics()

        self.assertEqual(1, len(snapshot["latest_turn"]["task_routes"]))
        self.assertNotIn("raw_provider_output", snapshot["latest_turn"]["task_routes"][0])

    def test_explicit_provider_probe_records_only_bounded_health_metadata(self):
        session = FakeSession()
        provider = HealthyProvider()
        session.provider = provider
        app = AssistantApplication(session)

        before = app.runtime_diagnostics()
        snapshot = app.runtime_diagnostics(probe_provider=True)

        self.assertEqual(provider.probe_calls, 1)
        self.assertEqual(before["provider"]["health"], "not_probed")
        self.assertEqual(snapshot["provider"]["name"], "healthy fake")
        self.assertEqual(snapshot["provider"]["health"], "healthy")
        self.assertTrue(snapshot["provider"]["probe_performed"])
        self.assertEqual(snapshot["provider"]["model_count"], 2)
        self.assertIsNotNone(snapshot["provider"]["checked_at"])
        self.assertIsNone(snapshot["provider"]["error"])
        self.assertEqual(session.calls, [])

    def test_explicit_provider_probe_reports_unavailability_without_generating(self):
        session = FakeSession()
        session.provider = UnavailableProvider()
        app = AssistantApplication(session)

        snapshot = app.runtime_diagnostics(probe_provider=True)

        self.assertEqual(snapshot["provider"]["health"], "unavailable")
        self.assertTrue(snapshot["provider"]["probe_performed"])
        self.assertEqual(snapshot["provider"]["error"], "provider is offline")
        self.assertEqual(session.calls, [])
    def test_application_attaches_one_core_manifest_when_session_supports_it(self):
        class ManifestAwareSession(FakeSession):
            def set_capability_manifest(self, manifest):
                self.received_manifest = manifest

        session = ManifestAwareSession()
        app = AssistantApplication(session)

        self.assertIs(session.received_manifest, app.capability_manifest)
        self.assertIsNotNone(app.capability_manifest.get("assistant.memory.proposals"))
    def test_factory_centralizes_standard_session_dependencies(self):
        config = FakeConfig()
        captured = {}

        def session_factory(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return FakeSession(*args, **kwargs)

        with patch("pipeline.application.load_config", return_value=config), patch(
            "pipeline.application.load_persona", return_value="persona"
        ), patch("pipeline.application.load_policy", return_value="policy"):
            app = create_assistant_application(
                "custom.json",
                stream=True,
                stream_writer=lambda text: None,
                debug_level="verbose",
                session_factory=session_factory,
            )

        self.assertIsInstance(app, AssistantApplication)
        self.assertEqual(captured["args"], (config, "persona"))
        self.assertEqual(captured["kwargs"]["policy"], "policy")
        self.assertTrue(captured["kwargs"]["stream"])
        self.assertEqual(captured["kwargs"]["debug_level"], "verbose")
        self.assertIsNotNone(captured["kwargs"]["proposal_creator"])

    def test_standard_factory_resolves_only_the_declared_builtin_murr_idle_slot(self):
        app = create_assistant_application(session_factory=FakeSession)

        asset = app.persona_asset_resolver.resolve("murr", "idle")
        self.assertIsNotNone(asset)
        self.assertTrue(asset.is_file())
        self.assertIsNone(app.persona_asset_resolver.resolve("nova", "idle"))

    def test_factory_preserves_builtin_murr_art_for_a_pre_manifest_stock_config(self):
        config = FakeConfig()
        config.persona_registry = PersonaRegistry((load_persona_package(
            None, persona_id="murr", display_name="Murr",
        ),))
        config.active_persona_id = "murr"

        with patch("pipeline.application.load_config", return_value=config), patch(
            "pipeline.application.load_policy", return_value="policy"
        ):
            app = create_assistant_application("legacy-config.json", session_factory=FakeSession)

        self.assertTrue(app.persona_asset_resolver.resolve("murr", "idle").is_file())


if __name__ == "__main__":
    unittest.main()
