"""Local OpenAI-compatible adapter for external chat UIs.

This intentionally exposes only chat/model/health endpoints. StarFur remains the
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


API_MODEL_ID = "starfur-assistant"


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


class StarFurAPI:
    """OpenAI-compatible request adapter over a shared application facade."""

    def __init__(self, application_or_session, *, api_key=None, model_id=API_MODEL_ID):
        self.application = (
            application_or_session
            if isinstance(application_or_session, AssistantApplication)
            else AssistantApplication(application_or_session)
        )
        # Retained for injected-session compatibility with existing callers/tests.
        self.session = self.application.session
        self.api_key = api_key
        self.model_id = model_id

    def authenticate(self, headers):
        if not self.api_key:
            return True
        return headers.get("Authorization", "") == f"Bearer {self.api_key}"

    def models(self):
        active = self.application.active_model
        return {
            "object": "list",
            "data": [{"id": self.model_id, "object": "model", "owned_by": "starfur", "active_backend": active}],
        }

    def complete(self, payload, *, stream_writer=None):
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
        content = self.application.respond(user_text, stream_writer=stream_writer)
        active = self.application.active_model
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
            self._send_json(200, self.api.models())
        else:
            self._send_json(404, {"error": {"message": "Not found", "type": "invalid_request_error"}})

    def do_POST(self):  # noqa: N802
        if not self._authorized():
            return
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": {"message": "Not found", "type": "invalid_request_error"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": {"message": f"Invalid JSON request: {error}", "type": "invalid_request_error"}})
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
                result = self.api.complete(payload, stream_writer=write_chunk)
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
            result = self.api.complete(payload)
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


__all__ = ["API_MODEL_ID", "StarFurAPI", "StarFurHTTPServer", "create_api_application", "create_api_session", "serve"]