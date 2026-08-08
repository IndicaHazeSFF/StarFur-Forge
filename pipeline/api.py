"""Local OpenAI-compatible adapter for external chat UIs.

This intentionally exposes chat/model/health endpoints plus isolated document preparation/review. StarFur remains the
owner of persona, retrieval, policy, proposals, and session state.
"""

from __future__ import annotations

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from pipeline.assistant import GenerationInterrupted
from pipeline.application import AssistantApplication, create_assistant_application
from pipeline.document_review import DocumentReviewError, DocumentReviewStore, candidate_public_id, review_public_payload
from pipeline.document_intake import (
    DEFAULT_MAX_DOCUMENT_BYTES,
    DocumentAnnotationError,
    DocumentIntakeError,
    prepare_document_text,
)


API_MODEL_ID = "starfur-assistant"
CONVERSATION_HEADER = "X-StarFur-Conversation"
DOCUMENT_PREPARE_PATH = "/v1/starfur/documents/prepare"
DOCUMENT_ANNOTATE_PATH = "/v1/starfur/documents/annotate"
DOCUMENT_REVIEW_PATH = "/v1/starfur/documents/review"
MAX_DOCUMENT_REQUEST_BYTES = DEFAULT_MAX_DOCUMENT_BYTES * 6 + 64 * 1024


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _content_from_message(message):
    content = message.get("content", "") if isinstance(message, dict) else ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content or "")


def _conversation_id_from_request(payload, header_value=None):
    """Resolve an opaque session key without using it for authorization.

    A StarFur-specific header is preferred for frontends that know a stable
    chat identifier. The documented ``conversation_id`` extension is next,
    followed by OpenAI's standard ``user`` field. Omission preserves the
    legacy default session.
    """
    if header_value is not None:
        return header_value
    if not isinstance(payload, dict):
        return None
    if "conversation_id" in payload:
        return payload["conversation_id"]
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and "starfur_conversation_id" in metadata:
        return metadata["starfur_conversation_id"]
    return payload.get("user")


