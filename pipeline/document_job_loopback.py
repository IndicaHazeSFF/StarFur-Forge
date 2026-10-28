"""Opt-in direct loopback annotation transport, disconnected from commands.

Trusted Core assembly supplies independently verified locality evidence. This
adapter does not verify an Ollama deployment, inspect environment/service state,
grant consent, discover/download models, redirect, proxy, or select fallback.
Tests inject a trusted fake connection; in-process adapters are not isolation.
"""

from http.client import HTTPConnection
from dataclasses import dataclass, field
import json
import sys
import time

from pipeline.document_job_locality import LocalAnnotationTarget, evaluate_annotation_locality
from pipeline.providers import ChatCompletion


MAX_LOCAL_REQUEST_BYTES = 64 * 1024
MAX_LOCAL_RESPONSE_BYTES = 256 * 1024
LOCAL_REQUEST_TIMEOUT_SECONDS = 30


class AnnotationLoopbackError(RuntimeError):
    """Closed content-free private annotation transport failure."""


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


@dataclass(frozen=True, init=False, repr=False, eq=False)
class LoopbackAnnotationProvider:
    """Completion-only trusted adapter, not the default resident chat provider.

    No constructor/call performs probes or grants disclosure authority. Claimed
    model digest/locality is checked for equality but not independently measured
    here. Backend verification and exact job consent remain external gates.
    """
    name = "Ollama"
    supports_model_thinking = True
    supports_model_keep_alive_seconds = True
    _target: LocalAnnotationTarget = field(repr=False)
    _model: str = field(repr=False)
    _evidence: object = field(repr=False)
    _connection_factory: object = field(repr=False)

    def __init__(self, target, model, evidence=None, *, _connection_factory=None):
        if type(target) is not LocalAnnotationTarget:
            raise AnnotationLoopbackError("private annotation transport is unavailable")
        try:
            decision = evaluate_annotation_locality(target, model, evidence)
        except ValueError:
            raise AnnotationLoopbackError("private annotation locality is unverified") from None
        if decision.status != "eligible":
            raise AnnotationLoopbackError("private annotation locality is unverified")
        factory = HTTPConnection if _connection_factory is None else _connection_factory
        if not callable(factory):
            raise AnnotationLoopbackError("private annotation transport is unavailable")
        for name, value in (("_target", target), ("_model", model), ("_evidence", evidence),
                            ("_connection_factory", factory)):
            object.__setattr__(self, name, value)

    def list_models(self):
        raise NotImplementedError("private annotation transport does not discover models")

    def probe_health(self):
        raise NotImplementedError("private annotation transport does not probe")

    def complete(self, messages, *, model=None, options=None, stream=False,
                 keep_alive_seconds=None, thinking=None):
        connection = None
        response = None
        try:
            if (model != self._model or stream is not False
                    or evaluate_annotation_locality(self._target, self._model, self._evidence).status != "eligible"
                    or not isinstance(messages, (list, tuple)) or not 1 <= len(messages) <= 8):
                raise ValueError
            copied = []
            for item in messages:
                if (type(item) is not dict or set(item) != {"role", "content"}
                        or item["role"] not in {"system", "user", "assistant"}
                        or not isinstance(item["content"], str)):
                    raise ValueError
                copied.append(dict(item))
            payload = {"model": self._model, "messages": copied, "stream": False}
            generation = {"num_predict": 1024}
            if options is not None:
                if type(options) is not dict or set(options) - {"temperature", "top_k", "top_p", "seed", "num_ctx", "num_predict"}:
                    raise ValueError
                if any(type(value) not in {int, float} for value in options.values()):
                    raise ValueError
                generation.update(options)
            if (type(generation["num_predict"]) is not int or not 1 <= generation["num_predict"] <= 1024
                    or ("num_ctx" in generation and (type(generation["num_ctx"]) is not int
                        or not 1 <= generation["num_ctx"] <= 32768))):
                raise ValueError
            payload["options"] = generation
            if thinking is not None:
                if type(thinking) is not bool:
                    raise ValueError
                payload["think"] = thinking
            if keep_alive_seconds is not None:
                if type(keep_alive_seconds) is not int or not 0 <= keep_alive_seconds <= 86400:
                    raise ValueError
                payload["keep_alive"] = keep_alive_seconds
            encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(encoded) > MAX_LOCAL_REQUEST_BYTES:
                raise ValueError
            # Canonical literal target avoids DNS aliases. HTTPConnection does
            # not consult HTTP(S)_PROXY, OLLAMA_HOST, auth/cookie environments
            # or redirect handlers. No caller can supply headers/path/transport.
            from urllib.parse import urlsplit
            endpoint = urlsplit(self._target.endpoint)
            started = time.monotonic()
            def remaining():
                value = LOCAL_REQUEST_TIMEOUT_SECONDS - (time.monotonic() - started)
                if value <= 0:
                    raise TimeoutError
                return value
            connection = self._connection_factory(endpoint.hostname, endpoint.port, timeout=LOCAL_REQUEST_TIMEOUT_SECONDS)
            connection.connect()
            # Retain the socket handle even when HTTPConnection transfers
            # response ownership on Connection: close. Rebind each read to
            # remaining acceptance time; do not let trickled data reset it.
            wire = connection.sock
            wire.settimeout(remaining())
            connection.request("POST", "/api/chat", body=encoded,
                               headers={"Content-Type": "application/json", "Accept": "application/json",
                                        "Accept-Encoding": "identity", "Connection": "close"})
            wire.settimeout(remaining())
            response = connection.getresponse()
            if (response.status != 200 or response.getheader("Content-Encoding", "identity").strip().lower() != "identity"
                    or response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json"):
                raise ValueError
            parts, size = [], 0
            while True:
                wire.settimeout(remaining())
                part = response.read1(min(16384, MAX_LOCAL_RESPONSE_BYTES + 1 - size))
                if not part:
                    break
                size += len(part)
                if size > MAX_LOCAL_RESPONSE_BYTES:
                    raise ValueError
                parts.append(part)
            remaining()
            raw = b"".join(parts)
            result = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                                parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
            if (type(result) is not dict or result.get("done") is not True or result.get("error")
                    or result.get("model") != self._model
                    or type(result.get("message")) is not dict
                    or not isinstance(result["message"].get("content"), str)):
                raise ValueError
            # Only answer content and a closed finish reason enter Core. The
            # server's thinking/timing/resource/error payloads are never exposed.
            reason = result.get("done_reason")
            reason = reason if reason in {"stop", "length"} else "unknown" if reason else None
            return ChatCompletion(result["message"]["content"], reason)
        except Exception:
            raise AnnotationLoopbackError("private annotation request failed safely") from None
        finally:
            active_error = sys.exc_info()[0] is not None
            cleanup_failed = False
            for resource in (response, connection):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        cleanup_failed = True
            if cleanup_failed and not active_error:
                raise AnnotationLoopbackError("private annotation cleanup failed safely") from None
