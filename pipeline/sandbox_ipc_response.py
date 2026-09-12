"""Authenticated response contracts for a future local supervisor service.

Responses use a service-owned key distinct from the client request key and
carry only an existing strict supervisor lifecycle value.  Authentication
proves the enrolled service produced the bytes; Core must still validate the
lifecycle value and it never creates tool authority or backend readiness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import math
import re
import secrets
import struct
from threading import RLock
import time
from typing import Callable, Mapping

from .sandbox_ipc import (
    ENROLLMENT_ID_RE,
    KEY_ID_RE,
    MAX_SUPERVISOR_IPC_LIFETIME_SECONDS,
    REQUEST_ID_RE,
    REVISION_RE,
    SHA256_RE,
    SUPERVISOR_IPC_SCHEMA_VERSION,
    SupervisorIPCRequest,
)
from .sandbox_supervisor import (
    SupervisorCancelReceipt,
    SupervisorCompletion,
    SupervisorRunStatus,
    WORKER_GENERATION_RE,
)
from .tool_contracts import ToolResult
from .tool_grants import IDENTITY_RE, INVOCATION_ID_RE


MAX_SUPERVISOR_IPC_RESPONSE_BYTES = 24 * 1024
MAX_SUPERVISOR_IPC_RESPONSES_PER_CONNECTION = 16
MAX_SUPERVISOR_IPC_RESPONSE_CONNECTION_BYTES = (
    (4 + MAX_SUPERVISOR_IPC_RESPONSE_BYTES)
    * MAX_SUPERVISOR_IPC_RESPONSES_PER_CONNECTION
)
RESPONSE_ID_RE = re.compile(r"^SO-[A-Za-z0-9_-]{1,64}$")
RESPONSE_NONCE_RE = re.compile(r"^SR-[A-Za-z0-9_-]{16,96}$")
RESPONSE_KINDS = frozenset({"status", "cancel_receipt", "completion"})
RESPONSE_KINDS_BY_OPERATION = {
    "launch": frozenset({"status", "completion"}),
    "query": frozenset({"status"}),
    "cancel": frozenset({"cancel_receipt", "completion"}),
}


class SupervisorIPCResponseError(ValueError):
    """Bounded response rejection without received content or secret detail."""


def _identifier(value: object, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _timestamp(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 <= float(value) < 10**12
    ):
        raise ValueError(f"{label} is invalid")
    return float(value)


def _exact(value: object, fields: frozenset[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"{label} fields are invalid")
    return value


def _payload_kind(payload: object) -> str:
    if isinstance(payload, SupervisorRunStatus):
        return "status"
    if isinstance(payload, SupervisorCancelReceipt):
        return "cancel_receipt"
    if isinstance(payload, SupervisorCompletion):
        return "completion"
    raise TypeError("supervisor IPC response payload is invalid")


def _payload_dict(payload: object) -> dict[str, object]:
    kind = _payload_kind(payload)
    if kind == "status":
        return {
            "schema_version": payload.schema_version,
            "invocation_id": payload.invocation_id,
            "binding_fingerprint": payload.binding_fingerprint,
            "worker_generation": payload.worker_generation,
            "state": payload.state,
        }
    if kind == "cancel_receipt":
        return {
            "schema_version": payload.schema_version,
            "invocation_id": payload.invocation_id,
            "worker_generation": payload.worker_generation,
            "state": payload.state,
        }
    return {
        "schema_version": payload.schema_version,
        "invocation_id": payload.invocation_id,
        "tool_id": payload.tool_id,
        "tool_version": payload.tool_version,
        "binding_fingerprint": payload.binding_fingerprint,
        "policy_revision": payload.policy_revision,
        "worker_generation": payload.worker_generation,
        "outcome": payload.outcome,
        "stop_state": payload.stop_state,
        "result": None if payload.result is None else payload.result.public_dict(),
    }


def _parse_payload(kind: object, value: object) -> object:
    if kind == "status":
        item = _exact(value, frozenset({
            "schema_version", "invocation_id", "binding_fingerprint",
            "worker_generation", "state",
        }), "supervisor IPC status payload")
        return SupervisorRunStatus(**item)
    if kind == "cancel_receipt":
        item = _exact(value, frozenset({
            "schema_version", "invocation_id", "worker_generation", "state",
        }), "supervisor IPC cancellation payload")
        return SupervisorCancelReceipt(**item)
    if kind == "completion":
        item = dict(_exact(value, frozenset({
            "schema_version", "invocation_id", "tool_id", "tool_version",
            "binding_fingerprint", "policy_revision", "worker_generation",
            "outcome", "stop_state", "result",
        }), "supervisor IPC completion payload"))
        result = item["result"]
        item["result"] = None if result is None else ToolResult.from_mapping(result)
        return SupervisorCompletion(**item)
    raise ValueError("supervisor IPC response kind is invalid")


@dataclass(frozen=True)
class SupervisorIPCServiceIdentity:
    """Public response-key binding for one enrolled service; contains no key."""

    schema_version: int
    enrollment_id: str
    service_id: str
    service_revision: str
    transport_revision: str
    response_key_id: str
    created_at: float
    expires_at: float

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SUPERVISOR_IPC_SCHEMA_VERSION:
            raise ValueError("supervisor IPC service schema version is unsupported")
        _identifier(self.enrollment_id, ENROLLMENT_ID_RE, "supervisor IPC enrollment identifier")
        _identifier(self.service_id, IDENTITY_RE, "supervisor IPC service identifier")
        _identifier(self.service_revision, REVISION_RE, "supervisor IPC service revision")
        _identifier(self.transport_revision, REVISION_RE, "supervisor IPC transport revision")
        _identifier(self.response_key_id, KEY_ID_RE, "supervisor IPC response key identifier")
        created = _timestamp(self.created_at, "supervisor IPC service creation time")
        expires = _timestamp(self.expires_at, "supervisor IPC service expiry")
        if created >= expires:
            raise ValueError("supervisor IPC service lifetime is invalid")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "enrollment_id": self.enrollment_id,
            "service_id": self.service_id,
            "service_revision": self.service_revision,
            "transport_revision": self.transport_revision,
            "response_key_id": self.response_key_id,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class SupervisorIPCResponse:
    """Strict service-authenticated response bound to one exact request."""

    schema_version: int
    response_id: str
    request_id: str
    enrollment_id: str
    service_id: str
    service_revision: str
    transport_revision: str
    operation: str
    invocation_id: str
    worker_generation: str
    binding_fingerprint: str
    response_key_id: str
    nonce: str
    issued_at: float
    expires_at: float
    response_kind: str
    payload: object
    authentication_tag: str = field(repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SUPERVISOR_IPC_SCHEMA_VERSION:
            raise ValueError("supervisor IPC response schema version is unsupported")
        _identifier(self.response_id, RESPONSE_ID_RE, "supervisor IPC response identifier")
        _identifier(self.request_id, REQUEST_ID_RE, "supervisor IPC request identifier")
        _identifier(self.enrollment_id, ENROLLMENT_ID_RE, "supervisor IPC enrollment identifier")
        _identifier(self.service_id, IDENTITY_RE, "supervisor IPC service identifier")
        _identifier(self.service_revision, REVISION_RE, "supervisor IPC service revision")
        _identifier(self.transport_revision, REVISION_RE, "supervisor IPC transport revision")
        if self.operation not in RESPONSE_KINDS_BY_OPERATION:
            raise ValueError("supervisor IPC response operation is invalid")
        _identifier(self.invocation_id, INVOCATION_ID_RE, "supervisor IPC invocation identifier")
        _identifier(self.worker_generation, WORKER_GENERATION_RE, "supervisor IPC worker generation")
        _identifier(self.binding_fingerprint, SHA256_RE, "supervisor IPC binding fingerprint")
        _identifier(self.response_key_id, KEY_ID_RE, "supervisor IPC response key identifier")
        _identifier(self.nonce, RESPONSE_NONCE_RE, "supervisor IPC response nonce")
        issued = _timestamp(self.issued_at, "supervisor IPC response issue time")
        expires = _timestamp(self.expires_at, "supervisor IPC response expiry")
        if issued >= expires or expires - issued > MAX_SUPERVISOR_IPC_LIFETIME_SECONDS:
            raise ValueError("supervisor IPC response lifetime is invalid")
        if self.response_kind != _payload_kind(self.payload):
            raise ValueError("supervisor IPC response payload kind does not match")
        if self.response_kind not in RESPONSE_KINDS_BY_OPERATION[self.operation]:
            raise ValueError("supervisor IPC response kind is not valid for operation")
        if (
            self.payload.invocation_id != self.invocation_id
            or self.payload.worker_generation != self.worker_generation
            or (
                hasattr(self.payload, "binding_fingerprint")
                and self.payload.binding_fingerprint != self.binding_fingerprint
            )
        ):
            raise ValueError("supervisor IPC response payload binding does not match")
        _identifier(self.authentication_tag, SHA256_RE, "supervisor IPC response authentication tag")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "response_id": self.response_id,
            "request_id": self.request_id,
            "enrollment_id": self.enrollment_id,
            "service_id": self.service_id,
            "service_revision": self.service_revision,
            "transport_revision": self.transport_revision,
            "operation": self.operation,
            "invocation_id": self.invocation_id,
            "worker_generation": self.worker_generation,
            "binding_fingerprint": self.binding_fingerprint,
            "response_key_id": self.response_key_id,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "response_kind": self.response_kind,
            "payload": _payload_dict(self.payload),
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "response_id": self.response_id,
            "request_id": self.request_id,
            "operation": self.operation,
            "invocation_id": self.invocation_id,
            "worker_generation": self.worker_generation,
            "response_kind": self.response_kind,
        }

    def to_json_bytes(self) -> bytes:
        value = self.unsigned_dict()
        value["authentication_tag"] = self.authentication_tag
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        if len(encoded) > MAX_SUPERVISOR_IPC_RESPONSE_BYTES:
            raise ValueError("supervisor IPC response exceeds its byte limit")
        return encoded

    @classmethod
    def from_json_bytes(cls, encoded: object) -> "SupervisorIPCResponse":
        if not isinstance(encoded, bytes) or not encoded or len(encoded) > MAX_SUPERVISOR_IPC_RESPONSE_BYTES:
            raise ValueError("supervisor IPC response bytes are invalid")
        try:
            def pairs(values):
                result = {}
                for key, value in values:
                    if key in result:
                        raise ValueError("supervisor IPC response contains duplicate fields")
                    result[key] = value
                return result
            value = json.loads(encoded.decode("utf-8", errors="strict"), object_pairs_hook=pairs)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("supervisor IPC response JSON is invalid") from error
        fields = tuple(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) != set(fields):
            raise ValueError("supervisor IPC response fields are invalid")
        value["payload"] = _parse_payload(value["response_kind"], value["payload"])
        return cls(**value)


def _canonical_unsigned(response: SupervisorIPCResponse) -> bytes:
    return json.dumps(response.unsigned_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sign_supervisor_ipc_response(
    identity: SupervisorIPCServiceIdentity,
    secret: bytes,
    request: SupervisorIPCRequest,
    payload: object,
    *,
    issued_at: float,
    expires_at: float,
    response_id: str | None = None,
    nonce: str | None = None,
) -> SupervisorIPCResponse:
    if not isinstance(identity, SupervisorIPCServiceIdentity):
        raise TypeError("supervisor IPC service identity is invalid")
    if not isinstance(request, SupervisorIPCRequest):
        raise TypeError("supervisor IPC request is invalid")
    if not isinstance(secret, bytes) or not 32 <= len(secret) <= 128:
        raise ValueError("supervisor IPC response secret is invalid")
    if identity.enrollment_id != request.enrollment_id:
        raise ValueError("supervisor IPC service enrollment does not match request")
    if identity.response_key_id == request.key_id:
        raise ValueError("supervisor IPC request and response key identities must differ")
    unsigned = SupervisorIPCResponse(
        SUPERVISOR_IPC_SCHEMA_VERSION,
        response_id or f"SO-{secrets.token_hex(16)}",
        request.request_id,
        identity.enrollment_id,
        identity.service_id,
        identity.service_revision,
        identity.transport_revision,
        request.operation,
        request.invocation_id,
        request.worker_generation,
        request.binding_fingerprint,
        identity.response_key_id,
        nonce or f"SR-{secrets.token_hex(16)}",
        issued_at,
        expires_at,
        _payload_kind(payload),
        payload,
        "0" * 64,
    )
    tag = hmac.new(secret, _canonical_unsigned(unsigned), hashlib.sha256).hexdigest()
    return SupervisorIPCResponse(**{**unsigned.__dict__, "authentication_tag": tag})


@dataclass(frozen=True)
class AuthenticatedSupervisorIPCResponse:
    response: SupervisorIPCResponse

    def public_dict(self) -> dict[str, object]:
        return self.response.public_dict()


class SupervisorIPCResponseAuthenticator:
    """Client-side service verifier with bounded response replay denial."""

    def __init__(
        self,
        identity: SupervisorIPCServiceIdentity,
        secret: bytes,
        *,
        clock: Callable[[], float] = time.time,
        maximum_seen_responses: int = MAX_SUPERVISOR_IPC_RESPONSES_PER_CONNECTION,
    ) -> None:
        if not isinstance(identity, SupervisorIPCServiceIdentity):
            raise TypeError("supervisor IPC service identity is invalid")
        if not isinstance(secret, bytes) or not 32 <= len(secret) <= 128:
            raise ValueError("supervisor IPC response secret is invalid")
        if not callable(clock):
            raise TypeError("supervisor IPC response clock is invalid")
        if isinstance(maximum_seen_responses, bool) or not isinstance(maximum_seen_responses, int) or not 1 <= maximum_seen_responses <= 256:
            raise ValueError("supervisor IPC response replay capacity is invalid")
        self._identity = identity
        self._secret = secret
        self._clock = clock
        self._maximum_seen = maximum_seen_responses
        self._seen_ids: set[str] = set()
        self._seen_nonces: set[str] = set()
        self._revoked = False
        self._lock = RLock()

    def revoke(self) -> None:
        with self._lock:
            self._revoked = True

    def authenticate(
        self, response: SupervisorIPCResponse, *, request: SupervisorIPCRequest,
    ) -> AuthenticatedSupervisorIPCResponse:
        if not isinstance(response, SupervisorIPCResponse) or not isinstance(request, SupervisorIPCRequest):
            raise SupervisorIPCResponseError("supervisor IPC response binding is invalid")
        try:
            now = _timestamp(self._clock(), "supervisor IPC response clock")
        except (TypeError, ValueError) as error:
            raise SupervisorIPCResponseError("supervisor IPC response clock is invalid") from error
        with self._lock:
            identity = self._identity
            if self._revoked:
                raise SupervisorIPCResponseError("supervisor IPC service identity is revoked")
            if now < identity.created_at or now >= identity.expires_at:
                raise SupervisorIPCResponseError("supervisor IPC service identity is inactive")
            if now < response.issued_at or now >= response.expires_at:
                raise SupervisorIPCResponseError("supervisor IPC response is stale")
            if (
                response.enrollment_id != identity.enrollment_id
                or response.service_id != identity.service_id
                or response.service_revision != identity.service_revision
                or response.transport_revision != identity.transport_revision
                or response.response_key_id != identity.response_key_id
                or response.response_key_id == request.key_id
            ):
                raise SupervisorIPCResponseError("supervisor IPC service binding does not match")
            if (
                response.request_id != request.request_id
                or response.enrollment_id != request.enrollment_id
                or response.operation != request.operation
                or response.invocation_id != request.invocation_id
                or response.worker_generation != request.worker_generation
                or response.binding_fingerprint != request.binding_fingerprint
            ):
                raise SupervisorIPCResponseError("supervisor IPC request binding does not match")
            if response.response_id in self._seen_ids or response.nonce in self._seen_nonces:
                raise SupervisorIPCResponseError("supervisor IPC response was already used")
            if len(self._seen_ids) >= self._maximum_seen:
                raise SupervisorIPCResponseError("supervisor IPC response replay capacity is exhausted")
            expected = hmac.new(self._secret, _canonical_unsigned(response), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, response.authentication_tag):
                raise SupervisorIPCResponseError("supervisor IPC response authentication failed")
            self._seen_ids.add(response.response_id)
            self._seen_nonces.add(response.nonce)
            return AuthenticatedSupervisorIPCResponse(response)


def frame_supervisor_ipc_response(response: SupervisorIPCResponse) -> bytes:
    if not isinstance(response, SupervisorIPCResponse):
        raise TypeError("supervisor IPC framed response is invalid")
    payload = response.to_json_bytes()
    return struct.pack(">I", len(payload)) + payload


class AuthenticatedSupervisorIPCResponseReceiver:
    """Bounded fail-closed response parser for one exact outstanding request."""

    def __init__(
        self,
        authenticator: SupervisorIPCResponseAuthenticator,
        *,
        request: SupervisorIPCRequest,
        maximum_responses: int = MAX_SUPERVISOR_IPC_RESPONSES_PER_CONNECTION,
    ) -> None:
        if not isinstance(authenticator, SupervisorIPCResponseAuthenticator):
            raise TypeError("supervisor IPC response authenticator is invalid")
        if not isinstance(request, SupervisorIPCRequest):
            raise TypeError("supervisor IPC response request is invalid")
        if isinstance(maximum_responses, bool) or not isinstance(maximum_responses, int) or not 1 <= maximum_responses <= MAX_SUPERVISOR_IPC_RESPONSES_PER_CONNECTION:
            raise ValueError("supervisor IPC response frame limit is invalid")
        self._authenticator = authenticator
        self._request = request
        self._maximum = maximum_responses
        self._buffer = bytearray()
        self._received = 0
        self._count = 0
        self._closed = False
        self._failed = False

    @property
    def failed(self) -> bool:
        return self._failed

    def _reject(self, reason: str) -> None:
        self._failed = True
        self._closed = True
        self._buffer.clear()
        raise SupervisorIPCResponseError(reason)

    def feed(self, data: bytes) -> tuple[AuthenticatedSupervisorIPCResponse, ...]:
        if self._closed or self._failed:
            raise SupervisorIPCResponseError("supervisor IPC response connection is closed")
        if not isinstance(data, bytes):
            self._reject("supervisor IPC response frame bytes are invalid")
        if not data:
            return ()
        self._received += len(data)
        if self._received > MAX_SUPERVISOR_IPC_RESPONSE_CONNECTION_BYTES:
            self._reject("supervisor IPC response connection byte limit exceeded")
        self._buffer.extend(data)
        results = []
        while len(self._buffer) >= 4:
            length = struct.unpack(">I", self._buffer[:4])[0]
            if not 1 <= length <= MAX_SUPERVISOR_IPC_RESPONSE_BYTES:
                self._reject("supervisor IPC response frame length is invalid")
            end = 4 + length
            if len(self._buffer) < end:
                break
            if self._count >= self._maximum:
                self._reject("supervisor IPC response frame limit exceeded")
            payload = bytes(self._buffer[4:end])
            del self._buffer[:end]
            try:
                response = SupervisorIPCResponse.from_json_bytes(payload)
                authenticated = self._authenticator.authenticate(response, request=self._request)
            except (TypeError, ValueError):
                self._reject("supervisor IPC response authentication failed")
            self._count += 1
            results.append(authenticated)
        return tuple(results)

    def close(self) -> None:
        if self._failed:
            raise SupervisorIPCResponseError("supervisor IPC response connection is closed")
        if self._closed:
            return
        if self._buffer:
            self._reject("supervisor IPC response connection ended with a partial frame")
        self._closed = True

    def abort(self) -> None:
        self._buffer.clear()
        self._closed = True


__all__ = [
    "AuthenticatedSupervisorIPCResponse",
    "AuthenticatedSupervisorIPCResponseReceiver",
    "MAX_SUPERVISOR_IPC_RESPONSE_BYTES",
    "RESPONSE_KINDS",
    "SupervisorIPCResponse",
    "SupervisorIPCResponseAuthenticator",
    "SupervisorIPCResponseError",
    "SupervisorIPCServiceIdentity",
    "frame_supervisor_ipc_response",
    "sign_supervisor_ipc_response",
]