class StarFurAPI:
    """OpenAI-compatible request adapter over a shared application facade."""

    def __init__(self, application_or_session, *, api_key=None, model_id=API_MODEL_ID, document_annotator=None, document_review_store=None):
        self.application = (
            application_or_session
            if isinstance(application_or_session, AssistantApplication)
            else AssistantApplication(application_or_session)
        )
        # Retained for injected-session compatibility with existing callers/tests.
        self.session = self.application.session
        self.api_key = api_key
        self.model_id = model_id
        # Optional injection keeps the document-review boundary service-free in tests.
        self.document_annotator = document_annotator
        self.document_review_store = document_review_store or DocumentReviewStore()

    def authenticate(self, headers):
        if not self.api_key:
            return True
        return headers.get("Authorization", "") == f"Bearer {self.api_key}"

    def models(self, *, conversation_id=None):
        active = self.application.active_model_for(conversation_id)
        return {
            "object": "list",
            "data": [{"id": self.model_id, "object": "model", "owned_by": "starfur", "active_backend": active}],
        }

    def _prepared_document(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        allowed = {"filename", "content", "domain"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Unknown document-preparation field(s): {sorted(unknown)}")
        if "filename" not in payload or "content" not in payload:
            raise ValueError("Document request requires filename and content.")
        return prepare_document_text(
            payload["content"],
            payload["filename"],
            domain=payload.get("domain", "personal"),
        )

    @staticmethod
    def _document_source_payload(document):
        return {
            "id": document.source_id,
            "name": document.source_name,
            "kind": document.source_kind,
            "domain": document.domain,
            "byte_count": document.byte_count,
            "chunk_count": len(document.chunks),
        }

    def prepare_document(self, payload):
        """Prepare external text without invoking chat, annotation, or storage."""
        document = self._prepared_document(payload)
        return {
            "object": "starfur.document.preparation",
            "source": self._document_source_payload(document),
            "chunks": [
                {
                    "id": chunk.chunk_id,
                    "scene_index": chunk.scene_index,
                    "chunk_index": chunk.chunk_index,
                    "heading": chunk.heading,
                    "character_count": len(chunk.text),
                }
                for chunk in document.chunks
            ],
        }

    def annotate_document(self, payload):
        """Return reviewable candidates plus bounded per-chunk failures."""
        document = self._prepared_document(payload)
        annotation = self.application.annotate_document(
            document, annotator=self.document_annotator,
        )
        candidates = annotation.candidates
        review = self.document_review_store.create(document, candidates)
        return {
            "object": "starfur.document.annotation",
            "source": self._document_source_payload(document),
            "review": review_public_payload(review),
            "failures": [
                {
                    "chunk_id": failure.chunk_id,
                    "scene_index": failure.scene_index,
                    "chunk_index": failure.chunk_index,
                    "attempts": failure.attempts,
                    "reason": failure.reason,
                }
                for failure in annotation.failures
            ],
            "candidates": [
                {
                    "id": candidate_public_id(index),
                    "proposal": dict(candidate.proposal),
                    "provenance": {
                        "source": candidate.proposal["source"],
                        "source_id": candidate.source_id,
                        "source_reference": candidate.source_reference,
                        "chunk_id": candidate.chunk_id,
                        "observation_characters": len(candidate.observation_text),
                    },
                }
                for index, candidate in enumerate(candidates)
            ],
        }
    def create_document_pending_proposal(self, payload):
        """Persist one selected review candidate as a normal pending proposal."""
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        allowed = {"review_id", "candidate_id", "confirm"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Unknown document-review field(s): {sorted(unknown)}")
        if payload.get("confirm") != "create pending proposal":
            raise ValueError("Document proposal handoff requires confirm='create pending proposal'.")
        candidate = self.document_review_store.get_candidate(
            payload.get("review_id"), payload.get("candidate_id"),
        )
        result = self.application.create_document_pending_proposal(candidate)
        return {
            "object": "starfur.document.proposal_handoff",
            "review_id": payload["review_id"],
            "candidate_id": payload["candidate_id"],
            "proposal_id": result["proposal_id"],
            "proposal_status": "pending",
            "persistence_action": result["action"],
            "evidence_count": result["evidence_count"],
        }

    def complete(self, payload, *, stream_writer=None, conversation_id=None):
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list.")
        user_messages = [message for message in messages if isinstance(message, dict) and message.get("role") == "user"]
        if not user_messages:
            raise ValueError("messages must contain a user message.")
        user_text = _content_from_message(user_messages[-1]).strip()
        if not user_text:
            raise ValueError("The latest user message is empty.")
        requested_model = payload.get("model")
        if requested_model not in (None, self.model_id):
            raise ValueError(f"Unknown StarFur model: {requested_model}")
        resolved_conversation = _conversation_id_from_request(payload, conversation_id)
        content = self.application.respond(
            user_text,
            stream_writer=stream_writer,
            conversation_id=resolved_conversation,
        )
        active = self.application.active_model_for(resolved_conversation)
        return {"content": content or "", "model": active}


class _Handler(BaseHTTPRequestHandler):
    server_version = "StarFurAPI/1.0"

    def log_message(self, format, *args):  # noqa: A002
        if getattr(self.server, "quiet", False):
            return
        super().log_message(format, *args)

    @property
    def api(self):
        return self.server.api

    def _send_json(self, status, payload):
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        if self.api.authenticate(self.headers):
            return True
        self._send_json(401, {"error": {"message": "Unauthorized", "type": "authentication_error"}})
        return False

    def do_GET(self):  # noqa: N802
        if not self._authorized():
            return
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "starfur"})
        elif self.path == "/v1/models":
            try:
                self._send_json(200, self.api.models(conversation_id=self.headers.get(CONVERSATION_HEADER)))
            except ValueError as error:
                self._send_json(400, {"error": {"message": str(error), "type": "invalid_request_error"}})
        elif self.path == "/v1/starfur/diagnostics":
            try:
                self._send_json(200, self.api.application.runtime_diagnostics(conversation_id=self.headers.get(CONVERSATION_HEADER)))
            except ValueError as error:
                self._send_json(400, {"error": {"message": str(error), "type": "invalid_request_error"}})
        else:
            self._send_json(404, {"error": {"message": "Not found", "type": "invalid_request_error"}})

    def do_POST(self):  # noqa: N802
        if not self._authorized():
            return
        if self.path not in {"/v1/chat/completions", DOCUMENT_PREPARE_PATH, DOCUMENT_ANNOTATE_PATH, DOCUMENT_REVIEW_PATH}:
            self._send_json(404, {"error": {"message": "Not found", "type": "invalid_request_error"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0:
                raise ValueError("Content-Length must not be negative.")
            if self.path in {DOCUMENT_PREPARE_PATH, DOCUMENT_ANNOTATE_PATH} and length > MAX_DOCUMENT_REQUEST_BYTES:
                self._send_json(413, {"error": {"message": "Document request exceeds the intake transport limit.", "type": "invalid_request_error"}})
                return
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": {"message": f"Invalid JSON request: {error}", "type": "invalid_request_error"}})
            return
        if self.path in {DOCUMENT_PREPARE_PATH, DOCUMENT_ANNOTATE_PATH, DOCUMENT_REVIEW_PATH}:
            try:
                if self.path == DOCUMENT_PREPARE_PATH:
                    result = self.api.prepare_document(payload)
                elif self.path == DOCUMENT_ANNOTATE_PATH:
                    result = self.api.annotate_document(payload)
                else:
                    result = self.api.create_document_pending_proposal(payload)
            except DocumentReviewError as error:
                self._send_json(404, {"error": {"message": str(error), "type": "document_review_not_found"}})
                return
            except DocumentAnnotationError as error:
                self._send_json(422, {"error": {"message": str(error), "type": "document_annotation_error"}})
                return
            except (ValueError, DocumentIntakeError) as error:
                self._send_json(400, {"error": {"message": str(error), "type": "invalid_request_error"}})
                return
            except RuntimeError as error:
                self._send_json(503, {"error": {"message": str(error), "type": "provider_unavailable"}})
                return
            self._send_json(200, result)
            return

        stream = bool(payload.get("stream", False))
        request_id = "chatcmpl-" + uuid.uuid4().hex
        created = int(time.time())
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            wrote_content = {"value": False}

            def write_chunk(text):
                if not text:
                    return
                wrote_content["value"] = True
                chunk = {"id": request_id, "object": "chat.completion.chunk", "created": created, "model": self.api.model_id, "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}]}
                self.wfile.write(b"data: " + _json_bytes(chunk) + b"\n\n")
                self.wfile.flush()

            try:
                result = self.api.complete(
                    payload,
                    stream_writer=write_chunk,
                    conversation_id=self.headers.get(CONVERSATION_HEADER),
                )
                if not wrote_content["value"] and result["content"]:
                    write_chunk(result["content"])
                finish = {"id": request_id, "object": "chat.completion.chunk", "created": created, "model": result["model"], "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                self.wfile.write(b"data: " + _json_bytes(finish) + b"\n\ndata: [DONE]\n\n")
                self.wfile.flush()
            except (GenerationInterrupted, BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:
                error_payload = {"error": {"message": str(error), "type": "server_error"}}
                try:
                    self.wfile.write(b"data: " + _json_bytes(error_payload) + b"\n\ndata: [DONE]\n\n")
                    self.wfile.flush()
                except OSError:
                    pass
            return
        try:
            result = self.api.complete(
                payload,
                conversation_id=self.headers.get(CONVERSATION_HEADER),
            )
        except ValueError as error:
            self._send_json(400, {"error": {"message": str(error), "type": "invalid_request_error"}})
            return
        except Exception as error:
            self._send_json(500, {"error": {"message": str(error), "type": "server_error"}})
            return
        self._send_json(200, {"id": request_id, "object": "chat.completion", "created": created, "model": result["model"], "choices": [{"index": 0, "message": {"role": "assistant", "content": result["content"]}, "finish_reason": "stop"}]})


class StarFurHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address, api, *, quiet=False):
        super().__init__(address, _Handler)
        self.api = api
        self.quiet = quiet


def create_api_session(config_path=None, *, stream=False):
    """Compatibility factory for callers that still need the underlying session."""
    return create_api_application(config_path, stream=stream).session


def create_api_application(config_path=None, *, stream=False):
    """Create the shared assistant application used by the local API server."""
    return create_assistant_application(config_path, stream=stream)


def serve(*, host="127.0.0.1", port=8000, config_path=None, api_key=None, quiet=False):
    application = create_api_application(config_path)
    server = StarFurHTTPServer((host, port), StarFurAPI(application, api_key=api_key), quiet=quiet)
    print(f"StarFur API listening at http://{host}:{port}")
    print(f"OpenAI-compatible endpoint: http://{host}:{port}/v1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStarFur API stopped.")
    finally:
        server.server_close()


__all__ = ["API_MODEL_ID", "CONVERSATION_HEADER", "DOCUMENT_ANNOTATE_PATH", "DOCUMENT_PREPARE_PATH", "DOCUMENT_REVIEW_PATH", "StarFurAPI", "StarFurHTTPServer", "create_api_application", "create_api_session", "serve"]
