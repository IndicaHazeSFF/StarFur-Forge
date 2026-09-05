import http.client
import json
import sys
import tempfile
import threading
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.application import AssistantApplication
from pipeline.persona_asset_resolver import InstalledPersonaAssetPackage, PersonaAssetResolver
from pipeline.persona_assets import PersonaAssetManifest

from pipeline.adventure_events import AdventureEventLog
from pipeline.adventure_registry import AdventureRegistry
from pipeline.assistant import AssistantSession
from pipeline.api import APARTMENT_DASHBOARD_PATH, API_MODEL_ID, CONVERSATION_HEADER, DOCUMENT_ADVENTURE_IMPORT_PATH, DOCUMENT_ANNOTATE_PATH, DOCUMENT_CONTEXT_PATH, DOCUMENT_PREPARE_PATH, DOCUMENT_REVIEW_PATH, DOCUMENT_REVIEWS_PATH, MURR_IDLE_ASSET_PATH, PERSONA_RUNTIME_PATH, RESIDENT_SNAPSHOT_PATH, StarFurAPI, StarFurHTTPServer


class FakeConfig:
    chat_model = "qwen3:8b"
    domain = "personal"


class FakeSession:
    def __init__(self):
        self.config = FakeConfig()
        self.active_model = "qwen3:8b"
        self.stream = False
        self.stream_writer = None
        self.calls = []
        self.messages = []
        self.last_memory_ids = []
        self.pending_bulk_approval = None
        self.document_contexts = []

    def respond(self, text, *, external_document_context=None):
        self.calls.append(text)
        self.document_contexts.append(external_document_context)
        self.messages.append({"role": "user", "content": text})
        if self.stream and self.stream_writer:
            self.stream_writer("streamed answer")
        return "streamed answer" if self.stream else "normal answer"


