import json
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_hyperv import (
    HYPERV_PROBE_REVISION,
    HyperVHostFacts,
    HyperVReadinessInspector,
    HyperVReferenceProfile,
    WindowsPowerShellHyperVProbe,
    assess_hyperv_host,
    format_hyperv_readiness,
)


def facts(**overrides):
    values = {
        "schema_version": 1,
        "probe_revision": HYPERV_PROBE_REVISION,
        "observed_at_epoch": 100.0,
        "os_family": "windows",
        "os_caption": "Microsoft Windows 11 Pro",
        "os_version": "10.0.26100",
        "os_build": "26100",
        "architecture": "64-bit",
        "feature_state": "enabled",
        "hypervisor_present": True,
        "virtualization_firmware_enabled": None,
        "slat": None,
        "vm_monitor_mode": None,
        "dep_available": None,
    }
    values.update(overrides)
    return HyperVHostFacts(**values)


def probe_payload(**overrides):
    values = {
        "schema_version": 1,
        "os_family": "windows",
        "os_caption": "Microsoft Windows 11 Pro",
        "os_version": "10.0.26100",
        "os_build": "26100",
        "architecture": "64-bit",
        "feature_install_state": 1,
        "hypervisor_present": True,
        "virtualization_firmware_enabled": None,
        "slat": None,
        "vm_monitor_mode": None,
        "dep_available": None,
    }
    values.update(overrides)
    return json.dumps(values).encode("utf-8")


class StaticProbe:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error

    def probe_host(self):
        if self.error is not None:
            raise self.error
        return self.value


class HyperVReadinessTests(unittest.TestCase):
    def test_reference_profile_is_immutable_non_executable_and_network_disabled(self):
        profile = HyperVReferenceProfile()
        self.assertFalse(profile.executable)
        self.assertFalse(profile.public_dict()["executable"])
        self.assertEqual(profile.network_mode, "disabled")
        self.assertEqual(profile.image_revision, "unconfigured")
        self.assertEqual(profile.transport_revision, "unconfigured")
        with self.assertRaises(FrozenInstanceError):
            profile.image_revision = "changed"
        with self.assertRaises(ValueError):
            HyperVReferenceProfile(network_mode="enabled")

    def test_met_host_prerequisites_never_claim_execution_readiness(self):
        report = assess_hyperv_host(facts())
        self.assertEqual(report.host_status, "prerequisites_met")
        self.assertEqual(report.execution_status, "unavailable")
        self.assertFalse(report.execution_ready)
        self.assertIn("image_unconfigured", report.reasons)
        self.assertIn("transport_unconfigured", report.reasons)
        self.assertNotIn("os_caption", report.public_dict())

    def test_edition_architecture_feature_and_hardware_fail_closed(self):
        cases = (
            (facts(os_caption="Microsoft Windows 11 Home"), "unsupported", "unsupported_edition"),
            (facts(architecture="32-bit"), "unsupported", "unsupported_architecture"),
            (facts(feature_state="disabled"), "unavailable", "hyperv_feature_disabled"),
            (facts(feature_state="absent"), "unavailable", "hyperv_feature_absent"),
            (facts(feature_state="unknown"), "unknown", "hyperv_feature_unknown"),
            (
                facts(
                    hypervisor_present=False,
                    virtualization_firmware_enabled=True,
                    slat=False,
                    vm_monitor_mode=True,
                    dep_available=True,
                ),
                "unavailable",
                "slat_unavailable",
            ),
            (
                facts(hypervisor_present=False, virtualization_firmware_enabled=None),
                "unknown",
                "hardware_state_unknown",
            ),
        )
        for value, status, reason in cases:
            with self.subTest(reason=reason):
                report = assess_hyperv_host(value)
                self.assertEqual(report.host_status, status)
                self.assertIn(reason, report.reasons)
                self.assertFalse(report.execution_ready)

    def test_inspector_is_explicit_and_probe_errors_are_bounded(self):
        unavailable = HyperVReadinessInspector().probe()
        self.assertIn("probe_unavailable", unavailable.reasons)
        failed = HyperVReadinessInspector(
            StaticProbe(error=RuntimeError("C:/secret/user/path")),
        ).probe()
        rendered = format_hyperv_readiness(failed)
        self.assertIn("probe_failed", rendered)
        self.assertNotIn("secret", rendered)
        self.assertFalse(failed.execution_ready)

    def test_powershell_probe_uses_fixed_non_mutating_query_and_strict_json(self):
        completed = subprocess.CompletedProcess([], 0, probe_payload(), b"")
        with patch("pipeline.sandbox_hyperv.subprocess.run", return_value=completed) as run:
            result = WindowsPowerShellHyperVProbe(
                "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            ).probe_host()
        self.assertEqual(result.feature_state, "enabled")
        command = run.call_args.args[0]
        self.assertTrue(command[0].casefold().endswith("powershell.exe"))
        self.assertEqual(command[1:4], ["-NoLogo", "-NoProfile", "-NonInteractive"])
        script = command[-1]
        for forbidden in ("Enable-WindowsOptionalFeature", "Disable-WindowsOptionalFeature", "Get-VM", "Start-VM", "New-VM", "Set-VM"):
            self.assertNotIn(forbidden, script)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertFalse(run.call_args.kwargs["check"])

    def test_probe_rejects_extra_duplicate_malformed_oversized_and_failed_output(self):
        executable = "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        invalid_outputs = (
            probe_payload(extra=True),
            b'{"schema_version":1,"schema_version":1}',
            b"not-json",
            b"x" * (16 * 1024 + 1),
        )
        for output in invalid_outputs:
            with self.subTest(size=len(output)), patch(
                "pipeline.sandbox_hyperv.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, output, b"secret"),
            ):
                with self.assertRaises(ValueError):
                    WindowsPowerShellHyperVProbe(executable).probe_host()
        with patch(
            "pipeline.sandbox_hyperv.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, b"", b"secret"),
        ):
            with self.assertRaisesRegex(RuntimeError, "host query failed"):
                WindowsPowerShellHyperVProbe(executable).probe_host()

    def test_import_and_construction_do_not_probe(self):
        with patch("pipeline.sandbox_hyperv.subprocess.run", side_effect=AssertionError("probe")):
            HyperVReferenceProfile()
            HyperVReadinessInspector()
        with self.assertRaisesRegex(ValueError, "Windows-owned"):
            WindowsPowerShellHyperVProbe("C:/temporary/powershell.exe")


if __name__ == "__main__":
    unittest.main()
