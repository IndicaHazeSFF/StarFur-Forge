"""Single-use, session-ephemeral approval binding for tool invocations.

Only trusted Core control code may call ``approve``.  A model-provided boolean,
chat phrase, persona/adventure label, or proposal field can never construct the
approval evidence returned by this controller.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
import secrets
from threading import RLock
import time
from typing import Callable

from .tool_grants import (
    MAX_TOOL_BINDING_SECONDS, SessionToolGrant, ToolInvocation, _validate_time, _validate_ttl,
)


MAX_ACTIVE_TOOL_APPROVALS = 128
APPROVAL_ID_RE = re.compile(r"^TA-[A-Za-z0-9_-]{1,64}$")


class ToolApprovalError(ValueError):
    """Raised when trusted approval evidence is missing, stale, or replayed."""


@dataclass(frozen=True)
class ToolApproval:
    approval_id: str
    invocation_id: str
    grant_id: str
    binding: tuple[object, ...]
    grant_revocation_generation: int
    created_at: float
    expires_at: float
    consumed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.approval_id, str) or not APPROVAL_ID_RE.fullmatch(self.approval_id):
            raise ToolApprovalError("tool approval identifier is invalid")
        if not isinstance(self.invocation_id, str) or not self.invocation_id.startswith("TI-"):
            raise ToolApprovalError("tool approval invocation identifier is invalid")
        if not isinstance(self.grant_id, str) or not self.grant_id.startswith("TG-"):
            raise ToolApprovalError("tool approval grant identifier is invalid")
        if not isinstance(self.binding, tuple) or not self.binding:
            raise ToolApprovalError("tool approval binding is invalid")
        if (
            isinstance(self.grant_revocation_generation, bool)
            or not isinstance(self.grant_revocation_generation, int)
            or self.grant_revocation_generation < 0
        ):
            raise ToolApprovalError("tool approval revocation generation is invalid")
        created = _validate_time(self.created_at, "tool approval creation time")
        expires = _validate_time(self.expires_at, "tool approval expiry")
        if not created < expires or expires - created > MAX_TOOL_BINDING_SECONDS:
            raise ToolApprovalError("tool approval lifetime is invalid")
        if not isinstance(self.consumed, bool):
            raise ToolApprovalError("tool approval consumed state is invalid")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)


@dataclass(frozen=True)
class ToolApprovalEvidence:
    """Opaque trusted evidence produced only by one successful atomic claim."""

    approval_id: str
    invocation_id: str
    grant_id: str


class ToolApprovalController:
    def __init__(
        self, *, clock: Callable[[], float] = time.time,
        id_factory: Callable[[], str] | None = None,
        maximum_approvals: int = MAX_ACTIVE_TOOL_APPROVALS,
    ) -> None:
        if not callable(clock) or (id_factory is not None and not callable(id_factory)):
            raise TypeError("tool approval controller dependency is invalid")
        if (
            isinstance(maximum_approvals, bool)
            or not isinstance(maximum_approvals, int)
            or not 1 <= maximum_approvals <= 1024
        ):
            raise ValueError("tool approval controller limit is invalid")
        self._clock = clock
        self._id_factory = id_factory or (lambda: f"TA-{secrets.token_hex(16)}")
        self._maximum_approvals = maximum_approvals
        self._records: dict[str, ToolApproval] = {}
        self._lock = RLock()

    def approve(
        self, invocation: ToolInvocation, grant: SessionToolGrant, *, lifetime_seconds: float = 120,
    ) -> ToolApproval:
        if not isinstance(invocation, ToolInvocation) or not isinstance(grant, SessionToolGrant):
            raise TypeError("tool approval binding is invalid")
        now = _validate_time(self._clock(), "tool approval clock")
        ttl = _validate_ttl(lifetime_seconds)
        if grant.revoked or grant.uses >= grant.maximum_uses:
            raise ToolApprovalError("tool grant is not approval-eligible")
        if grant.invocation_id != invocation.invocation_id or grant.binding != invocation.binding_tuple():
            raise ToolApprovalError("tool approval binding does not match invocation")
        if now >= invocation.expires_at or now >= grant.expires_at:
            raise ToolApprovalError("tool approval binding has expired")
        expires = min(now + ttl, invocation.expires_at, grant.expires_at)
        with self._lock:
            if len(self._records) >= self._maximum_approvals:
                raise ToolApprovalError("tool approval controller is full")
            record = ToolApproval(
                self._id_factory(), invocation.invocation_id, grant.grant_id,
                invocation.binding_tuple(), grant.revocation_generation, now, expires,
            )
            if record.approval_id in self._records:
                raise ToolApprovalError("tool approval identifier already exists")
            self._records[record.approval_id] = record
            return record

    def get(self, approval_id: object) -> ToolApproval | None:
        if not isinstance(approval_id, str):
            return None
        with self._lock:
            return self._records.get(approval_id)

    def claim(
        self, approval_id: object, invocation: ToolInvocation, current_grant: SessionToolGrant,
    ) -> ToolApprovalEvidence:
        if not isinstance(invocation, ToolInvocation) or not isinstance(current_grant, SessionToolGrant):
            raise TypeError("tool approval claim binding is invalid")
        now = _validate_time(self._clock(), "tool approval clock")
        with self._lock:
            record = self._records.get(approval_id) if isinstance(approval_id, str) else None
            if record is None:
                raise ToolApprovalError("tool approval was not found")
            if record.consumed:
                raise ToolApprovalError("tool approval was already consumed")
            if now >= record.expires_at or now >= invocation.expires_at or now >= current_grant.expires_at:
                raise ToolApprovalError("tool approval has expired")
            if (
                record.invocation_id != invocation.invocation_id
                or record.grant_id != current_grant.grant_id
                or record.binding != invocation.binding_tuple()
                or current_grant.binding != invocation.binding_tuple()
                or record.grant_revocation_generation != current_grant.revocation_generation
                or current_grant.revoked
            ):
                raise ToolApprovalError("tool approval binding is stale or mismatched")
            self._records[record.approval_id] = replace(record, consumed=True)
            return ToolApprovalEvidence(record.approval_id, record.invocation_id, record.grant_id)

    def revoke(self, approval_id: object) -> ToolApproval:
        with self._lock:
            record = self._records.get(approval_id) if isinstance(approval_id, str) else None
            if record is None:
                raise ToolApprovalError("tool approval was not found")
            if record.consumed:
                return record
            revoked = replace(record, consumed=True)
            self._records[record.approval_id] = revoked
            return revoked


__all__ = [
    "ToolApproval", "ToolApprovalController", "ToolApprovalError", "ToolApprovalEvidence",
]
