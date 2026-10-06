"""Provider-free concurrency leases for future routed work.

The default gate is process-local.  An explicitly supplied process gate may
add one OS advisory capacity lease without changing this API.  This module
neither invokes nor probes providers, waits/queues, monitors work, preempts a
request, or enforces host resource limits.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets
import threading

from pipeline.task_routing import normalize_provider_id
from pipeline.provider_process_gate import ProviderProcessGate, ProviderProcessLease


WORKLOAD_GATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ProviderWorkloadLease:
    """One opaque, process-local reservation with no provider reference."""

    schema_version: int
    gate_id: str
    lease_id: str
    provider_id: str
    max_concurrent_requests: int

    def __post_init__(self) -> None:
        if self.schema_version != WORKLOAD_GATE_SCHEMA_VERSION:
            raise ValueError("workload lease schema version is unsupported")
        if not isinstance(self.gate_id, str) or len(self.gate_id) != 24:
            raise ValueError("workload lease gate ID is invalid")
        if not isinstance(self.lease_id, str) or len(self.lease_id) != 24:
            raise ValueError("workload lease ID is invalid")
        if normalize_provider_id(self.provider_id) != self.provider_id:
            raise ValueError("workload lease provider ID is invalid")
        if (
            isinstance(self.max_concurrent_requests, bool)
            or not isinstance(self.max_concurrent_requests, int)
            or not 1 <= self.max_concurrent_requests <= 64
        ):
            raise ValueError("workload lease concurrency limit is invalid")


@dataclass(frozen=True)
class ProviderWorkloadAdmission:
    """One immediate, non-authoritative capacity decision."""

    status: str
    provider_id: str
    reason: str | None
    lease: ProviderWorkloadLease | None

    def __post_init__(self) -> None:
        if self.status not in {"admitted", "deferred"}:
            raise ValueError("workload admission status is invalid")
        if normalize_provider_id(self.provider_id) != self.provider_id:
            raise ValueError("workload admission provider ID is invalid")
        if self.status == "admitted":
            if self.reason is not None or not isinstance(self.lease, ProviderWorkloadLease):
                raise ValueError("admitted workload decision requires exactly one lease")
            if self.lease.provider_id != self.provider_id:
                raise ValueError("workload lease provider binding is invalid")
        elif self.reason != "concurrency_busy" or self.lease is not None:
            raise ValueError("deferred workload decision is invalid")


class ProviderWorkloadGate:
    """Finite Core-owned provider capacity with immediate fail-closed admission."""

    def __init__(
        self, provider_capacities: dict[str, int], *, id_factory=None,
        process_gate: ProviderProcessGate | None = None,
    ) -> None:
        if not isinstance(provider_capacities, dict) or not provider_capacities:
            raise ValueError("workload gate capacities are invalid")
        normalized = {}
        for provider_id, capacity in provider_capacities.items():
            normalized_id = normalize_provider_id(provider_id)
            if normalized_id in normalized:
                raise ValueError("workload gate provider capacities are duplicated")
            if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= 64:
                raise ValueError("workload gate provider capacity is invalid")
            normalized[normalized_id] = capacity
        if process_gate is not None and not isinstance(process_gate, ProviderProcessGate):
            raise TypeError("workload process gate is invalid")
        if process_gate is not None and any(capacity != 1 for capacity in normalized.values()):
            raise ValueError("cross-process workload capacity must be exactly one")
        self._capacities = normalized
        self._gate_id = secrets.token_hex(12)
        self._id_factory = id_factory or (lambda: secrets.token_hex(12))
        if not callable(self._id_factory):
            raise TypeError("workload gate ID factory is invalid")
        self._leases: dict[str, ProviderWorkloadLease] = {}
        self._process_gate = process_gate
        self._process_leases: dict[str, ProviderProcessLease] = {}
        self._lock = threading.Lock()

    def try_acquire(self, provider_id: object, max_concurrent_requests: object) -> ProviderWorkloadAdmission:
        """Reserve capacity immediately; never queue, execute, or wait."""
        normalized_provider_id = normalize_provider_id(provider_id)
        if (
            isinstance(max_concurrent_requests, bool)
            or not isinstance(max_concurrent_requests, int)
            or not 1 <= max_concurrent_requests <= 64
        ):
            raise ValueError("workload gate request concurrency limit is invalid")
        try:
            capacity = self._capacities[normalized_provider_id]
        except KeyError as error:
            raise ValueError("workload gate provider is not configured") from error
        with self._lock:
            active = [lease for lease in self._leases.values() if lease.provider_id == normalized_provider_id]
            effective_capacity = min(
                capacity,
                max_concurrent_requests,
                *(lease.max_concurrent_requests for lease in active),
            )
            if len(active) >= effective_capacity:
                return ProviderWorkloadAdmission("deferred", normalized_provider_id, "concurrency_busy", None)
            process_lease = None
            if self._process_gate is not None:
                process_admission = self._process_gate.try_acquire(normalized_provider_id)
                if process_admission.lease is None:
                    return ProviderWorkloadAdmission(
                        "deferred", normalized_provider_id, "concurrency_busy", None,
                    )
                process_lease = process_admission.lease
            try:
                lease = ProviderWorkloadLease(
                    WORKLOAD_GATE_SCHEMA_VERSION,
                    self._gate_id,
                    self._id_factory(),
                    normalized_provider_id,
                    max_concurrent_requests,
                )
                if lease.lease_id in self._leases:
                    raise ValueError("workload gate lease ID is duplicated")
                self._leases[lease.lease_id] = lease
                if process_lease is not None:
                    self._process_leases[lease.lease_id] = process_lease
                return ProviderWorkloadAdmission("admitted", normalized_provider_id, None, lease)
            except Exception:
                if process_lease is not None:
                    self._process_gate.release(process_lease)
                raise

    def release(self, lease: object) -> bool:
        """Release only a matching gate-owned lease; false means no state changed."""
        if not isinstance(lease, ProviderWorkloadLease) or lease.gate_id != self._gate_id:
            return False
        with self._lock:
            current = self._leases.get(lease.lease_id)
            if current != lease:
                return False
            process_lease = self._process_leases.get(lease.lease_id)
            if process_lease is not None and not self._process_gate.release(process_lease):
                return False
            self._process_leases.pop(lease.lease_id, None)
            del self._leases[lease.lease_id]
            return True

    def active_count(self, provider_id: object) -> int:
        """Return one bounded in-process count without inspecting a provider."""
        normalized_provider_id = normalize_provider_id(provider_id)
        if normalized_provider_id not in self._capacities:
            raise ValueError("workload gate provider is not configured")
        with self._lock:
            return sum(lease.provider_id == normalized_provider_id for lease in self._leases.values())


__all__ = [
    "ProviderWorkloadAdmission", "ProviderWorkloadGate", "ProviderWorkloadLease",
    "WORKLOAD_GATE_SCHEMA_VERSION",
]
