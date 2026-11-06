"""Inert private-worker wire data; no transport, consent, identity or execution.

IDs correlate bytes only. A decoded request is NOT an admission/dispatch token.
Core must burn exact-attempt consent before sending any encoded private bytes.
Platform adapters must authenticate their channel independently; never accept
executor, URL, path, grant or provider-selection instructions from this schema.
"""
from dataclasses import dataclass
import json
import re

POLICY = "annotation-worker-wire-v1"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESULT_BYTES = 256 * 1024
_ID = re.compile(r"[0-9a-f]{32}")
_MODEL = re.compile(r"[a-z0-9][a-z0-9._-]{0,62}:[a-z0-9][a-z0-9._-]{0,62}")


class WorkerProtocolError(ValueError):
    """Content-free refusal; never include private wire values."""


def _deny():
    raise WorkerProtocolError("private worker message is invalid") from None


def _identity(epoch, dispatch):
    if any(type(v) is not str or _ID.fullmatch(v) is None for v in (epoch, dispatch)):
        _deny()


def _text(value, ceiling):
    if type(value) is not str or len(value) > ceiling:
        _deny()
    try:
        if len(value.encode("utf-8")) > ceiling:
            _deny()
    except UnicodeError:
        _deny()


def _model(value):
    if (type(value) is not str or len(value) > 128 or _MODEL.fullmatch(value) is None
            or "cloud" in re.split(r"[:._-]", value)):
        _deny()


@dataclass(frozen=True, repr=False)
class WorkerRequest:
    """Private data only; model is the already Core-selected exact short name."""
    epoch: str
    dispatch: str
    model: str
    system_text: str
    chunk_text: str
    context_size: int
    max_output_tokens: int

    def __post_init__(self):
        _identity(self.epoch, self.dispatch)
        _model(self.model)
        _text(self.system_text, MAX_REQUEST_BYTES)
        _text(self.chunk_text, MAX_REQUEST_BYTES)
        if not self.system_text.strip() or not self.chunk_text.strip():
            _deny()
        if (type(self.context_size) is not int or not 1 <= self.context_size <= 32768
                or type(self.max_output_tokens) is not int
                or not 1 <= self.max_output_tokens <= 1024):
            _deny()
        _dump(_request_object(self), MAX_REQUEST_BYTES)


@dataclass(frozen=True, repr=False)
class WorkerResult:
    """Untrusted completion/closed failure, never verification or publication."""
    epoch: str
    dispatch: str
    model: str
    status: str
    content: str
    finish_reason: str
    failure: str

    def __post_init__(self):
        _identity(self.epoch, self.dispatch)
        _model(self.model)
        _text(self.content, MAX_RESULT_BYTES)
        if any(type(v) is not str for v in (self.status, self.finish_reason, self.failure)):
            _deny()
        if self.status == "completed":
            if self.finish_reason not in {"stop", "length"} or self.failure != "":
                _deny()
        elif self.status == "failed":
            if (self.content != "" or self.finish_reason != ""
                    or self.failure not in {"provider_failed", "response_invalid", "interrupted", "unavailable"}):
                _deny()
        else:
            _deny()
        _dump(_result_object(self), MAX_RESULT_BYTES)


def _request_object(value):
    return dict(policy=POLICY, kind="request", epoch=value.epoch, dispatch=value.dispatch,
                model=value.model, system_text=value.system_text, chunk_text=value.chunk_text,
                context_size=value.context_size, max_output_tokens=value.max_output_tokens)


def _result_object(value):
    return dict(policy=POLICY, kind="result", epoch=value.epoch, dispatch=value.dispatch,
                model=value.model, status=value.status, content=value.content,
                finish_reason=value.finish_reason, failure=value.failure)


def _dump(value, ceiling):
    try:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(raw) > ceiling:
            _deny()
        return raw
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _deny()


def encode_request(value):
    if type(value) is not WorkerRequest:
        _deny()
    value.__post_init__()
    return _dump(_request_object(value), MAX_REQUEST_BYTES)


def encode_result(value):
    if type(value) is not WorkerResult:
        _deny()
    value.__post_init__()
    return _dump(_result_object(value), MAX_RESULT_BYTES)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _deny()
        result[key] = value
    return result


def _load(raw, ceiling, kind, fields):
    if type(raw) is not bytes or not 2 <= len(raw) <= ceiling:
        _deny()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: _deny())
        if (type(value) is not dict or set(value) != set(fields) | {"policy", "kind"}
                or value.pop("policy") != POLICY or value.pop("kind") != kind):
            _deny()
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        _deny()


def decode_request(raw):
    return WorkerRequest(**_load(raw, MAX_REQUEST_BYTES, "request", WorkerRequest.__dataclass_fields__))


def decode_result(raw):
    return WorkerResult(**_load(raw, MAX_RESULT_BYTES, "result", WorkerResult.__dataclass_fields__))


def match_result(request, result):
    """Equality only: cannot detect replay, authenticate a worker or grant consent."""
    encode_request(request)
    encode_result(result)
    if (request.epoch, request.dispatch, request.model) != (result.epoch, result.dispatch, result.model):
        _deny()
    return result
