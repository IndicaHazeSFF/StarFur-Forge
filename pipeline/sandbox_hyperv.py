"""Explicit read-only Hyper-V host readiness inspection.

This module may query a Windows host only when ``probe()`` is called. It never
enables features, elevates, inventories virtual machines, starts services,
creates a guest, or converts host prerequisites into execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import time
from typing import Mapping, Protocol


HYPERV_READINESS_SCHEMA_VERSION = 1
HYPERV_BACKEND_ID = "hyperv-managed"
HYPERV_PROBE_REVISION = "hyperv-host-probe-v1"
MAX_HYPERV_PROBE_OUTPUT_BYTES = 16 * 1024
MAX_HYPERV_PROBE_SECONDS = 20.0

HYPERV_FEATURE_STATES = frozenset({"enabled", "disabled", "absent", "unknown"})
HYPERV_HOST_STATUSES = frozenset({
    "prerequisites_met", "unsupported", "unavailable", "unknown",
})
HYPERV_EXECUTION_STATUSES = frozenset({"unavailable"})
HYPERV_READINESS_REASONS = frozenset({
    "host_prerequisites_met",
    "unsupported_os",
    "unsupported_edition",
    "unsupported_architecture",
    "hyperv_feature_disabled",
    "hyperv_feature_absent",
    "hyperv_feature_unknown",
    "firmware_virtualization_unavailable",
    "slat_unavailable",
    "vm_monitor_mode_unavailable",
    "dep_unavailable",
    "hardware_state_unknown",
    "probe_unavailable",
    "probe_failed",
    "image_unconfigured",
    "transport_unconfigured",
    "supervisor_unconfigured",
})

_SAFE_TEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,160}$")
_POWERSHELL_QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$os = Get-CimInstance -ClassName Win32_OperatingSystem
$computer = Get-CimInstance -ClassName Win32_ComputerSystem
$cpus = @(Get-CimInstance -ClassName Win32_Processor)
$feature = Get-CimInstance -ClassName Win32_OptionalFeature -Filter "Name = 'Microsoft-Hyper-V-All'" | Select-Object -First 1
function Get-AllCpuFlag([object[]]$Items, [string]$Name) {
    if ($Items.Count -eq 0) { return $null }
    $values = @($Items | ForEach-Object { $_.$Name })
    if ($values.Count -eq 0 -or $values -contains $null) { return $null }
    return -not ($values -contains $false)
}
[pscustomobject]@{
    schema_version = 1
    os_family = 'windows'
    os_caption = [string]$os.Caption
    os_version = [string]$os.Version
    os_build = [string]$os.BuildNumber
    architecture = [string]$os.OSArchitecture
    feature_install_state = if ($null -eq $feature) { $null } else { [int]$feature.InstallState }
    hypervisor_present = if ($null -eq $computer.HypervisorPresent) { $null } else { [bool]$computer.HypervisorPresent }
    virtualization_firmware_enabled = Get-AllCpuFlag $cpus 'VirtualizationFirmwareEnabled'
    slat = Get-AllCpuFlag $cpus 'SecondLevelAddressTranslationExtensions'
    vm_monitor_mode = Get-AllCpuFlag $cpus 'VMMonitorModeExtensions'
    dep_available = Get-AllCpuFlag $cpus 'DataExecutionPrevention_Available'
} | ConvertTo-Json -Compress
""".strip()


def _safe_text(name: str, value: object, *, maximum: int = 160) -> str:
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or not _SAFE_TEXT_RE.fullmatch(value)
    ):
        raise ValueError(f"{name} is invalid")
    return value


def _optional_boolean(name: str, value: object) -> bool | None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean or null")
    return value


def _reject_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Hyper-V probe output contains duplicate fields")
        result[key] = value
    return result


