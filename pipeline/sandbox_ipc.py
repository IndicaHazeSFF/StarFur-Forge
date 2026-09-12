"""Provider-free authentication contracts for a future local supervisor IPC.

This module authenticates one narrowly enrolled Core client.  It does not
authorize a tool invocation, install or contact a service, open a socket,
select a backend, manage Hyper-V, or execute work.  A future native transport
must supply the peer principal from an independently trusted OS boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import math
import re
import secrets
from threading import RLock
import time
from typing import Callable

from .tool_grants import IDENTITY_RE, INVOCATION_ID_RE
from .sandbox_supervisor import WORKER_GENERATION_RE


SUPERVISOR_IPC_SCHEMA_VERSION = 1
MAX_SUPERVISOR_IPC_BYTES = 4096
MAX_SUPERVISOR_IPC_LIFETIME_SECONDS = 30.0
MAX_SEEN_SUPERVISOR_IPC_REQUESTS = 256
SUPERVISOR_IPC_OPERATIONS = frozenset({"launch", "query", "cancel"})
ENROLLMENT_ID_RE = re.compile(r"^SE-[A-Za-z0-9_-]{1,64}$")
REQUEST_ID_RE = re.compile(r"^SI-[A-Za-z0-9_-]{1,64}$")
NONCE_RE = re.compile(r"^SN-[A-Za-z0-9_-]{16,96}$")
KEY_ID_RE = re.compile(r"^SK-[A-Za-z0-9_-]{1,64}$")
REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SupervisorIPCAuthenticationError(ValueError):
    """Bounded authentication rejection with no secret or payload detail."""


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


def _canonical_unsigned(request: "SupervisorIPCRequest") -> bytes:
    return json.dumps(
        request.unsigned_dict(), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


@dataclass(frozen=True)
class SupervisorIPCEnrollment:
    """Public binding for one pre-enrolled local Core client; contains no key."""

    schema_version: int
    enrollment_id: str
    client_principal_id: str
    service_id: str
    service_revision: str
    transport_kind: str
    transport_revision: str
    key_id: str
    allowed_operations: tuple[str, ...]
    created_at: float
    expires_at: float

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SUPERVISOR_IPC_SCHEMA_VERSION:
            raise ValueError("supervisor IPC enrollment schema version is unsupported")
        _identifier(self.enrollment_id, ENROLLMENT_ID_RE, "supervisor IPC enrollment identifier")
        _identifier(self.client_principal_id, IDENTITY_RE, "supervisor IPC client principal")
        _identifier(self.service_id, IDENTITY_RE, "supervisor IPC service identifier")
        _identifier(self.service_revision, REVISION_RE, "supervisor IPC service revision")
        _identifier(self.transport_kind, REVISION_RE, "supervisor IPC transport kind")
        _identifier(self.transport_revision, REVISION_RE, "supervisor IPC transport revision")
        _identifier(self.key_id, KEY_ID_RE, "supervisor IPC key identifier")
        operations = tuple(self.allowed_operations)
        if (
            not operations
            or len(operations) > len(SUPERVISOR_IPC_OPERATIONS)
            or len(set(operations)) != len(operations)
            or not set(operations).issubset(SUPERVISOR_IPC_OPERATIONS)
        ):
            raise ValueError("supervisor IPC allowed operations are invalid")
        created = _timestamp(self.created_at, "supervisor IPC enrollment creation time")
        expires = _timestamp(self.expires_at, "supervisor IPC enrollment expiry")
        if created >= expires:
            raise ValueError("supervisor IPC enrollment lifetime is invalid")
        object.__setattr__(self, "allowed_operations", tuple(sorted(operations)))
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "enrollment_id": self.enrollment_id,
            "service_id": self.service_id,
            "service_revision": self.service_revision,
            "transport_kind": self.transport_kind,
            "transport_revision": self.transport_revision,
            "key_id": self.key_id,
            "allowed_operations": list(self.allowed_operations),
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class SupervisorIPCRequest:
    """Strict authenticated envelope carrying no proposal or result payload."""

    schema_version: int
    request_id: str
    enrollment_id: str
    client_principal_id: str
    session_instance_id: str
    operation: str
    invocation_id: str
    worker_generation: str
    binding_fingerprint: str
    key_id: str
    nonce: str
    issued_at: float
    expires_at: float
    authentication_tag: str = field(repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SUPERVISOR_IPC_SCHEMA_VERSION:
            raise ValueError("supervisor IPC request schema version is unsupported")
        _identifier(self.request_id, REQUEST_ID_RE, "supervisor IPC request identifier")
        _identifier(self.enrollment_id, ENROLLMENT_ID_RE, "supervisor IPC enrollment identifier")
        _identifier(self.client_principal_id, IDENTITY_RE, "supervisor IPC client principal")
        _identifier(self.session_instance_id, IDENTITY_RE, "supervisor IPC session instance")
        if self.operation not in SUPERVISOR_IPC_OPERATIONS:
            raise ValueError("supervisor IPC operation is invalid")
        _identifier(self.invocation_id, INVOCATION_ID_RE, "supervisor IPC invocation identifier")
        _identifier(self.worker_generation, WORKER_GENERATION_RE, "supervisor IPC worker generation")
        _identifier(self.binding_fingerprint, SHA256_RE, "supervisor IPC binding fingerprint")
        _identifier(self.key_id, KEY_ID_RE, "supervisor IPC key identifier")
        _identifier(self.nonce, NONCE_RE, "supervisor IPC nonce")
        issued = _timestamp(self.issued_at, "supervisor IPC request issue time")
        expires = _timestamp(self.expires_at, "supervisor IPC request expiry")
        if issued >= expires or expires - issued > MAX_SUPERVISOR_IPC_LIFETIME_SECONDS:
            raise ValueError("supervisor IPC request lifetime is invalid")
        _identifier(self.authentication_tag, SHA256_RE, "supervisor IPC authentication tag")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "enrollment_id": self.enrollment_id,
            "client_principal_id": self.client_principal_id,
            "session_instance_id": self.session_instance_id,
            "operation": self.operation,
            "invocation_id": self.invocation_id,
            "worker_generation": self.worker_generation,
            "binding_fingerprint": self.binding_fingerprint,
            "key_id": self.key_id,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "operation": self.operation,
            "invocation_id": self.invocation_id,
            "worker_generation": self.worker_generation,
        }

    def to_json_bytes(self) -> bytes:
        value = self.unsigned_dict()
        value["authentication_tag"] = self.authentication_tag
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")
        if len(encoded) > MAX_SUPERVISOR_IPC_BYTES:
            raise ValueError("supervisor IPC request exceeds its byte limit")
        return encoded

    @classmethod
    def from_json_bytes(cls, encoded: object) -> "SupervisorIPCRequest":
        if not isinstance(encoded, bytes) or not encoded or len(encoded) > MAX_SUPERVISOR_IPC_BYTES:
            raise ValueError("supervisor IPC request bytes are invalid")
        try:
            text = encoded.decode("utf-8", errors="strict")

            def pairs(values):
                result = {}
                for key, value in values:
                    if key in result:
                        raise ValueError("supervisor IPC request contains duplicate fields")
                    result[key] = value
                return result

            value = json.loads(text, object_pairs_hook=pairs)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("supervisor IPC request JSON is invalid") from error
        fields = tuple(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) != set(fields):
            raise ValueError("supervisor IPC request fields are invalid")
        return cls(**value)


def sign_supervisor_ipc_request(
    enrollment: SupervisorIPCEnrollment,
    secret: bytes,
    *,
    session_instance_id: str,
    operation: str,
    invocation_id: str,
    worker_generation: str,
    binding_fingerprint: str,
    issued_at: float,
    expires_at: float,
    request_id: str | None = None,
    nonce: str | None = None,
) -> SupervisorIPCRequest:
    """Create one bounded proof; possession authenticates but does not authorize."""
    if not isinstance(enrollment, SupervisorIPCEnrollment):
        raise TypeError("supervisor IPC enrollment is invalid")
    if not isinstance(secret, bytes) or not 32 <= len(secret) <= 128:
        raise ValueError("supervisor IPC enrollment secret is invalid")
    unsigned = SupervisorIPCRequest(
        SUPERVISOR_IPC_SCHEMA_VERSION,
        request_id or f"SI-{secrets.token_hex(16)}",
        enrollment.enrollment_id,
        enrollment.client_principal_id,
        session_instance_id,
        operation,
        invocation_id,
        worker_generation,
        binding_fingerprint,
        enrollment.key_id,
        nonce or f"SN-{secrets.token_hex(16)}",
        issued_at,
        expires_at,
        "0" * 64,
    )
    tag = hmac.new(secret, _canonical_unsigned(unsigned), hashlib.sha256).hexdigest()
    return SupervisorIPCRequest(**{**unsigned.__dict__, "authentication_tag": tag})


@dataclass(frozen=True)
class AuthenticatedSupervisorIPCRequest:
    """Authentication evidence only; never tool authority or readiness."""

    request: SupervisorIPCRequest
    authenticated_principal_id: str

    def public_dict(self) -> dict[str, object]:
        return self.request.public_dict()


class SupervisorIPCAuthenticator:
    """Session-local verifier with bounded replay denial and explicit revocation."""

    def __init__(
        self,
        enrollment: SupervisorIPCEnrollment,
        secret: bytes,
        *,
        clock: Callable[[], float] = time.time,
        maximum_seen_requests: int = MAX_SEEN_SUPERVISOR_IPC_REQUESTS,
    ) -> None:
        if not isinstance(enrollment, SupervisorIPCEnrollment):
            raise TypeError("supervisor IPC enrollment is invalid")
        if not isinstance(secret, bytes) or not 32 <= len(secret) <= 128:
            raise ValueError("supervisor IPC enrollment secret is invalid")
        if not callable(clock):
            raise TypeError("supervisor IPC clock is invalid")
        if (
            isinstance(maximum_seen_requests, bool)
            or not isinstance(maximum_seen_requests, int)
            or not 1 <= maximum_seen_requests <= MAX_SEEN_SUPERVISOR_IPC_REQUESTS
        ):
            raise ValueError("supervisor IPC replay capacity is invalid")
        self._enrollment = enrollment
        self._secret = secret
        self._clock = clock
        self._maximum_seen_requests = maximum_seen_requests
        self._seen_request_ids: set[str] = set()
        self._seen_nonces: set[str] = set()
        self._revoked = False
        self._lock = RLock()

    def revoke(self) -> None:
        with self._lock:
            self._revoked = True

    def authenticate(
        self,
        request: SupervisorIPCRequest,
        *,
        trusted_peer_principal_id: str,
    ) -> AuthenticatedSupervisorIPCRequest:
        """Authenticate a request using an OS-supplied peer identity.

        The caller must not populate ``trusted_peer_principal_id`` from message
        text, a conversation ID, provider output, persona data, or the request.
        """
        if not isinstance(request, SupervisorIPCRequest):
            raise SupervisorIPCAuthenticationError("supervisor IPC request is invalid")
        try:
            peer = _identifier(
                trusted_peer_principal_id, IDENTITY_RE,
                "supervisor IPC trusted peer principal",
            )
            now = _timestamp(self._clock(), "supervisor IPC authentication clock")
        except (TypeError, ValueError) as error:
            raise SupervisorIPCAuthenticationError("supervisor IPC peer evidence is invalid") from error
        with self._lock:
            enrollment = self._enrollment
            if self._revoked:
                raise SupervisorIPCAuthenticationError("supervisor IPC enrollment is revoked")
            if now < enrollment.created_at or now >= enrollment.expires_at:
                raise SupervisorIPCAuthenticationError("supervisor IPC enrollment is inactive")
            if peer != enrollment.client_principal_id or request.client_principal_id != peer:
                raise SupervisorIPCAuthenticationError("supervisor IPC principal is not enrolled")
            if (
                request.enrollment_id != enrollment.enrollment_id
                or request.key_id != enrollment.key_id
                or request.operation not in enrollment.allowed_operations
            ):
                raise SupervisorIPCAuthenticationError("supervisor IPC request is not enrolled")
            if now < request.issued_at or now >= request.expires_at:
                raise SupervisorIPCAuthenticationError("supervisor IPC request is stale")
            if (
                request.request_id in self._seen_request_ids
                or request.nonce in self._seen_nonces
            ):
                raise SupervisorIPCAuthenticationError("supervisor IPC request was already used")
            if len(self._seen_request_ids) >= self._maximum_seen_requests:
                raise SupervisorIPCAuthenticationError("supervisor IPC replay capacity is exhausted")
            expected = hmac.new(
                self._secret, _canonical_unsigned(request), hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, request.authentication_tag):
                raise SupervisorIPCAuthenticationError("supervisor IPC authentication failed")
            self._seen_request_ids.add(request.request_id)
            self._seen_nonces.add(request.nonce)
            return AuthenticatedSupervisorIPCRequest(request, peer)


__all__ = [
    "AuthenticatedSupervisorIPCRequest",
    "MAX_SEEN_SUPERVISOR_IPC_REQUESTS",
    "MAX_SUPERVISOR_IPC_BYTES",
    "MAX_SUPERVISOR_IPC_LIFETIME_SECONDS",
    "SUPERVISOR_IPC_OPERATIONS",
    "SUPERVISOR_IPC_SCHEMA_VERSION",
    "SupervisorIPCAuthenticationError",
    "SupervisorIPCAuthenticator",
    "SupervisorIPCEnrollment",
    "SupervisorIPCRequest",
    "sign_supervisor_ipc_request",
]