class APITests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.sessions = [self.session]
        self.annotation_chunks = []
        self.proposal_writes = []
        # Document-review handoff tests inject proposal IDs instead of writing
        # proposals.  Keep public-reference rendering independent from any
        # developer's real assistant database, where an injected numeric ID
        # could coincidentally already exist with a different public ordinal.
        self.public_id_patch = patch(
            "pipeline.api.assistant_public_id",
            side_effect=lambda kind, record_id, domain="personal": (
                f"{'M' if kind == 'memory' else 'P'}-{int(record_id):03d}"
            ),
        )
        self.public_id_patch.start()

        def session_factory():
            session = FakeSession()
            self.sessions.append(session)
            return session

        def proposal_creator(proposal, *, domain, source_reference, observation_text):
            self.proposal_writes.append({
                "proposal": proposal,
                "domain": domain,
                "source_reference": source_reference,
                "observation_text": observation_text,
            })
            return {"proposal_id": 77, "action": "created", "evidence_count": 1}

        self.application = AssistantApplication(
            self.session,
            proposal_creator=proposal_creator,
            session_factory=session_factory,
            max_conversations=2,
            persona_asset_resolver=PersonaAssetResolver((InstalledPersonaAssetPackage(
                PersonaAssetManifest("murr", {"idle": "Assets/Murr/Murr_S_Idle.png"}),
                Path(__file__).resolve().parents[1],
            ),)),
        )
        self.adventure_directory = tempfile.TemporaryDirectory()
        self.adventure_registry = AdventureRegistry(self.adventure_directory.name)
        self.adventure_record = self.adventure_registry.create("Quiet Ember")

        def document_annotator(chunk):
            self.annotation_chunks.append(chunk)
            return {"proposals": [{
                "store": True,
                "subject": "Roger",
                "memory_type": "project_context",
                "summary": "Roger is testing document intake.",
                "details": None,
                "importance": 0.7,
                "confidence": 0.9,
                "retention": "short_term",
            }]}

        self.api = StarFurAPI(
            self.application,
            api_key="local-test",
            document_annotator=document_annotator,
            adventure_registry=self.adventure_registry,
        )
        self.server = StarFurHTTPServer(("127.0.0.1", 0), self.api, quiet=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.adventure_directory.cleanup()
        self.public_id_patch.stop()

    def request(self, method, path, body=None, *, auth=True, extra_headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer local-test"
        if extra_headers:
            headers.update(extra_headers)
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response.status, raw

    def test_health_and_models_are_openai_compatible(self):
        status, raw = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["status"], "ok")
        status, raw = self.request("GET", "/v1/models")
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"][0]["id"], API_MODEL_ID)
        self.assertEqual(payload["data"][0]["active_backend"], "qwen3:8b")
        status, raw = self.request("GET", "/v1/starfur/diagnostics")
        diagnostics = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(diagnostics["model"]["active"], "qwen3:8b")
        self.assertFalse(diagnostics["provider"]["probe_performed"])
        self.assertIn("capabilities", diagnostics)

    def test_diagnostics_provider_probe_is_explicit_and_non_generating(self):
        class Provider:
            name = "probe fake"

            def __init__(self):
                self.calls = 0

            def probe_health(self):
                self.calls += 1
                return {"models": [{"name": "one"}]}

        provider = Provider()
        self.session.provider = provider
        status, raw = self.request("GET", "/v1/starfur/diagnostics?probe=provider")
        diagnostics = json.loads(raw)

        self.assertEqual(status, 200)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(diagnostics["provider"]["health"], "healthy")
        self.assertEqual(diagnostics["provider"]["model_count"], 1)
        self.assertEqual(self.session.calls, [])

        status, raw = self.request("GET", "/v1/starfur/diagnostics?probe=all")
        self.assertEqual(status, 400)
        self.assertIn("probe=provider", json.loads(raw)["error"]["message"])

    def test_persona_runtime_endpoint_is_read_only_and_compatible(self):
        status, raw = self.request("GET", PERSONA_RUNTIME_PATH)

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {
            "object": "starfur.persona_runtime", "available": False, "persona": None,
        })
        self.assertEqual(self.session.calls, [])

    def test_resident_snapshot_endpoint_is_authenticated_read_only_summary(self):
        status, raw = self.request("GET", RESIDENT_SNAPSHOT_PATH)
        payload = json.loads(raw)

        self.assertEqual(status, 200)
        self.assertEqual(payload["object"], "starfur.resident_snapshot")
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["conversation"]["id"], "default")
        self.assertEqual(payload["activity"], "provider_unavailable")
        self.assertEqual(payload["presentation"]["animation_slot"], "resident.default.offline")
        self.assertNotIn("messages", payload)
        self.assertEqual(self.session.calls, [])

        status, _ = self.request("GET", RESIDENT_SNAPSHOT_PATH, auth=False)
        self.assertEqual(status, 401)

    def test_read_only_snapshot_rejects_an_unknown_conversation_without_creating_it(self):
        status, raw = self.request(
            "GET", RESIDENT_SNAPSHOT_PATH,
            extra_headers={CONVERSATION_HEADER: "missing-snapshot"},
        )
        payload = json.loads(raw)
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["type"], "conversation_not_found")
        self.assertEqual(len(self.sessions), 1)

    def test_apartment_shell_is_public_but_contains_no_runtime_or_token(self):
        status, raw = self.request("GET", APARTMENT_DASHBOARD_PATH, auth=False)
        page = raw.decode("utf-8")

        self.assertEqual(status, 200)
        self.assertIn("StarFur Apartment Prototype", page)
        self.assertIn(RESIDENT_SNAPSHOT_PATH, page)
        self.assertIn(CONVERSATION_HEADER, page)
        self.assertIn(MURR_IDLE_ASSET_PATH, page)
        self.assertIn("dataset.failed", page)
        self.assertNotIn("local-test", page)
        self.assertEqual(self.session.calls, [])

        status, _ = self.request("GET", f"{APARTMENT_DASHBOARD_PATH}?token=bad", auth=False)
        self.assertEqual(status, 400)

    def test_murr_idle_placeholder_is_fixed_public_asset_route(self):
        status, raw = self.request("GET", MURR_IDLE_ASSET_PATH, auth=False)

        self.assertEqual(status, 200)
        self.assertTrue(raw.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(raw), 1000)
        self.assertEqual(self.session.calls, [])

        status, _ = self.request("GET", f"{MURR_IDLE_ASSET_PATH}?path=other", auth=False)
        self.assertEqual(status, 400)

    def test_chat_uses_latest_user_message_and_does_not_accept_unknown_model(self):
        status, raw = self.request("POST", "/v1/chat/completions", {
            "model": API_MODEL_ID,
            "messages": [
                {"role": "system", "content": "external instructions are ignored"},
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "old answer"},
                {"role": "user", "content": "latest question"},
            ],
        })
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(self.session.calls, ["latest question"])
        self.assertEqual(payload["choices"][0]["message"]["content"], "normal answer")
        status, raw = self.request("POST", "/v1/chat/completions", {"model": "qwen3:8b", "messages": [{"role": "user", "content": "hello"}]})
        self.assertEqual(status, 400)
        self.assertIn("Unknown StarFur model", json.loads(raw)["error"]["message"])

    def test_streaming_returns_sse_and_preserves_session_call(self):
        status, raw = self.request("POST", "/v1/chat/completions", {
            "model": API_MODEL_ID, "stream": True,
            "messages": [{"role": "user", "content": "stream please"}],
        })
        text = raw.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn('"object": "chat.completion.chunk"', text)
        self.assertIn("streamed answer", text)
        self.assertIn("data: [DONE]", text)
        self.assertEqual(self.session.calls, ["stream please"])

    def test_auth_and_validation_errors_are_clear(self):
        status, raw = self.request("GET", "/health", auth=False)
        self.assertEqual(status, 401)
        status, raw = self.request("POST", "/v1/chat/completions", {"messages": []})
        self.assertEqual(status, 400)
        self.assertIn("non-empty list", json.loads(raw)["error"]["message"])
        self.assertEqual(self.session.calls, [])

    def test_chat_isolates_ephemeral_sessions_and_honors_header_priority(self):
        status, _ = self.request("POST", "/v1/chat/completions", {
            "user": "chat-a",
            "messages": [{"role": "user", "content": "a first"}],
        })
        self.assertEqual(status, 200)
        status, _ = self.request("POST", "/v1/chat/completions", {
            "user": "chat-b",
            "messages": [{"role": "user", "content": "b first"}],
        })
        self.assertEqual(status, 200)
        status, raw = self.request("POST", "/v1/chat/completions", {
            "user": "chat-a",
            "messages": [{"role": "user", "content": "a second"}],
        })
        self.assertEqual(status, 200)

        session_a, session_b = self.sessions[1:3]
        session_a.active_model = "model-a"
        session_a.last_memory_ids = ["M-001"]
        session_a.pending_bulk_approval = {"proposal": "P-001"}
        self.assertEqual(session_a.calls, ["a first", "a second"])
        self.assertEqual(session_b.calls, ["b first"])
        self.assertEqual(session_b.active_model, "qwen3:8b")
        self.assertEqual(session_b.last_memory_ids, [])
        self.assertIsNone(session_b.pending_bulk_approval)

        status, raw = self.request("POST", "/v1/chat/completions", {
            "user": "body-session",
            "messages": [{"role": "user", "content": "header wins"}],
        }, extra_headers={CONVERSATION_HEADER: "header-session"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["model"], "qwen3:8b")
        self.assertEqual(self.sessions[-1].calls, ["header wins"])

    def test_invalid_conversation_identifier_returns_client_error(self):
        status, raw = self.request("POST", "/v1/chat/completions", {
            "conversation_id": "bad/session",
            "messages": [{"role": "user", "content": "hello"}],
        })
        self.assertEqual(status, 400)
        self.assertIn("Conversation identifier", json.loads(raw)["error"]["message"])
        self.assertEqual(self.session.calls, [])


    def test_document_preparation_is_authenticated_metadata_only_and_never_calls_chat(self):
        status, raw = self.request("POST", DOCUMENT_PREPARE_PATH, {
            "filename": "notes.md",
            "content": "# Notes\n\nStarFur keeps provenance.",
            "domain": "project:starfur",
        })
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(payload["object"], "starfur.document.preparation")
        self.assertEqual(payload["source"]["name"], "notes.md")
        self.assertEqual(payload["source"]["domain"], "project:starfur")
        self.assertEqual(payload["source"]["profile"], "assistant_note")
        self.assertEqual(payload["source"]["chunk_count"], 1)
        self.assertTrue(payload["source"]["id"].startswith("external:"))
        self.assertNotIn("text", payload["chunks"][0])
        self.assertEqual(self.session.calls, [])

    def test_document_preparation_accepts_structural_profile(self):
        status, raw = self.request("POST", DOCUMENT_PREPARE_PATH, {
            "filename": "adventure.md",
            "content": "# Story State\n\nKnown fact.\n\nCURRENT SCENE\n\nThe storm begins.",
            "domain": "personal",
            "profile": "adventure_state",
        })
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(payload["source"]["profile"], "adventure_state")
        self.assertEqual(payload["source"]["chunk_count"], 2)

    def test_document_annotation_returns_reviewable_candidates_without_chat_or_storage(self):
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md",
            "content": "Roger is testing document intake.",
            "domain": "personal",
        })
        payload = json.loads(raw)

        self.assertEqual(status, 200)
        self.assertEqual(payload["object"], "starfur.document.annotation")
        self.assertEqual(payload["source"]["domain"], "personal")
        self.assertEqual(len(payload["candidates"]), 1)
        candidate = payload["candidates"][0]
        self.assertEqual(candidate["proposal"]["source"], "external_document_annotation")
        self.assertEqual(candidate["provenance"]["chunk_id"], self.annotation_chunks[0].chunk_id)
        self.assertNotIn("observation_text", candidate["provenance"])
        self.assertEqual(self.session.calls, [])

    def test_document_annotation_terminal_progress_is_opt_in_and_finishes_with_json(self):
        status, raw = self.request("POST", f"{DOCUMENT_ANNOTATE_PATH}?stream=terminal", {
            "filename": "notes.md",
            "content": "Roger is testing document intake.",
            "domain": "personal",
        })
        text = raw.decode("utf-8")

        self.assertEqual(status, 200)
        self.assertIn("\rStarFur annotation: [", text)
        self.assertIn("1/1 chunks", text)
        payload = json.loads(text.strip().splitlines()[-1])
        self.assertEqual(payload["object"], "starfur.document.annotation")
        self.assertEqual(payload["source"]["chunk_count"], 1)
        self.assertEqual(len(payload["candidates"]), 1)
        self.assertEqual(self.session.calls, [])

    def test_document_annotation_rejects_unsupported_query_parameters(self):
        status, raw = self.request("POST", f"{DOCUMENT_ANNOTATE_PATH}?stream=events", {
            "filename": "notes.md",
            "content": "Roger is testing document intake.",
        })
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"]["message"], "Unsupported query parameter.")
        self.assertEqual(self.annotation_chunks, [])

    def test_document_candidate_handoff_requires_confirmation_and_writes_only_selected_server_candidate(self):
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md",
            "content": "Roger is testing document intake.",
            "domain": "personal",
        })
        annotation = json.loads(raw)
        review_id = annotation["review"]["id"]
        candidate_id = annotation["candidates"][0]["id"]
        self.assertEqual(self.proposal_writes, [])

        status, raw = self.request("POST", DOCUMENT_REVIEW_PATH, {
            "review_id": review_id,
            "candidate_id": candidate_id,
        })
        self.assertEqual(status, 400)
        self.assertIn("requires confirm", json.loads(raw)["error"]["message"])
        self.assertEqual(self.proposal_writes, [])

        status, raw = self.request("POST", DOCUMENT_REVIEW_PATH, {
            "review_id": review_id,
            "candidate_id": candidate_id,
            "confirm": "create pending proposal",
        })
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(payload["object"], "starfur.document.proposal_handoff")
        self.assertEqual(payload["proposal_id"], 77)
        self.assertEqual(payload["proposal_ref"], "P-077")
        self.assertEqual(payload["proposal_status"], "pending")
        self.assertEqual(payload["persistence_action"], "created")
        self.assertEqual(self.proposal_writes[0]["domain"], "personal")
        self.assertRegex(
            self.proposal_writes[0]["source_reference"],
            rf"^{self.annotation_chunks[0].chunk_id}:candidate:[0-9a-f]{{64}}$",
        )
        self.assertEqual(self.proposal_writes[0]["observation_text"], self.annotation_chunks[0].text)
        self.assertEqual(self.session.calls, [])

    def test_reviewed_document_candidates_can_be_staged_for_one_exact_adventure_without_events(self):
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "story.md", "content": "Vespera guards the brass hatch.", "domain": "personal",
        })
        annotation = json.loads(raw)
        review_id = annotation["review"]["id"]
        candidate_id = annotation["candidates"][0]["id"]

        status, raw = self.request("POST", DOCUMENT_ADVENTURE_IMPORT_PATH, {
            "review_id": review_id,
            "candidate_ids": [candidate_id],
            "adventure_title": "Quiet Ember",
        })
        self.assertEqual(status, 400)
        self.assertIn("requires confirm", json.loads(raw)["error"]["message"])

        status, raw = self.request("POST", DOCUMENT_ADVENTURE_IMPORT_PATH, {
            "review_id": review_id,
            "candidate_ids": [candidate_id],
            "adventure_title": "quiet ember",
            "confirm": "stage reviewed adventure import",
        })
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(payload["object"], "starfur.document.adventure_import_staging")
        self.assertEqual(payload["adventure"]["id"], self.adventure_record.adventure_id)
        self.assertEqual(payload["import"]["id"], "AI-000001")
        self.assertEqual(payload["import"]["candidate_count"], 1)
        self.assertEqual(payload["persistence_action"], "staged_noncanonical")
        workspace = self.adventure_registry.workspace_path(self.adventure_record.adventure_id)
        self.assertTrue((workspace / "imports.jsonl").exists())
        self.assertFalse((workspace / "events.jsonl").exists())
        self.assertEqual(self.proposal_writes, [])
        self.assertEqual(self.session.calls, [])

        status, raw = self.request("POST", DOCUMENT_ADVENTURE_IMPORT_PATH, {
            "review_id": review_id,
            "candidate_ids": [candidate_id],
            "adventure_title": "Quiet Ember",
            "confirm": "stage reviewed adventure import",
        })
        self.assertEqual(status, 200)
        self.assertEqual("AI-000001", json.loads(raw)["import"]["id"])
        self.assertEqual(1, len((workspace / "imports.jsonl").read_text(encoding="utf-8").splitlines()))

    def test_document_review_can_be_inspected_and_driven_by_controlled_chat_extension(self):
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md", "content": "Roger is testing document intake.",
        })
        annotation = json.loads(raw)
        review_id = annotation["review"]["id"]
        candidate_id = annotation["candidates"][0]["id"]

        status, raw = self.request("GET", f"{DOCUMENT_REVIEW_PATH}?review_id={review_id}")
        review = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(review["object"], "starfur.document.review")
        self.assertEqual(review["candidates"][0]["status"], "pending")
        self.assertNotIn("observation_text", str(review))

        status, raw = self.request("POST", "/v1/chat/completions", {
            "model": API_MODEL_ID,
            "messages": [{"role": "user", "content": f"document review {review_id}"}],
            "starfur_document_review": {"action": "show", "review_id": review_id},
        })
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertIn(candidate_id, payload["choices"][0]["message"]["content"])
        self.assertEqual(self.session.calls, [])

        status, raw = self.request("POST", "/v1/chat/completions", {
            "model": API_MODEL_ID,
            "messages": [{"role": "user", "content": f"document approve {review_id} {candidate_id}"}],
            "starfur_document_review": {
                "action": "approve", "review_id": review_id, "candidate_ids": [candidate_id],
                "confirm": "create pending proposals",
            },
        })
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertIn("P-077", payload["choices"][0]["message"]["content"])
        self.assertEqual(len(self.proposal_writes), 1)
        self.assertEqual(self.session.calls, [])

        status, raw = self.request("GET", f"{DOCUMENT_REVIEW_PATH}?review_id={review_id}")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["candidates"][0]["status"], "handed_off")

    def test_active_document_reviews_are_listed_by_read_only_endpoint_and_controlled_chat(self):
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md", "content": "Roger is testing document intake.",
        })
        review_id = json.loads(raw)["review"]["id"]

        status, raw = self.request("GET", DOCUMENT_REVIEWS_PATH)
        review_list = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(review_list["object"], "starfur.document.review_list")
        self.assertEqual(review_list["reviews"][0]["review"]["id"], review_id)
        self.assertNotIn("observation_text", str(review_list))
        self.assertEqual(self.session.calls, [])

        status, raw = self.request("POST", "/v1/chat/completions", {
            "model": API_MODEL_ID,
            "messages": [{"role": "user", "content": "document review list"}],
            "starfur_document_review": {"action": "list"},
        })
        self.assertEqual(status, 200)
        self.assertIn(review_id, json.loads(raw)["choices"][0]["message"]["content"])
        self.assertEqual(self.session.calls, [])

    def test_document_review_rejection_is_ephemeral_and_never_writes_a_proposal(self):
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md", "content": "Roger is testing document intake.",
        })
        annotation = json.loads(raw)
        review_id = annotation["review"]["id"]
        candidate_id = annotation["candidates"][0]["id"]
        status, raw = self.request("POST", "/v1/chat/completions", {
            "model": API_MODEL_ID,
            "messages": [{"role": "user", "content": f"document reject {review_id} {candidate_id}"}],
            "starfur_document_review": {
                "action": "reject", "review_id": review_id, "candidate_ids": [candidate_id],
                "confirm": "reject document candidates",
            },
        })
        self.assertEqual(status, 200)
        self.assertIn("No proposals or memories", json.loads(raw)["choices"][0]["message"]["content"])
        self.assertEqual(self.proposal_writes, [])

        status, raw = self.request("POST", DOCUMENT_REVIEW_PATH, {
            "review_id": review_id, "candidate_id": candidate_id,
            "confirm": "create pending proposal",
        })
        self.assertEqual(status, 404)
        self.assertIn("dismissed", json.loads(raw)["error"]["message"])

    def test_document_context_is_source_scoped_read_only_and_does_not_call_chat(self):
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md",
            "content": "# Hardware\n\nThe desktop has an RTX 4070 graphics card.\n\n# Food\n\nRoger prefers jasmine rice.",
        })
        annotation = json.loads(raw)
        self.assertEqual(status, 200)

        status, raw = self.request("POST", DOCUMENT_CONTEXT_PATH, {
            "review_id": annotation["review"]["id"],
            "query": "Which graphics card is in the desktop?",
            "limit": 1,
        })
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(payload["object"], "starfur.document.context")
        self.assertEqual(payload["source"]["id"], annotation["source"]["id"])
        self.assertEqual(len(payload["chunks"]), 1)
        self.assertIn("RTX 4070", payload["chunks"][0]["text"])
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.proposal_writes, [])

        status, raw = self.request("POST", DOCUMENT_CONTEXT_PATH, {
            "review_id": annotation["review"]["id"], "query": "the and of",
        })
        self.assertEqual(status, 400)
        self.assertIn("meaningful", json.loads(raw)["error"]["message"])

    def test_chat_can_attach_only_server_reviewed_document_context(self):
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md",
            "content": "The desktop has an RTX 4070 graphics card.",
            "domain": "personal",
        })
        annotation = json.loads(raw)
        self.assertEqual(status, 200)

        status, raw = self.request("POST", "/v1/chat/completions", {
            "model": API_MODEL_ID,
            "messages": [{"role": "user", "content": "What GPU is in the desktop?"}],
            "starfur_document_context": {"review_id": annotation["review"]["id"], "limit": 1},
        })
        self.assertEqual(status, 200)
        packet = self.session.document_contexts[-1]
        self.assertEqual(packet.source_id, annotation["source"]["id"])
        self.assertEqual(packet.query, "What GPU is in the desktop?")
        self.assertEqual(len(packet.chunks), 1)
        self.assertIn("RTX 4070", packet.chunks[0].chunk.text)
        self.assertEqual(self.proposal_writes, [])

        status, raw = self.request("POST", "/v1/chat/completions", {
            "model": API_MODEL_ID,
            "messages": [{"role": "user", "content": "What GPU is in the desktop?"}],
            "starfur_document_context": {
                "review_id": annotation["review"]["id"],
                "query": "client supplied alternate query",
            },
        })
        self.assertEqual(status, 400)
        self.assertIn("Unknown starfur_document_context", json.loads(raw)["error"]["message"])

    def test_document_candidate_batch_handoff_requires_plural_confirmation_and_preserves_order(self):
        self.api.document_annotator = lambda _chunk: {"proposals": [
            {
                "store": True, "subject": "Roger", "memory_type": "preference",
                "summary": "Roger prefers tea.", "details": None,
                "importance": 0.6, "confidence": 0.9, "retention": "long_term",
            },
            {
                "store": True, "subject": "Roger", "memory_type": "preference",
                "summary": "Roger prefers coffee.", "details": None,
                "importance": 0.6, "confidence": 0.9, "retention": "long_term",
            },
        ]}
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md", "content": "Roger is testing document intake.",
        })
        annotation = json.loads(raw)
        self.assertEqual(status, 200)
        review_id = annotation["review"]["id"]
        candidate_ids = [candidate["id"] for candidate in annotation["candidates"]]

        status, raw = self.request("POST", DOCUMENT_REVIEW_PATH, {
            "review_id": review_id,
            "candidate_ids": candidate_ids,
            "confirm": "create pending proposal",
        })
        self.assertEqual(status, 400)
        self.assertIn("batch handoff requires", json.loads(raw)["error"]["message"])
        self.assertEqual(self.proposal_writes, [])

        status, raw = self.request("POST", DOCUMENT_REVIEW_PATH, {
            "review_id": review_id,
            "candidate_ids": candidate_ids,
            "confirm": "create pending proposals",
        })
        payload = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(payload["object"], "starfur.document.proposal_handoff_batch")
        self.assertEqual(payload["count"], 2)
        self.assertEqual([item["candidate_id"] for item in payload["handoffs"]], candidate_ids)
        self.assertEqual(len(self.proposal_writes), 2)
        self.assertEqual(self.session.calls, [])

    def test_document_candidate_batch_validates_all_ids_before_writing(self):
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md", "content": "Roger is testing document intake.",
        })
        annotation = json.loads(raw)
        status, raw = self.request("POST", DOCUMENT_REVIEW_PATH, {
            "review_id": annotation["review"]["id"],
            "candidate_ids": [annotation["candidates"][0]["id"], "C-999"],
            "confirm": "create pending proposals",
        })
        self.assertEqual(status, 404)
        self.assertEqual(self.proposal_writes, [])

    def test_document_candidate_handoff_rejects_unknown_or_forged_review_identifiers(self):
        status, raw = self.request("POST", DOCUMENT_REVIEW_PATH, {
            "review_id": "DR-not-real",
            "candidate_id": "C-001",
            "confirm": "create pending proposal",
        })
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(raw)["error"]["type"], "document_review_not_found")
        self.assertEqual(self.proposal_writes, [])
    def test_document_annotation_is_authenticated_and_reports_invalid_model_output(self):
        status, _ = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md", "content": "text",
        }, auth=False)
        self.assertEqual(status, 401)
        self.api.document_annotator = lambda _chunk: {"proposals": "not a list"}
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md", "content": "text",
        })
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        self.assertEqual(payload["candidates"], [])
        self.assertEqual(payload["failures"][0]["attempts"], 3)
        self.assertEqual(payload["failures"][0]["reason"], "invalid_annotation_output")
        self.assertEqual(self.session.calls, [])
    def test_document_preparation_rejects_untrusted_filename_content_and_unknown_fields(self):
        status, raw = self.request("POST", DOCUMENT_PREPARE_PATH, {
            "filename": "../notes.md", "content": "content",
        })
        self.assertEqual(status, 400)
        self.assertIn("must not contain a path", json.loads(raw)["error"]["message"])
        status, raw = self.request("POST", DOCUMENT_PREPARE_PATH, {
            "filename": "notes.md", "content": 42,
        })
        self.assertEqual(status, 400)
        self.assertIn("text string", json.loads(raw)["error"]["message"])
        status, raw = self.request("POST", DOCUMENT_PREPARE_PATH, {
            "filename": "notes.md", "content": "content", "source": "untrusted",
        })
        self.assertEqual(status, 400)
        self.assertIn("Unknown document-preparation", json.loads(raw)["error"]["message"])
        self.assertEqual(self.session.calls, [])


