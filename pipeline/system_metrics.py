"""Bounded, passive host-resource summaries for presentation clients.

This is intentionally not a task manager, process inspector, GPU probe, or
background monitor.  It reads a few portable aggregate values on demand so a
local apartment/dashboard can honestly display what Core knows.  Platform-
specific GPU/VRAM/temperature collection belongs behind a later explicit
adapter and permission policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil
from typing import Protocol


def _nonnegative_int(value: object, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"system metric {field} must be a non-negative integer or None")
    return value


@dataclass(frozen=True)
class SystemMetricsSnapshot:
    """Public aggregate resource values with explicit partial availability."""

    status: str
    platform_name: str | None = None
    cpu_logical_cores: int | None = None
    memory_total_bytes: int | None = None
    memory_available_bytes: int | None = None
    storage_total_bytes: int | None = None
    storage_free_bytes: int | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"unavailable", "partial"}:
            raise ValueError("system metrics status is invalid")
        if self.platform_name is not None and (not isinstance(self.platform_name, str) or not self.platform_name):
            raise ValueError("system metrics platform is invalid")
        for field in (
            "cpu_logical_cores", "memory_total_bytes", "memory_available_bytes",
            "storage_total_bytes", "storage_free_bytes",
        ):
            object.__setattr__(self, field, _nonnegative_int(getattr(self, field), field=field))
        if self.memory_available_bytes is not None and self.memory_total_bytes is not None and self.memory_available_bytes > self.memory_total_bytes:
            raise ValueError("available memory cannot exceed total memory")
        if self.storage_free_bytes is not None and self.storage_total_bytes is not None and self.storage_free_bytes > self.storage_total_bytes:
            raise ValueError("free storage cannot exceed total storage")
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason.strip()):
            raise ValueError("system metrics reason is invalid")

    @classmethod
    def unavailable(cls, reason: str = "not_configured") -> "SystemMetricsSnapshot":
        return cls("unavailable", reason=reason)

    def public_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "platform": self.platform_name,
            "cpu": {"logical_cores": self.cpu_logical_cores, "usage_percent": None},
            "memory": {"total_bytes": self.memory_total_bytes, "available_bytes": self.memory_available_bytes},
            "storage": {"total_bytes": self.storage_total_bytes, "free_bytes": self.storage_free_bytes},
            "gpu": {"status": "unavailable", "name": None, "vram_total_bytes": None, "vram_available_bytes": None},
            "reason": self.reason,
        }


class SystemMetricsProvider(Protocol):
    """A passive aggregate-resource source with no authority over Core."""

    def snapshot(self) -> SystemMetricsSnapshot: ...


class NullSystemMetricsProvider:
    """Safe default for tests or deployments that do not enable host metrics."""

    def snapshot(self) -> SystemMetricsSnapshot:
        return SystemMetricsSnapshot.unavailable()


class LocalSystemMetricsProvider:
    """Use only stdlib aggregate host/workspace values; never run a command."""

    def __init__(self, workspace: Path | str | None = None) -> None:
        self._workspace = Path(workspace) if workspace is not None else Path.cwd()

    @staticmethod
    def _linux_memory() -> tuple[int | None, int | None]:
        """Return Linux aggregate memory values, or no values elsewhere."""
        if platform.system().casefold() != "linux":
            return None, None
        try:
            values = {}
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                key, raw = line.split(":", 1)
                values[key] = int(raw.strip().split()[0]) * 1024
            return values.get("MemTotal"), values.get("MemAvailable")
        except (OSError, ValueError, IndexError):
            return None, None

    def snapshot(self) -> SystemMetricsSnapshot:
        memory_total, memory_available = self._linux_memory()
        storage_total = storage_free = None
        try:
            disk = shutil.disk_usage(self._workspace)
            storage_total, storage_free = disk.total, disk.free
        except OSError:
            pass
        cores = os.cpu_count()
        if isinstance(cores, int) and cores < 0:
            cores = None
        available = any(value is not None for value in (
            cores, memory_total, memory_available, storage_total, storage_free,
        ))
        return SystemMetricsSnapshot(
            "partial" if available else "unavailable",
            platform_name=platform.system().casefold() or None,
            cpu_logical_cores=cores,
            memory_total_bytes=memory_total,
            memory_available_bytes=memory_available,
            storage_total_bytes=storage_total,
            storage_free_bytes=storage_free,
            reason=None if available else "host_metrics_unavailable",
        )


__all__ = [
    "LocalSystemMetricsProvider", "NullSystemMetricsProvider", "SystemMetricsProvider", "SystemMetricsSnapshot",
]
