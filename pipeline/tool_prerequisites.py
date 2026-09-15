"""Session-local exact prerequisite receipts for tool admission.

Only trusted Core adapters may translate separately verified readiness/policy
evidence into these receipts.  The controller does not inspect a backend,
network, filesystem, model, or provider and receipt possession is not a grant
or approval.  Receipts are invocation-bound, expiring, revocable, and one-use.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
import secrets
from threading import RLock
import time
from typing import Callable, Iterable

from pipeline.tool_grants import (
    IDENTITY_RE,
    RESOURCE_REF_RE,
    ToolInvocation,
    tool_invocation_fingerprint,
)
from pipeline.tool_registry import TOOL_ID_RE


MAX_TOOL_PREREQUISITES = 128
MAX_TOOL_PREREQUISITE_SECONDS = 300.0
PREREQUISITE_ID_RE = re.compile(r"^TP-[A-Za-z0-9_-]{1,64}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class ToolPrerequisiteError(ValueError):
    """Raised when exact prerequisite evidence cannot be accepted or claimed."""


def _epoch(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolPrerequisiteError(f"{label} is invalid")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized < 1e12:
        raise ToolPrerequisiteError(f"{label} is invalid")
    return normalized


@dataclass(frozen=True)
class ToolPrerequisiteReceipt:
    """One Core-created exact prerequisite binding; never tool authority."""

    prerequisite_id: str
    invocation_id: str
    invocation_fingerprint: str
    requirement_id: str
    resource_ref: str
    evidence_sha256: str
    policy_revision: str
    created_at: float
    expires_at: float
    revocation_generation: int = 0
    revoked: bool = False
    claimed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.prerequisite_id, str) or not PREREQUISITE_ID_RE.fullmatch(self.prerequisite_id):
            raise ToolPrerequisiteError("tool prerequisite identifier is invalid")
        if not isinstance(self.invocation_id, str) or not self.invocation_id.startswith("TI-"):
            raise ToolPrerequisiteError("tool prerequisite invocation is invalid")
        if not isinstance(self.invocation_fingerprint, str) or not _DIGEST_RE.fullmatch(self.invocation_fingerprint):
            raise ToolPrerequisiteError("tool prerequisite invocation fingerprint is invalid")
        if not isinstance(self.requirement_id, str) or not TOOL_ID_RE.fullmatch(self.requirement_id):
            raise ToolPrerequisiteError("tool prerequisite requirement is invalid")
        if not isinstance(self.resource_ref, str) or not RESOURCE_REF_RE.fullmatch(self.resource_ref):
            raise ToolPrerequisiteError("tool prerequisite resource is invalid")
        if not isinstance(self.evidence_sha256, str) or not _DIGEST_RE.fullmatch(self.evidence_sha256):
            raise ToolPrerequisiteError("tool prerequisite evidence digest is invalid")
        if not isinstance(self.policy_revision, str) or not IDENTITY_RE.fullmatch(self.policy_revision):
            raise ToolPrerequisiteError("tool prerequisite policy revision is invalid")
        created = _epoch(self.created_at, "tool prerequisite creation time")
        expires = _epoch(self.expires_at, "tool prerequisite expiry")
        if not created < expires or expires - created > MAX_TOOL_PREREQUISITE_SECONDS:
            raise ToolPrerequisiteError("tool prerequisite lifetime is invalid")
        if (
            isinstance(self.revocation_generation, bool)
            or not isinstance(self.revocation_generation, int)
            or self.revocation_generation < 0
            or not isinstance(self.revoked, bool)
            or not isinstance(self.claimed, bool)
        ):
            raise ToolPrerequisiteError("tool prerequisite state is invalid")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)

    def matches(self, invocation: ToolInvocation, requirement_id: str) -> bool:
        return bool(
            isinstance(invocation, ToolInvocation)
            and self.invocation_id == invocation.invocation_id
            and self.invocation_fingerprint == tool_invocation_fingerprint(invocation)
            and self.requirement_id == requirement_id
            and self.resource_ref in invocation.resource_refs
            and self.policy_revision == invocation.policy_revision
        )


class SessionToolPrerequisiteController:
    """Bounded memory-only issuer and atomic one-use claimant."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        id_factory: Callable[[], str] | None = None,
        maximum_receipts: int = MAX_TOOL_PREREQUISITES,
    ) -> None:
        if not callable(clock) or (id_factory is not None and not callable(id_factory)):
            raise TypeError("tool prerequisite controller dependency is invalid")
        if (
            isinstance(maximum_receipts, bool)
            or not isinstance(maximum_receipts, int)
            or not 1 <= maximum_receipts <= 1024
        ):
            raise ValueError("tool prerequisite controller limit is invalid")
        self._clock = clock
        self._id_factory = id_factory or (lambda: f"TP-{secrets.token_hex(16)}")
        self._maximum_receipts = maximum_receipts
        self._receipts: dict[str, ToolPrerequisiteReceipt] = {}
        self._lock = RLock()

    def issue(
        self,
        invocation: ToolInvocation,
        *,
        requirement_id: str,
        resource_ref: str,
        evidence_sha256: str,
        lifetime_seconds: float = 120.0,
    ) -> ToolPrerequisiteReceipt:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("tool prerequisite invocation is invalid")
        if not isinstance(requirement_id, str) or not TOOL_ID_RE.fullmatch(requirement_id):
            raise ToolPrerequisiteError("tool prerequisite requirement is invalid")
        if resource_ref not in invocation.resource_refs:
            raise ToolPrerequisiteError("tool prerequisite resource is not invocation-bound")
        if not isinstance(evidence_sha256, str) or not _DIGEST_RE.fullmatch(evidence_sha256):
            raise ToolPrerequisiteError("tool prerequisite evidence digest is invalid")
        lifetime = _epoch(lifetime_seconds, "tool prerequisite lifetime")
        if not 0 < lifetime <= MAX_TOOL_PREREQUISITE_SECONDS:
            raise ToolPrerequisiteError("tool prerequisite lifetime is invalid")
        now = _epoch(self._clock(), "tool prerequisite clock")
        with self._lock:
            if len(self._receipts) >= self._maximum_receipts:
                raise ToolPrerequisiteError("tool prerequisite capacity is exhausted")
            if any(
                item.invocation_id == invocation.invocation_id
                and item.requirement_id == requirement_id
                and not item.revoked
                for item in self._receipts.values()
            ):
                raise ToolPrerequisiteError("tool prerequisite requirement already has a receipt")
            receipt = ToolPrerequisiteReceipt(
                prerequisite_id=self._id_factory(),
                invocation_id=invocation.invocation_id,
                invocation_fingerprint=tool_invocation_fingerprint(invocation),
                requirement_id=requirement_id,
                resource_ref=resource_ref,
                evidence_sha256=evidence_sha256,
                policy_revision=invocation.policy_revision,
                created_at=now,
                expires_at=min(now + lifetime, invocation.expires_at),
            )
            self._receipts[receipt.prerequisite_id] = receipt
            return receipt

    def claim_all(
        self,
        invocation: ToolInvocation,
        required_requirements: Iterable[str],
    ) -> tuple[ToolPrerequisiteReceipt, ...]:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("tool prerequisite invocation is invalid")
        requirements = tuple(required_requirements)
        if (
            len(set(requirements)) != len(requirements)
            or any(not isinstance(item, str) or not TOOL_ID_RE.fullmatch(item) for item in requirements)
        ):
            raise ToolPrerequisiteError("tool prerequisite requirements are invalid")
        if not requirements:
            return ()
        now = _epoch(self._clock(), "tool prerequisite clock")
        with self._lock:
            selected: list[ToolPrerequisiteReceipt] = []
            for requirement in requirements:
                matching = tuple(
                    item for item in self._receipts.values()
                    if not item.revoked
                    and item.requirement_id == requirement
                    and item.matches(invocation, requirement)
                )
                if len(matching) != 1:
                    raise ToolPrerequisiteError("tool prerequisite is missing or ambiguous")
                receipt = matching[0]
                if receipt.revoked or receipt.claimed or now >= receipt.expires_at:
                    raise ToolPrerequisiteError("tool prerequisite is unavailable")
                selected.append(receipt)
            claimed = tuple(replace(item, claimed=True) for item in selected)
            for item in claimed:
                self._receipts[item.prerequisite_id] = item
            return claimed

    def claims_are_valid(
        self,
        invocation: ToolInvocation,
        bindings: Iterable[tuple[str, int]],
    ) -> bool:
        """Recheck exact claimed receipts immediately before a future effect."""
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("tool prerequisite invocation is invalid")
        values = tuple(bindings)
        if any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not PREREQUISITE_ID_RE.fullmatch(item[0])
            or isinstance(item[1], bool)
            or not isinstance(item[1], int)
            or item[1] < 0
            for item in values
        ):
            raise ToolPrerequisiteError("tool prerequisite claim bindings are invalid")
        now = _epoch(self._clock(), "tool prerequisite clock")
        with self._lock:
            for receipt_id, generation in values:
                receipt = self._receipts.get(receipt_id)
                if (
                    receipt is None
                    or not receipt.claimed
                    or receipt.revoked
                    or receipt.revocation_generation != generation
                    or now >= receipt.expires_at
                    or not receipt.matches(invocation, receipt.requirement_id)
                ):
                    return False
            return True

    def revoke(self, prerequisite_id: object) -> ToolPrerequisiteReceipt | None:
        if not isinstance(prerequisite_id, str):
            return None
        with self._lock:
            receipt = self._receipts.get(prerequisite_id)
            if receipt is None:
                return None
            if not receipt.revoked:
                receipt = replace(
                    receipt, revoked=True,
                    revocation_generation=receipt.revocation_generation + 1,
                )
                self._receipts[prerequisite_id] = receipt
            return receipt

    def revoke_invocation(self, invocation_id: object) -> int:
        if not isinstance(invocation_id, str):
            return 0
        changed = 0
        with self._lock:
            for receipt_id, receipt in tuple(self._receipts.items()):
                if receipt.invocation_id == invocation_id and not receipt.revoked:
                    self._receipts[receipt_id] = replace(
                        receipt, revoked=True,
                        revocation_generation=receipt.revocation_generation + 1,
                    )
                    changed += 1
        return changed


__all__ = [
    "MAX_TOOL_PREREQUISITES",
    "MAX_TOOL_PREREQUISITE_SECONDS",
    "PREREQUISITE_ID_RE",
    "SessionToolPrerequisiteController",
    "ToolPrerequisiteError",
    "ToolPrerequisiteReceipt",
]
