"""Exact Core-owned selection of already-injected tool execution adapters.

The router maps one tool ID/version to one trusted supervisor. It performs no
discovery, authorization, provider call, backend probe, or execution itself.
An unavailable or unbound adapter stays unavailable; there is no generic
fallback from one tool class to another.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from pipeline.sandbox_supervisor import (
    SupervisorCancellation,
    SupervisorCancelReceipt,
    SupervisorCompletion,
    SupervisorLaunchRequest,
    SupervisorRunStatus,
    ToolExecutionSupervisor,
)
from pipeline.tool_contracts import ToolProposal
from pipeline.tool_grants import ToolInvocation
from pipeline.tool_registry import TOOL_ID_RE


MAX_TOOL_EXECUTION_BINDINGS = 32


def _version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 999:
        raise ValueError("tool executor version is invalid")
    return value


@dataclass(frozen=True)
class ToolExecutionBinding:
    """One exact Core-configured adapter binding; never tool authority."""

    tool_id: str
    tool_version: int
    supervisor: ToolExecutionSupervisor

    def __post_init__(self) -> None:
        if not isinstance(self.tool_id, str) or not TOOL_ID_RE.fullmatch(self.tool_id):
            raise ValueError("tool executor identifier is invalid")
        _version(self.tool_version)
        for member in ("available", "supports", "run", "request_cancel", "query"):
            if not hasattr(self.supervisor, member):
                raise TypeError("tool executor supervisor contract is incomplete")


class ToolExecutionRouter:
    """Route only exact tool/version bindings to Core-injected supervisors."""

    def __init__(self, bindings: Iterable[ToolExecutionBinding] = ()) -> None:
        ordered = tuple(bindings)
        if not all(isinstance(item, ToolExecutionBinding) for item in ordered):
            raise TypeError("tool execution bindings are invalid")
        if len(ordered) > MAX_TOOL_EXECUTION_BINDINGS:
            raise ValueError("tool execution binding limit exceeded")
        keys = tuple((item.tool_id, item.tool_version) for item in ordered)
        if len(keys) != len(set(keys)):
            raise ValueError("tool execution bindings must be unique")
        self._bindings: Mapping[tuple[str, int], ToolExecutionBinding] = MappingProxyType({
            (item.tool_id, item.tool_version): item for item in ordered
        })

    @property
    def available(self) -> bool:
        return any(self._binding_available(item) for item in self._bindings.values())

    def supports(self, tool_id: str, tool_version: int) -> bool:
        if not isinstance(tool_id, str) or not TOOL_ID_RE.fullmatch(tool_id):
            return False
        if isinstance(tool_version, bool) or not isinstance(tool_version, int):
            return False
        binding = self._bindings.get((tool_id, tool_version))
        return binding is not None and self._binding_available(binding)

    def run(
        self,
        request: SupervisorLaunchRequest,
        invocation: ToolInvocation,
        proposal: ToolProposal,
        cancellation: SupervisorCancellation,
    ) -> SupervisorCompletion:
        binding = self._require_exact(request)
        if (
            not request.matches_invocation(invocation)
            or proposal.tool_id != request.tool_id
            or proposal.tool_version != request.tool_version
        ):
            raise ValueError("tool execution route binding is inconsistent")
        return binding.supervisor.run(request, invocation, proposal, cancellation)

    def request_cancel(
        self,
        request: SupervisorLaunchRequest,
        cancellation: SupervisorCancellation,
    ) -> SupervisorCancelReceipt:
        return self._require_exact(request).supervisor.request_cancel(request, cancellation)

    def query(self, request: SupervisorLaunchRequest) -> SupervisorRunStatus:
        return self._require_exact(request).supervisor.query(request)

    @staticmethod
    def _adapter_available(binding: ToolExecutionBinding) -> bool:
        try:
            return binding.supervisor.available is True
        except Exception:
            return False

    @classmethod
    def _binding_available(cls, binding: ToolExecutionBinding) -> bool:
        if not cls._adapter_available(binding):
            return False
        try:
            return binding.supervisor.supports(
                binding.tool_id, binding.tool_version,
            ) is True
        except Exception:
            return False

    def _require_exact(self, request: SupervisorLaunchRequest) -> ToolExecutionBinding:
        if not isinstance(request, SupervisorLaunchRequest):
            raise TypeError("tool execution launch request is invalid")
        binding = self._bindings.get((request.tool_id, request.tool_version))
        if binding is None or not self.supports(request.tool_id, request.tool_version):
            raise RuntimeError("exact tool execution adapter is unavailable")
        return binding


__all__ = [
    "MAX_TOOL_EXECUTION_BINDINGS",
    "ToolExecutionBinding",
    "ToolExecutionRouter",
]
