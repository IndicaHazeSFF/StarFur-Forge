import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.application import AssistantApplication, create_assistant_application
from pipeline.document_intake import prepare_document_text


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
        self.assertEqual(writes[0]["source_reference"], f"{candidate.chunk_id}:candidate:0")
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


if __name__ == "__main__":
    unittest.main()
