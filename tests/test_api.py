import http.client
import json
import sys
import threading
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.application import AssistantApplication

from pipeline.api import API_MODEL_ID, CONVERSATION_HEADER, DOCUMENT_ANNOTATE_PATH, DOCUMENT_PREPARE_PATH, DOCUMENT_REVIEW_PATH, StarFurAPI, StarFurHTTPServer


class FakeConfig:
    chat_model = "qwen3:8b"


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

    def respond(self, text):
        self.calls.append(text)
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
        )

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
        )
        self.server = StarFurHTTPServer(("127.0.0.1", 0), self.api, quiet=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

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
        self.assertEqual(payload["source"]["chunk_count"], 1)
        self.assertTrue(payload["source"]["id"].startswith("external:"))
        self.assertNotIn("text", payload["chunks"][0])
        self.assertEqual(self.session.calls, [])

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
        self.assertEqual(payload["proposal_status"], "pending")
        self.assertEqual(payload["persistence_action"], "created")
        self.assertEqual(self.proposal_writes[0]["domain"], "personal")
        self.assertRegex(
            self.proposal_writes[0]["source_reference"],
            rf"^{self.annotation_chunks[0].chunk_id}:candidate:[0-9a-f]{{64}}$",
        )
        self.assertEqual(self.proposal_writes[0]["observation_text"], self.annotation_chunks[0].text)
        self.assertEqual(self.session.calls, [])

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

if __name__ == "__main__":
    unittest.main()