class AdventureAPITests(unittest.TestCase):
    """Prove the API adapter preserves Core-owned adventure command handling."""

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.provider_calls = []
        config = type("AdventureConfig", (), {
            "chat_model": "test-model",
            "domain": "personal",
            "max_session_messages": 4,
            "max_memories": 2,
            "memory_policy": "off",
            "debug_level": "off",
        })()
        registry = AdventureRegistry(
            self.workspace.name, now=lambda: datetime(2026, 8, 20, tzinfo=UTC),
        )
        self.session = AssistantSession(
            config,
            "Persona",
            policy="Policy",
            adventure_registry=registry,
            chat=lambda **kwargs: self.provider_calls.append(kwargs) or {"message": {"content": "unexpected"}},
            memory_loader=lambda **kwargs: [],
        )
        self.api = StarFurAPI(AssistantApplication(self.session), api_key="local-test")
        self.server = StarFurHTTPServer(("127.0.0.1", 0), self.api, quiet=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.workspace.cleanup()

    def chat(self, content, **extensions):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        payload = {"model": API_MODEL_ID, "messages": [{"role": "user", "content": content}]}
        payload.update(extensions)
        connection.request(
            "POST",
            "/v1/chat/completions",
            json.dumps(payload),
            headers={"Authorization": "Bearer local-test", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        self.assertEqual(200, response.status)
        return json.loads(raw)["choices"][0]["message"]["content"]

    def test_api_keeps_adventure_commands_core_owned_and_staging_invisible_until_commit(self):
        self.assertIn("Created adventure workspace", self.chat("adventure create API Lantern"))
        self.assertIn("loaded: API Lantern", self.chat("adventure load API Lantern"))
        self.assertIn("staging started", self.chat("adventure turn begin"))
        self.assertIn("Staged adventure state", self.chat(
            "adventure turn stage state current_location: chart room"
        ))
        self.assertIn("Unknown or malformed adventure command", self.chat("adventure state nonsense"))
        self.assertEqual(
            "No explicit authoritative story state is recorded for the loaded workspace.",
            self.chat("adventure state"),
        )
        record = self.session.adventure_session.record
        self.assertEqual([], AdventureEventLog(self.session.adventure_registry, record).events())
        self.assertEqual([], self.provider_calls)
        self.assertEqual([], self.session.messages)

        self.assertIn("Committed 1 staged adventure event(s)", self.chat("adventure turn commit"))
        self.assertIn("current_location: chart room", self.chat("adventure state"))
        self.assertEqual([], self.provider_calls)

    def test_reserved_adventure_command_ignores_stale_document_extensions(self):
        content = self.chat(
            "adventure create Document-Safe Lantern",
            starfur_document_context={"review_id": "DR-" + "f" * 32, "limit": 1},
            starfur_document_review={"action": "list"},
        )
        self.assertIn("Created adventure workspace: Document-Safe Lantern", content)
        self.assertEqual([], self.provider_calls)
        self.assertEqual([], self.session.messages)

    def test_stale_document_extensions_do_not_override_non_adventure_core_controls(self):
        extensions = {
            "starfur_document_context": {"review_id": "DR-" + "f" * 32, "limit": 1},
            "starfur_document_review": {"action": "list"},
        }
        self.assertIn("Active persona:", self.chat("persona current", **extensions))
        self.assertIn("No turn diagnostics", self.chat("context stats", **extensions))
        self.assertIn("proposal", self.chat("proposal list", **extensions).casefold())
        self.assertEqual([], self.provider_calls)


if __name__ == "__main__":
    unittest.main()
