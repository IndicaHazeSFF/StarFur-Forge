"""
title: StarFur reviewed document bridge
author: StarFur Forge
version: 0.1.0
required_open_webui_version: 0.6.0
description: Routes one supported OpenWebUI upload through StarFur's reviewed document-intake boundary.
requirements: pydantic

Install this file as an OpenWebUI Filter and attach it only to the
``starfur-assistant`` model. It deliberately owns file handling for that
model, so OpenWebUI's built-in RAG does not inject attachment text separately.

The bridge is self-contained because OpenWebUI Functions run in the OpenWebUI
process, not in the StarFur source tree.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import json
from pathlib import PurePosixPath
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pydantic import BaseModel


# OpenWebUI reads this at module import time. It must not be moved to the
# Filter instance: with this enabled OpenWebUI removes attachment references
# after inlet(), leaving StarFur as the sole document-context owner.
file_handler = True

SUPPORTED_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
DEFAULT_MAX_SOURCE_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_API_RESPONSE_BYTES = 8 * 1024 * 1024
_REVIEW_ID_RE = r"DR-[0-9a-f]{32}"
_CANDIDATE_ID_RE = r"C-\d{3}"


class DocumentBridgeError(RuntimeError):
    """A bounded, presentation-safe bridge failure."""


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = True
        STARFUR_BASE_URL: str = "http://host.docker.internal:8001"
        STARFUR_API_KEY: str = ""
        DOMAIN: str = "personal"
        DOCUMENT_CONTEXT_LIMIT: int = 3
        REVIEW_CACHE_SECONDS: int = 14 * 60
        MAX_SOURCE_BYTES: int = DEFAULT_MAX_SOURCE_BYTES
        REQUEST_TIMEOUT_SECONDS: int = 180
        # OpenWebUI's backend listens on 8080 inside its container. Override
        # this for a native install or a reverse proxy with a different port.
        OPENWEBUI_BASE_URL: str = "http://localhost:8080"

    def __init__(self) -> None:
        self.valves = self.Valves()
        # file-id + StarFur configuration -> (monotonic expiry, review id,
        # candidate count). It is intentionally in-memory, bounded, and
        # shorter than StarFur review expiry. A restart simply re-annotates.
        self._review_cache: OrderedDict[str, tuple[float, str, int]] = OrderedDict()

    @staticmethod
    def _as_mappings(value: object) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    @classmethod
    def _attachment_references(cls, body: dict[str, Any]) -> list[dict[str, Any]]:
        """Return stable, de-duplicated file references present at Filter inlet."""
        metadata = body.get("metadata")
        sources: list[object] = []
        if isinstance(metadata, dict):
            sources.append(metadata.get("files"))
        sources.append(body.get("files"))
        references: list[dict[str, Any]] = []
        seen: set[str] = set()
        for source in sources:
            for item in cls._as_mappings(source):
                file_id = cls._file_id(item)
                if not file_id or file_id in seen:
                    continue
                seen.add(file_id)
                references.append(item)
        return references

    @staticmethod
    def _strip_attachment_references(body: dict[str, Any]) -> None:
        """Prevent OpenWebUI versions without effective file_handler support from running RAG too."""
        metadata = body.get("metadata")
        if isinstance(metadata, dict) and "files" in metadata:
            metadata["files"] = []
        if "files" in body:
            body["files"] = []

    @staticmethod
    def _latest_user_text(body: dict[str, Any]) -> str:
        messages = body.get("messages")
        if not isinstance(messages, list):
            return ""
        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
        return ""

    @staticmethod
    def _candidate_ids(text: str) -> list[str] | None:
        values = text.split()
        if not values or any(not re.fullmatch(_CANDIDATE_ID_RE, value, flags=re.IGNORECASE) for value in values):
            return None
        normalized = [value.upper() for value in values]
        return normalized if len(set(normalized)) == len(normalized) else None

    def _review_command(self, body: dict[str, Any]) -> dict[str, Any] | None:
        """Recognize small explicit commands before a model sees them.

        Review IDs are intentionally included in command syntax because the
        server remains restart/expiry-safe and does not infer a review from an
        OpenWebUI chat identity.  The command is converted to a controlled API
        extension; the model never decides what gets persisted.
        """
        text = self._latest_user_text(body)
        show = re.fullmatch(rf"document\s+review\s+({_REVIEW_ID_RE})", text, flags=re.IGNORECASE)
        if show:
            return {"action": "show", "review_id": show.group(1)}
        action = re.fullmatch(rf"document\s+(approve|reject)\s+({_REVIEW_ID_RE})\s+(.+)", text, flags=re.IGNORECASE)
        if not action:
            return None
        candidate_ids = self._candidate_ids(action.group(3))
        if candidate_ids is None:
            return None
        if action.group(1).casefold() == "approve":
            return {
                "action": "approve",
                "review_id": action.group(2),
                "candidate_ids": candidate_ids,
                "confirm": "create pending proposals",
            }
        return {
            "action": "reject",
            "review_id": action.group(2),
            "candidate_ids": candidate_ids,
            "confirm": "reject document candidates",
        }

    @staticmethod
    def _file_id(reference: dict[str, Any]) -> str | None:
        candidates = (reference, reference.get("file"), reference.get("data"))
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for field in ("id", "file_id"):
                value = candidate.get(field)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _file_name(reference: dict[str, Any]) -> str | None:
        candidates = (reference, reference.get("file"), reference.get("data"))
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for field in ("name", "filename"):
                value = candidate.get(field)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _bounded_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            raise DocumentBridgeError(f"{name} must be an integer.")
        try:
            result = int(value)
        except (TypeError, ValueError) as error:
            raise DocumentBridgeError(f"{name} must be an integer.") from error
        if not minimum <= result <= maximum:
            raise DocumentBridgeError(f"{name} must be between {minimum} and {maximum}.")
        return result

    @staticmethod
    def _request_origin(request: object) -> str:
        base_url = getattr(request, "base_url", None)
        if base_url is None:
            raise DocumentBridgeError("OpenWebUI request origin is unavailable.")
        origin = str(base_url).rstrip("/")
        if not origin.startswith(("http://", "https://")):
            raise DocumentBridgeError("OpenWebUI request origin is not an HTTP URL.")
        return origin

    @staticmethod
    def _read_bounded(response: Any, *, maximum: int) -> bytes:
        data = response.read(maximum + 1)
        if len(data) > maximum:
            raise DocumentBridgeError("Response exceeds the configured bridge size limit.")
        return data

    def _openwebui_base_url(self, request: object) -> str:
        configured = self.valves.OPENWEBUI_BASE_URL.strip()
        if configured:
            if not configured.startswith(("http://", "https://")):
                raise DocumentBridgeError("OPENWEBUI_BASE_URL must be an HTTP URL.")
            return configured.rstrip("/")
        return self._request_origin(request)

    def _download_file(self, reference: dict[str, Any], request: object) -> tuple[str, str]:
        file_id = self._file_id(reference)
        filename = self._file_name(reference)
        if not file_id or not filename:
            raise DocumentBridgeError("Attachment is missing an OpenWebUI file ID or filename.")
        suffix = PurePosixPath(filename).suffix.casefold()
        if suffix not in SUPPORTED_SUFFIXES:
            raise DocumentBridgeError("Only .md, .markdown, and .txt attachments are supported by this bridge.")
        headers: dict[str, str] = {}
        request_headers = getattr(request, "headers", {})
        for source_name, target_name in (("authorization", "Authorization"), ("cookie", "Cookie")):
            value = request_headers.get(source_name) if hasattr(request_headers, "get") else None
            if isinstance(value, str) and value:
                headers[target_name] = value
        url = f"{self._openwebui_base_url(request)}/api/v1/files/{quote(file_id, safe='')}/content"
        timeout = self._bounded_int(self.valves.REQUEST_TIMEOUT_SECONDS, name="REQUEST_TIMEOUT_SECONDS", minimum=1, maximum=600)
        maximum = self._bounded_int(self.valves.MAX_SOURCE_BYTES, name="MAX_SOURCE_BYTES", minimum=1, maximum=DEFAULT_MAX_SOURCE_BYTES)
        try:
            with urlopen(Request(url, headers=headers, method="GET"), timeout=timeout) as response:
                raw = self._read_bounded(response, maximum=maximum)
        except HTTPError as error:
            raise DocumentBridgeError(f"OpenWebUI could not provide the attachment (HTTP {error.code}).") from error
        except URLError as error:
            reason = str(getattr(error, "reason", "unreachable"))
            raise DocumentBridgeError(f"OpenWebUI attachment download failed ({reason}); check OPENWEBUI_BASE_URL.") from error
        try:
            return filename, raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise DocumentBridgeError("Attachment must be UTF-8 text.") from error

    def _starfur_url(self, path: str) -> str:
        base_url = self.valves.STARFUR_BASE_URL.strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise DocumentBridgeError("STARFUR_BASE_URL must be an HTTP URL.")
        return base_url + path

    def _starfur_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        timeout = self._bounded_int(self.valves.REQUEST_TIMEOUT_SECONDS, name="REQUEST_TIMEOUT_SECONDS", minimum=1, maximum=600)
        api_key = self.valves.STARFUR_API_KEY.strip()
        if not api_key:
            raise DocumentBridgeError("STARFUR_API_KEY is required when the StarFur API requires bearer authentication.")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            with urlopen(Request(self._starfur_url(path), data=body, headers=headers, method="POST"), timeout=timeout) as response:
                raw = self._read_bounded(response, maximum=DEFAULT_MAX_API_RESPONSE_BYTES)
        except HTTPError as error:
            raise DocumentBridgeError(f"StarFur document intake failed (HTTP {error.code}).") from error
        except URLError as error:
            reason = str(getattr(error, "reason", "unreachable"))
            raise DocumentBridgeError(f"StarFur document intake is unavailable ({reason}); check STARFUR_BASE_URL.") from error
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DocumentBridgeError("StarFur document intake returned invalid JSON.") from error
        if not isinstance(value, dict):
            raise DocumentBridgeError("StarFur document intake returned an invalid response.")
        return value

    def _cache_key(self, reference: dict[str, Any]) -> str:
        file_id = self._file_id(reference)
        if not file_id:
            raise DocumentBridgeError("Attachment is missing an OpenWebUI file ID.")
        return "|".join((file_id, self.valves.DOMAIN.strip(), self.valves.STARFUR_BASE_URL.strip().rstrip("/")))

    def _cached_review(self, key: str) -> tuple[str, int] | None:
        now = time.monotonic()
        cached = self._review_cache.get(key)
        if cached is None:
            return None
        expires_at, review_id, candidate_count = cached
        if expires_at <= now:
            del self._review_cache[key]
            return None
        self._review_cache.move_to_end(key)
        return review_id, candidate_count

    def _remember_review(self, key: str, review_id: str, candidate_count: int) -> None:
        ttl = self._bounded_int(self.valves.REVIEW_CACHE_SECONDS, name="REVIEW_CACHE_SECONDS", minimum=1, maximum=14 * 60)
        self._review_cache[key] = (time.monotonic() + ttl, review_id, candidate_count)
        self._review_cache.move_to_end(key)
        while len(self._review_cache) > 32:
            self._review_cache.popitem(last=False)

    async def _emit(self, emitter: object, description: str, *, done: bool) -> None:
        if emitter is None:
            return
        payload = {"type": "status", "data": {"description": description, "done": done}}
        try:
            result = emitter(payload)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            # Progress reporting cannot change document safety or turn behavior.
            return

    async def inlet(self, body: dict[str, Any], __request__=None, __event_emitter__=None, __user__=None, __model__=None) -> dict[str, Any]:
        """Create/reuse one reviewed source, then bind its ID to this chat turn.

        Raw attachment text is never appended to ``messages``. StarFur derives
        source retrieval from the actual latest user message after its normal
        API adapter validates domain and review lifetime.
        """
        del __user__, __model__  # UI identity must never become a domain/source identity.
        if not isinstance(body, dict) or not self.valves.ENABLED:
            return body
        review_command = self._review_command(body)
        if review_command is not None:
            self._strip_attachment_references(body)
            body["starfur_document_review"] = review_command
            await self._emit(__event_emitter__, "StarFur document bridge: handling explicit reviewed-document command.", done=True)
            return body
        if "starfur_document_context" in body:
            self._strip_attachment_references(body)
            await self._emit(__event_emitter__, "StarFur document bridge: preserving existing reviewed context.", done=True)
            return body
        references = self._attachment_references(body)
        if not references:
            return body
        # file_handler=True is the documented switch. Clearing the references
        # here as well makes the no-double-RAG guarantee hold on older/custom
        # OpenWebUI builds that still process files after inlet().
        self._strip_attachment_references(body)
        if len(references) != 1:
            await self._emit(__event_emitter__, "StarFur document bridge: attach exactly one supported text file per turn.", done=True)
            return body
        if __request__ is None:
            await self._emit(__event_emitter__, "StarFur document bridge: OpenWebUI request context is unavailable.", done=True)
            return body

        reference = references[0]
        try:
            limit = self._bounded_int(self.valves.DOCUMENT_CONTEXT_LIMIT, name="DOCUMENT_CONTEXT_LIMIT", minimum=1, maximum=8)
            key = self._cache_key(reference)
            cached = self._cached_review(key)
            if cached is None:
                await self._emit(__event_emitter__, "StarFur document bridge: preparing attachment...", done=False)
                filename, content = await asyncio.to_thread(self._download_file, reference, __request__)
                annotation = await asyncio.to_thread(
                    self._starfur_json,
                    "/v1/starfur/documents/annotate",
                    {"filename": filename, "content": content, "domain": self.valves.DOMAIN.strip()},
                )
                review = annotation.get("review")
                review_id = review.get("id") if isinstance(review, dict) else None
                candidate_count = review.get("candidate_count") if isinstance(review, dict) else None
                if not isinstance(review_id, str) or not review_id.startswith("DR-"):
                    raise DocumentBridgeError("StarFur document intake did not return an active review ID.")
                if isinstance(candidate_count, bool) or not isinstance(candidate_count, int) or candidate_count < 0:
                    raise DocumentBridgeError("StarFur document intake returned an invalid review count.")
                self._remember_review(key, review_id, candidate_count)
                cached = (review_id, candidate_count)
            review_id, candidate_count = cached
            body["starfur_document_context"] = {"review_id": review_id, "limit": limit}
            await self._emit(
                __event_emitter__,
                f"StarFur document bridge: review {review_id} ready ({candidate_count} proposal candidate(s), not persisted).",
                done=True,
            )
        except DocumentBridgeError as error:
            await self._emit(__event_emitter__, f"StarFur document bridge: {error}", done=True)
        except Exception:
            # Do not leak implementation details or fall back to implicit RAG.
            await self._emit(__event_emitter__, "StarFur document bridge: attachment processing failed safely.", done=True)
        return body
