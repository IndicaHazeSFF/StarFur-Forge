import http.client
import json
import sys
import threading
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.api import API_MODEL_ID, DOCUMENT_ANNOTATE_PATH, DOCUMENT_PREPARE_PATH, StarFurAPI, StarFurHTTPServer


class FakeConfig:
    chat_model = "qwen3:8b"


class FakeSession:
    def __init__(self):
        self.config = FakeConfig()
        self.active_model = "qwen3:8b"
        self.stream = False
        self.stream_writer = None
        self.calls = []

    def respond(self, text):
        self.calls.append(text)
        if self.stream and self.stream_writer:
            self.stream_writer("streamed answer")
        return "streamed answer" if self.stream else "normal answer"


class APITests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.annotation_chunks = []

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
            self.session,
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

    def request(self, method, path, body=None, *, auth=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer local-test"
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

    def test_document_annotation_is_authenticated_and_reports_invalid_model_output(self):
        status, _ = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md", "content": "text",
        }, auth=False)
        self.assertEqual(status, 401)
        self.api.document_annotator = lambda _chunk: {"proposals": "not a list"}
        status, raw = self.request("POST", DOCUMENT_ANNOTATE_PATH, {
            "filename": "notes.md", "content": "text",
        })
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(raw)["error"]["type"], "document_annotation_error")
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