@dataclass(frozen=True)
class HyperVReferenceProfile:
    """Non-executable reference choices awaiting later enrollment/conformance."""

    schema_version: int = HYPERV_READINESS_SCHEMA_VERSION
    backend_id: str = HYPERV_BACKEND_ID
    guest_family: str = "linux"
    guest_generation: int = 2
    network_mode: str = "disabled"
    image_revision: str = "unconfigured"
    transport_kind: str = "hyperv_socket_candidate"
    transport_revision: str = "unconfigured"
    supervisor_revision: str = "unconfigured"

    def __post_init__(self) -> None:
        if self.schema_version != HYPERV_READINESS_SCHEMA_VERSION or isinstance(self.schema_version, bool):
            raise ValueError("Hyper-V reference profile schema version is unsupported")
        if self.backend_id != HYPERV_BACKEND_ID:
            raise ValueError("Hyper-V reference backend identifier is invalid")
        if self.guest_family != "linux" or self.guest_generation != 2:
            raise ValueError("Hyper-V reference guest profile is invalid")
        if self.network_mode != "disabled":
            raise ValueError("Hyper-V reference networking must remain disabled")
        for name in ("image_revision", "transport_kind", "transport_revision", "supervisor_revision"):
            _safe_text(name, getattr(self, name), maximum=128)

    @property
    def executable(self) -> bool:
        return False

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "backend_id": self.backend_id,
            "guest_family": self.guest_family,
            "guest_generation": self.guest_generation,
            "network_mode": self.network_mode,
            "image_revision": self.image_revision,
            "transport_kind": self.transport_kind,
            "transport_revision": self.transport_revision,
            "supervisor_revision": self.supervisor_revision,
            "executable": False,
        }


@dataclass(frozen=True)
class HyperVHostFacts:
    """Privacy-bounded facts returned by one explicit local host query."""

    schema_version: int
    probe_revision: str
    observed_at_epoch: float
    os_family: str
    os_caption: str
    os_version: str
    os_build: str
    architecture: str
    feature_state: str
    hypervisor_present: bool | None
    virtualization_firmware_enabled: bool | None
    slat: bool | None
    vm_monitor_mode: bool | None
    dep_available: bool | None

    def __post_init__(self) -> None:
        if self.schema_version != HYPERV_READINESS_SCHEMA_VERSION or isinstance(self.schema_version, bool):
            raise ValueError("Hyper-V host-facts schema version is unsupported")
        if self.probe_revision != HYPERV_PROBE_REVISION:
            raise ValueError("Hyper-V host-facts probe revision is unsupported")
        if (
            isinstance(self.observed_at_epoch, bool)
            or not isinstance(self.observed_at_epoch, (int, float))
            or not math.isfinite(float(self.observed_at_epoch))
            or not 0 <= float(self.observed_at_epoch) < 1e12
        ):
            raise ValueError("Hyper-V host-facts observation time is invalid")
        object.__setattr__(self, "observed_at_epoch", float(self.observed_at_epoch))
        if self.os_family != "windows":
            raise ValueError("Hyper-V host facts must describe Windows")
        for name, maximum in (
            ("os_caption", 160), ("os_version", 64), ("os_build", 32), ("architecture", 64),
        ):
            object.__setattr__(self, name, _safe_text(name, getattr(self, name), maximum=maximum))
        if self.feature_state not in HYPERV_FEATURE_STATES:
            raise ValueError("Hyper-V feature state is invalid")
        for name in (
            "hypervisor_present", "virtualization_firmware_enabled", "slat",
            "vm_monitor_mode", "dep_available",
        ):
            _optional_boolean(name, getattr(self, name))


@dataclass(frozen=True)
class HyperVReadinessReport:
    """Read-only host assessment; explicitly never execution readiness."""

    schema_version: int
    backend_id: str
    host_status: str
    execution_status: str
    reasons: tuple[str, ...]
    observed_at_epoch: float | None = None

    def __post_init__(self) -> None:
        if self.schema_version != HYPERV_READINESS_SCHEMA_VERSION or isinstance(self.schema_version, bool):
            raise ValueError("Hyper-V readiness schema version is unsupported")
        if self.backend_id != HYPERV_BACKEND_ID:
            raise ValueError("Hyper-V readiness backend identifier is invalid")
        if self.host_status not in HYPERV_HOST_STATUSES:
            raise ValueError("Hyper-V host readiness status is invalid")
        if self.execution_status not in HYPERV_EXECUTION_STATUSES:
            raise ValueError("Hyper-V execution status is invalid")
        reasons = tuple(self.reasons)
        if not reasons or len(reasons) > 12 or len(set(reasons)) != len(reasons):
            raise ValueError("Hyper-V readiness reasons are invalid")
        if any(reason not in HYPERV_READINESS_REASONS for reason in reasons):
            raise ValueError("Hyper-V readiness reason is invalid")
        object.__setattr__(self, "reasons", reasons)
        if self.observed_at_epoch is not None and (
            isinstance(self.observed_at_epoch, bool)
            or not isinstance(self.observed_at_epoch, (int, float))
            or not math.isfinite(float(self.observed_at_epoch))
        ):
            raise ValueError("Hyper-V readiness observation time is invalid")

    @property
    def execution_ready(self) -> bool:
        return False

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "backend_id": self.backend_id,
            "host_status": self.host_status,
            "execution_status": self.execution_status,
            "execution_ready": False,
            "reasons": list(self.reasons),
            "observed_at_epoch": self.observed_at_epoch,
        }


