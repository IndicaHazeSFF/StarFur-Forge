from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_execution_status import (
    DisabledSandboxExecutionStatusProvider,
    SandboxExecutionStatus,
)
from pipeline.sandbox_supervisor_readiness import SupervisorTransportReadiness


class SandboxExecutionStatusTests(unittest.TestCase):
    def test_default_is_deterministic_disabled_and_side_effect_free(self):
        with patch("subprocess.run", side_effect=AssertionError("must not probe")):
            value = DisabledSandboxExecutionStatusProvider().snapshot()
        self.assertEqual(value, SandboxExecutionStatus.disabled())
        self.assertEqual(value.public_dict(), {
            "schema_version": 1,
            "configured": False,
            "host_status": "unprobed",
            "supervisor_status": "unprobed",
            "execution_status": "disabled",
            "reason": "not_configured",
            "storage": "presentation_ephemeral",
        })

    def test_transport_ready_still_cannot_claim_execution(self):
        readiness = SupervisorTransportReadiness(1, "ready", "ready", "evidence-v1")
        value = SandboxExecutionStatus.from_transport_readiness(
            readiness, host_status="prerequisites_met",
        )
        self.assertEqual("ready", value.supervisor_status)
        self.assertEqual("disabled", value.execution_status)
        self.assertEqual("execution_not_enabled", value.reason)

    def test_unavailable_reasons_remain_sanitized(self):
        readiness = SupervisorTransportReadiness(
            1, "unavailable", "host_unsupported", None,
        )
        value = SandboxExecutionStatus.from_transport_readiness(
            readiness, host_status="unsupported",
        )
        self.assertEqual("unavailable", value.execution_status)
        self.assertEqual("host_unsupported", value.reason)
        self.assertNotIn("path", repr(value.public_dict()).casefold())
        self.assertNotIn("principal", repr(value.public_dict()).casefold())

    def test_invalid_or_inconsistent_states_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            SandboxExecutionStatus(1, False, "unsupported", "unavailable", "unavailable", "host_unsupported")
        with self.assertRaisesRegex(ValueError, "execution-disabled"):
            SandboxExecutionStatus(1, True, "prerequisites_met", "ready", "disabled", "supervisor_unavailable")
        with self.assertRaisesRegex(ValueError, "execution state"):
            SandboxExecutionStatus(1, True, "prerequisites_met", "ready", "ready", "execution_not_enabled")

    def test_status_is_immutable_and_contains_no_backend_identity(self):
        value = SandboxExecutionStatus.disabled()
        with self.assertRaises(FrozenInstanceError):
            value.reason = "changed"
        public = repr(value.public_dict()).casefold()
        self.assertNotIn("hyperv", public)
        self.assertNotIn("service", public)
        self.assertNotIn("transport", public)


if __name__ == "__main__":
    unittest.main()
