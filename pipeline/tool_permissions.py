"""Pure, fail-closed permission evaluation for declarative tool descriptions.

This module has no configuration loader, persistence, command surface, model
input, or executor.  A future caller must explicitly supply user-authorized
grants and one per-request confirmation value before it can ask whether a
``ToolDescriptor`` is allowed to proceed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pipeline.tool_registry import TOOL_ACCESS_MODES, TOOL_ID_RE, ToolDescriptor


PERMISSION_DECISION_REASONS = frozenset({
    "granted", "scope_not_granted", "access_not_granted", "confirmation_required",
})


@dataclass(frozen=True)
class PermissionGrant:
    """An exact user-authorized scope grant with no wildcard semantics."""

    permission_scope: str
    allowed_access_modes: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.permission_scope, str) or not TOOL_ID_RE.fullmatch(self.permission_scope):
            raise ValueError("permission grant scope is invalid")
        if not isinstance(self.allowed_access_modes, frozenset) or not self.allowed_access_modes:
            raise ValueError("permission grant access modes are invalid")
        if not self.allowed_access_modes.issubset(TOOL_ACCESS_MODES):
            raise ValueError("permission grant access modes are invalid")


@dataclass(frozen=True)
class PermissionDecision:
    """Bounded explanation of one pure authorization decision."""

    allowed: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool) or self.reason not in PERMISSION_DECISION_REASONS:
            raise ValueError("permission decision is invalid")
        if self.allowed != (self.reason == "granted"):
            raise ValueError("permission decision must agree with its reason")

    def public_dict(self) -> dict[str, object]:
        return {"allowed": self.allowed, "reason": self.reason}


def evaluate_tool_permission(
    descriptor: ToolDescriptor,
    grants: Iterable[PermissionGrant] = (),
    *,
    confirmed: bool = False,
) -> PermissionDecision:
    """Evaluate exact grants and confirmation without granting or executing.

    Scope matching is intentionally exact.  A grant for ``workspace.read``
    cannot authorize ``workspace.write`` or any inferred parent/child scope.
    """
    if not isinstance(descriptor, ToolDescriptor):
        raise TypeError("tool descriptor is invalid")
    if not isinstance(confirmed, bool):
        raise TypeError("tool confirmation is invalid")
    collected = tuple(grants)
    if not all(isinstance(item, PermissionGrant) for item in collected):
        raise TypeError("permission grants are invalid")
    matching = tuple(item for item in collected if item.permission_scope == descriptor.permission_scope)
    if not matching:
        return PermissionDecision(False, "scope_not_granted")
    if not any(descriptor.access_mode in item.allowed_access_modes for item in matching):
        return PermissionDecision(False, "access_not_granted")
    if descriptor.requires_confirmation and not confirmed:
        return PermissionDecision(False, "confirmation_required")
    return PermissionDecision(True, "granted")


__all__ = [
    "PERMISSION_DECISION_REASONS", "PermissionDecision", "PermissionGrant", "evaluate_tool_permission",
]