class HyperVHostProbe(Protocol):
    def probe_host(self) -> HyperVHostFacts:
        ...


def default_windows_powershell_path() -> str | None:
    """Resolve only the conventional Windows-owned PowerShell executable."""
    if os.name == "nt":
        windows_root = os.environ.get("SystemRoot")
        if not windows_root:
            return None
        candidate = Path(windows_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    else:
        candidate = Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    return str(candidate) if candidate.is_file() else None


class WindowsPowerShellHyperVProbe:
    """Explicit fixed read-only WMI query; never an administrative command seam."""

    def __init__(self, executable: str | None = None, *, timeout_seconds: float = MAX_HYPERV_PROBE_SECONDS):
        selected = executable if executable is not None else default_windows_powershell_path()
        if selected is None:
            raise RuntimeError("Windows PowerShell is unavailable")
        path = Path(selected)
        normalized_path = selected.replace("\\", "/").casefold()
        if (
            not (path.is_absolute() or PureWindowsPath(selected).is_absolute())
            or path.name.casefold() != "powershell.exe"
            or not normalized_path.endswith(
                "/windows/system32/windowspowershell/v1.0/powershell.exe"
            )
        ):
            raise ValueError("PowerShell probe executable must be the Windows-owned system path")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 1.0 <= float(timeout_seconds) <= MAX_HYPERV_PROBE_SECONDS
        ):
            raise ValueError("Hyper-V probe timeout is invalid")
        self._executable = str(path)
        self._timeout_seconds = float(timeout_seconds)

    def probe_host(self) -> HyperVHostFacts:
        completed = subprocess.run(
            [
                self._executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                _POWERSHELL_QUERY,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self._timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("Hyper-V host query failed")
        raw = completed.stdout
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_HYPERV_PROBE_OUTPUT_BYTES:
            raise ValueError("Hyper-V probe output size is invalid")
        try:
            decoded = raw.decode("utf-8-sig").strip()
            value = json.loads(decoded, object_pairs_hook=_reject_duplicate_object)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Hyper-V probe output is invalid") from error
        if not isinstance(value, Mapping):
            raise ValueError("Hyper-V probe output must be an object")
        expected = frozenset({
            "schema_version", "os_family", "os_caption", "os_version", "os_build",
            "architecture", "feature_install_state", "hypervisor_present",
            "virtualization_firmware_enabled", "slat", "vm_monitor_mode", "dep_available",
        })
        if frozenset(value) != expected:
            raise ValueError("Hyper-V probe output fields are invalid")
        if value["schema_version"] != HYPERV_READINESS_SCHEMA_VERSION or isinstance(
            value["schema_version"], bool,
        ):
            raise ValueError("Hyper-V probe output schema version is unsupported")
        install_state = value["feature_install_state"]
        if install_state is not None and (isinstance(install_state, bool) or not isinstance(install_state, int)):
            raise ValueError("Hyper-V feature install state is invalid")
        feature_state = {1: "enabled", 2: "disabled", 3: "absent", 4: "unknown"}.get(
            install_state, "unknown",
        )
        return HyperVHostFacts(
            HYPERV_READINESS_SCHEMA_VERSION,
            HYPERV_PROBE_REVISION,
            time.time(),
            value["os_family"],
            value["os_caption"],
            value["os_version"],
            value["os_build"],
            value["architecture"],
            feature_state,
            value["hypervisor_present"],
            value["virtualization_firmware_enabled"],
            value["slat"],
            value["vm_monitor_mode"],
            value["dep_available"],
        )


def assess_hyperv_host(facts: HyperVHostFacts) -> HyperVReadinessReport:
    """Assess prerequisites while keeping executable readiness unavailable."""
    if not isinstance(facts, HyperVHostFacts):
        raise TypeError("Hyper-V host facts are invalid")
    caption = facts.os_caption.casefold()
    architecture = facts.architecture.casefold()
    host_status = "unknown"
    host_reasons: list[str] = []

    if not any(label in caption for label in (
        "windows 10 pro", "windows 10 enterprise", "windows 11 pro",
        "windows 11 enterprise", "windows server",
    )):
        host_status = "unsupported"
        host_reasons.append("unsupported_edition")
    elif not any(label in architecture for label in ("64-bit", "x64", "amd64")):
        host_status = "unsupported"
        host_reasons.append("unsupported_architecture")
    elif facts.feature_state != "enabled":
        host_status = "unavailable" if facts.feature_state in {"disabled", "absent"} else "unknown"
        host_reasons.append({
            "disabled": "hyperv_feature_disabled",
            "absent": "hyperv_feature_absent",
            "unknown": "hyperv_feature_unknown",
        }[facts.feature_state])
    elif facts.hypervisor_present is True:
        host_status = "prerequisites_met"
        host_reasons.append("host_prerequisites_met")
    else:
        hardware = (
            (facts.virtualization_firmware_enabled, "firmware_virtualization_unavailable"),
            (facts.slat, "slat_unavailable"),
            (facts.vm_monitor_mode, "vm_monitor_mode_unavailable"),
            (facts.dep_available, "dep_unavailable"),
        )
        if any(value is None for value, _ in hardware):
            host_status = "unknown"
            host_reasons.append("hardware_state_unknown")
        elif any(value is False for value, _ in hardware):
            host_status = "unavailable"
            host_reasons.extend(reason for value, reason in hardware if value is False)
        else:
            host_status = "prerequisites_met"
            host_reasons.append("host_prerequisites_met")

    return HyperVReadinessReport(
        HYPERV_READINESS_SCHEMA_VERSION,
        HYPERV_BACKEND_ID,
        host_status,
        "unavailable",
        tuple(host_reasons + [
            "image_unconfigured", "transport_unconfigured", "supervisor_unconfigured",
        ]),
        facts.observed_at_epoch,
    )


class HyperVReadinessInspector:
    """Explicit probe facade that converts every probe fault to a safe denial."""

    def __init__(self, probe: HyperVHostProbe | None = None):
        self._probe = probe

    def probe(self) -> HyperVReadinessReport:
        if self._probe is None:
            return HyperVReadinessReport(
                HYPERV_READINESS_SCHEMA_VERSION,
                HYPERV_BACKEND_ID,
                "unavailable",
                "unavailable",
                ("probe_unavailable", "image_unconfigured", "transport_unconfigured", "supervisor_unconfigured"),
            )
        try:
            facts = self._probe.probe_host()
            return assess_hyperv_host(facts)
        except Exception:
            return HyperVReadinessReport(
                HYPERV_READINESS_SCHEMA_VERSION,
                HYPERV_BACKEND_ID,
                "unknown",
                "unavailable",
                ("probe_failed", "image_unconfigured", "transport_unconfigured", "supervisor_unconfigured"),
            )


def format_hyperv_readiness(report: HyperVReadinessReport) -> str:
    if not isinstance(report, HyperVReadinessReport):
        raise TypeError("Hyper-V readiness report is invalid")
    lines = [
        "Hyper-V sandbox readiness",
        f"Host prerequisites: {report.host_status}",
        "Execution backend: unavailable",
        "Reasons:",
    ]
    lines.extend(f"- {reason}" for reason in report.reasons)
    lines.append("Read-only inspection; no feature, service, VM, image, or execution state was changed.")
    return "\n".join(lines)


def main() -> None:
    """Run the explicit local probe; importing this module performs no query."""
    try:
        probe = WindowsPowerShellHyperVProbe()
    except Exception:
        probe = None
    print(format_hyperv_readiness(HyperVReadinessInspector(probe).probe()))


if __name__ == "__main__":
    main()


__all__ = [
    "HYPERV_BACKEND_ID",
    "HYPERV_FEATURE_STATES",
    "HYPERV_HOST_STATUSES",
    "HYPERV_PROBE_REVISION",
    "HYPERV_READINESS_SCHEMA_VERSION",
    "HyperVHostFacts",
    "HyperVHostProbe",
    "HyperVReadinessInspector",
    "HyperVReadinessReport",
    "HyperVReferenceProfile",
    "WindowsPowerShellHyperVProbe",
    "assess_hyperv_host",
    "default_windows_powershell_path",
    "format_hyperv_readiness",
]
