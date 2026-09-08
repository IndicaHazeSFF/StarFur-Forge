"""Session-ephemeral invocation identity and exact tool grants.

Callers must supply authenticated internal principal and server-created session
instance identifiers.  This module validates and binds those trusted values; it
does not authenticate HTTP clients, interpret conversation IDs, persist grants,
approve requests, select an executor, or run tools.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import re
import secrets
from threading import RLock
import time
from typing import Callable, Iterable

from .tool_contracts import ToolContractRegistry, ToolProposal
from .tool_permissions import PermissionGrant


MAX_ACTIVE_TOOL_GRANTS = 128
MAX_TOOL_GRANT_USES = 16
MAX_TOOL_BINDING_SECONDS = 3600
IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
RESOURCE_REF_RE = re.compile(r"^TR-[A-Za-z0-9_-]{1,64}$")
INVOCATION_ID_RE = re.compile(r"^TI-[A-Za-z0-9_-]{1,64}$")
GRANT_ID_RE = re.compile(r"^TG-[A-Za-z0-9_-]{1,64}$")


class ToolGrantError(ValueError):
    """Raised when an invocation or grant fails a Core-owned binding."""


def _default_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(16)}"


def _validate_identity(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTITY_RE.fullmatch(value):
        raise ToolGrantError(f"{label} is invalid")
    return value


def _validate_time(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) < 10**12:
        raise ToolGrantError(f"{label} is invalid")
    return float(value)


def _validate_ttl(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 < float(value) <= MAX_TOOL_BINDING_SECONDS
    ):
        raise ToolGrantError("tool binding lifetime is invalid")
    return float(value)


def _proposal_digest(proposal: ToolProposal) -> str:
    canonical = json.dumps(
        proposal.public_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class ToolInvocation:
    """Core-issued immutable identity for one exact validated proposal."""

    invocation_id: str
    principal_id: str
    session_instance_id: str
    persona_id: str
    adventure_id: str | None
    tool_id: str
    tool_version: int
    permission_scope: str
    access_mode: str
    operation_digest: str
    resource_refs: tuple[str, ...]
    policy_revision: str
    created_at: float
    expires_at: float

    def __post_init__(self) -> None:
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ToolGrantError("tool invocation identifier is invalid")
        for label, value in (
            ("tool principal", self.principal_id),
            ("tool session instance", self.session_instance_id),
            ("tool persona", self.persona_id),
            ("tool policy revision", self.policy_revision),
        ):
            _validate_identity(value, label)
        if self.adventure_id is not None:
            _validate_identity(self.adventure_id, "tool adventure")
        if not isinstance(self.tool_id, str) or not self.tool_id:
            raise ToolGrantError("tool invocation operation is invalid")
        if isinstance(self.tool_version, bool) or not isinstance(self.tool_version, int) or self.tool_version < 1:
            raise ToolGrantError("tool invocation version is invalid")
        if not isinstance(self.permission_scope, str) or not self.permission_scope:
            raise ToolGrantError("tool invocation permission scope is invalid")
        if self.access_mode not in {"read_only", "mutating"}:
            raise ToolGrantError("tool invocation access mode is invalid")
        if not isinstance(self.operation_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", self.operation_digest):
            raise ToolGrantError("tool invocation operation digest is invalid")
        refs = tuple(self.resource_refs)
        if len(refs) > 16 or any(not isinstance(item, str) or not RESOURCE_REF_RE.fullmatch(item) for item in refs):
            raise ToolGrantError("tool invocation resource references are invalid")
        if len(set(refs)) != len(refs):
            raise ToolGrantError("tool invocation resource references must be unique")
        created = _validate_time(self.created_at, "tool invocation creation time")
        expires = _validate_time(self.expires_at, "tool invocation expiry")
        if not created < expires or expires - created > MAX_TOOL_BINDING_SECONDS:
            raise ToolGrantError("tool invocation lifetime is invalid")
        object.__setattr__(self, "resource_refs", refs)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)

    def binding_tuple(self) -> tuple[object, ...]:
        return (
            self.principal_id, self.session_instance_id, self.persona_id, self.adventure_id,
            self.tool_id, self.tool_version, self.permission_scope, self.access_mode,
            self.operation_digest, self.resource_refs, self.policy_revision,
        )


class ToolInvocationIssuer:
    """Core-owned issuer; injected clocks/IDs keep tests deterministic."""

    def __init__(
        self, contracts: ToolContractRegistry, *, clock: Callable[[], float] = time.time,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not isinstance(contracts, ToolContractRegistry):
            raise TypeError("tool invocation contract registry is invalid")
        if not callable(clock) or (id_factory is not None and not callable(id_factory)):
            raise TypeError("tool invocation issuer dependency is invalid")
        self._contracts = contracts
        self._clock = clock
        self._id_factory = id_factory or (lambda: _default_id("TI"))

    def issue(
        self, proposal: ToolProposal, *, trusted_principal_id: str, session_instance_id: str,
        persona_id: str, adventure_id: str | None, policy_revision: str,
        resource_refs: Iterable[str] = (), lifetime_seconds: float = 300,
        invocation_id: str | None = None,
    ) -> ToolInvocation:
        validated = self._contracts.validate_proposal(proposal)
        contract = self._contracts.get(validated.tool_id, validated.tool_version)
        if contract is None:
            raise ToolGrantError("tool invocation contract is unavailable")
        descriptor = contract.descriptor
        now = _validate_time(self._clock(), "tool invocation clock")
        ttl = _validate_ttl(lifetime_seconds)
        issued_id = self._id_factory() if invocation_id is None else invocation_id
        return ToolInvocation(
            issued_id,
            _validate_identity(trusted_principal_id, "tool principal"),
            _validate_identity(session_instance_id, "tool session instance"),
            _validate_identity(persona_id, "tool persona"),
            None if adventure_id is None else _validate_identity(adventure_id, "tool adventure"),
            validated.tool_id,
            validated.tool_version,
            descriptor.permission_scope,
            descriptor.access_mode,
            _proposal_digest(validated),
            tuple(resource_refs),
            _validate_identity(policy_revision, "tool policy revision"),
            now,
            now + ttl,
        )


@dataclass(frozen=True)
class SessionToolGrant:
    """Finite exact grant for one invocation binding; never an approval."""

    grant_id: str
    invocation_id: str
    binding: tuple[object, ...]
    permission_scope: str
    access_mode: str
    created_at: float
    expires_at: float
    maximum_uses: int
    uses: int = 0
    revocation_generation: int = 0
    revoked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.grant_id, str) or not GRANT_ID_RE.fullmatch(self.grant_id):
            raise ToolGrantError("tool grant identifier is invalid")
        if not isinstance(self.invocation_id, str) or not INVOCATION_ID_RE.fullmatch(self.invocation_id):
            raise ToolGrantError("tool grant invocation identifier is invalid")
        if not isinstance(self.binding, tuple) or not self.binding:
            raise ToolGrantError("tool grant binding is invalid")
        if not isinstance(self.permission_scope, str) or not self.permission_scope:
            raise ToolGrantError("tool grant scope is invalid")
        if self.access_mode not in {"read_only", "mutating"}:
            raise ToolGrantError("tool grant access mode is invalid")
        created = _validate_time(self.created_at, "tool grant creation time")
        expires = _validate_time(self.expires_at, "tool grant expiry")
        if not created < expires or expires - created > MAX_TOOL_BINDING_SECONDS:
            raise ToolGrantError("tool grant lifetime is invalid")
        if (
            isinstance(self.maximum_uses, bool)
            or not isinstance(self.maximum_uses, int)
            or not 1 <= self.maximum_uses <= MAX_TOOL_GRANT_USES
        ):
            raise ToolGrantError("tool grant use limit is invalid")
        if isinstance(self.uses, bool) or not isinstance(self.uses, int) or not 0 <= self.uses <= self.maximum_uses:
            raise ToolGrantError("tool grant use count is invalid")
        if (
            isinstance(self.revocation_generation, bool)
            or not isinstance(self.revocation_generation, int)
            or self.revocation_generation < 0
        ):
            raise ToolGrantError("tool grant revocation generation is invalid")
        if not isinstance(self.revoked, bool):
            raise ToolGrantError("tool grant revocation state is invalid")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)


class SessionToolGrantController:
    """Bounded in-memory grant lifecycle with atomic finite-use claims."""

    def __init__(
        self, *, clock: Callable[[], float] = time.time,
        id_factory: Callable[[], str] | None = None, maximum_grants: int = MAX_ACTIVE_TOOL_GRANTS,
    ) -> None:
        if not callable(clock) or (id_factory is not None and not callable(id_factory)):
            raise TypeError("tool grant controller dependency is invalid")
        if isinstance(maximum_grants, bool) or not isinstance(maximum_grants, int) or not 1 <= maximum_grants <= 1024:
            raise ValueError("tool grant controller limit is invalid")
        self._clock = clock
        self._id_factory = id_factory or (lambda: _default_id("TG"))
        self._maximum_grants = maximum_grants
        self._records: dict[str, SessionToolGrant] = {}
        self._lock = RLock()

    def issue(
        self, invocation: ToolInvocation, *, lifetime_seconds: float = 300, maximum_uses: int = 1,
    ) -> SessionToolGrant:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("tool grant invocation is invalid")
        now = _validate_time(self._clock(), "tool grant clock")
        ttl = _validate_ttl(lifetime_seconds)
        if now >= invocation.expires_at:
            raise ToolGrantError("tool invocation has expired")
        expires = min(now + ttl, invocation.expires_at)
        with self._lock:
            if len(self._records) >= self._maximum_grants:
                raise ToolGrantError("tool grant controller is full")
            record = SessionToolGrant(
                self._id_factory(), invocation.invocation_id, invocation.binding_tuple(),
                invocation.permission_scope, invocation.access_mode, now, expires, maximum_uses,
            )
            if record.grant_id in self._records:
                raise ToolGrantError("tool grant identifier already exists")
            self._records[record.grant_id] = record
            return record

    def get(self, grant_id: object) -> SessionToolGrant | None:
        if not isinstance(grant_id, str):
            return None
        with self._lock:
            return self._records.get(grant_id)

    def claim(self, grant_id: object, invocation: ToolInvocation) -> PermissionGrant:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("tool grant invocation is invalid")
        now = _validate_time(self._clock(), "tool grant clock")
        with self._lock:
            record = self._records.get(grant_id) if isinstance(grant_id, str) else None
            if record is None:
                raise ToolGrantError("tool grant was not found")
            if record.revoked:
                raise ToolGrantError("tool grant was revoked")
            if now >= record.expires_at or now >= invocation.expires_at:
                raise ToolGrantError("tool grant has expired")
            if record.invocation_id != invocation.invocation_id or record.binding != invocation.binding_tuple():
                raise ToolGrantError("tool grant binding does not match invocation")
            if record.uses >= record.maximum_uses:
                raise ToolGrantError("tool grant use limit was exhausted")
            self._records[record.grant_id] = replace(record, uses=record.uses + 1)
            return PermissionGrant(record.permission_scope, frozenset({record.access_mode}))

    def revoke(self, grant_id: object) -> SessionToolGrant:
        with self._lock:
            record = self._records.get(grant_id) if isinstance(grant_id, str) else None
            if record is None:
                raise ToolGrantError("tool grant was not found")
            if record.revoked:
                return record
            revoked = replace(
                record, revoked=True, revocation_generation=record.revocation_generation + 1,
            )
            self._records[record.grant_id] = revoked
            return revoked

    def revoke_session(self, *, principal_id: str, session_instance_id: str) -> int:
        principal = _validate_identity(principal_id, "tool principal")
        session = _validate_identity(session_instance_id, "tool session instance")
        changed = 0
        with self._lock:
            for grant_id, record in tuple(self._records.items()):
                if record.binding[0:2] == (principal, session) and not record.revoked:
                    self._records[grant_id] = replace(
                        record, revoked=True, revocation_generation=record.revocation_generation + 1,
                    )
                    changed += 1
        return changed


__all__ = [
    "SessionToolGrant", "SessionToolGrantController", "ToolGrantError", "ToolInvocation",
    "ToolInvocationIssuer",
]
