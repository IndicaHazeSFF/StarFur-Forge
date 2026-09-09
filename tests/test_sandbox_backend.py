import math
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_backend import (
    BackendDescriptor,
    BackendObservation,
    EnforcementProfile,
    ExecutionLimits,
    SANDBOX_BACKEND_SCHEMA_VERSION,
    evaluate_backend_readiness,
)


ALL_DIMENSIONS = (
    "wall_time", "cpu", "memory", "process_count", "disk", "input",
    "stdout", "stderr", "artifacts", "concurrency", "filesystem_isolation",
    "process_isolation", "network_isolation", "cleanup",
)
DEFAULT_EVIDENCE = object()


def limits(**overrides):
    values = {
        "wall_time_seconds": 30.0,
        "cpu_cores": 2,
        "memory_bytes": 512 * 1024 * 1024,
        "process_count": 32,
        "disk_bytes": 256 * 1024 * 1024,
        "input_bytes": 256 * 1024,
        "stdout_bytes": 64 * 1024,
        "stderr_bytes": 64 * 1024,
        "artifact_count": 8,
        "artifact_bytes": 16 * 1024 * 1024,
        "concurrency": 1,
    }
    values.update(overrides)
    return ExecutionLimits(**values)


def descriptor(**overrides):
    values = {
        "schema_version": 1,
        "backend_id": "hyperv-managed",
        "backend_version": 1,
        "isolation_class": "hardware_vm",
        "host_families": ("windows",),
        "guest_families": ("linux",),
        "supported_task_kinds": ("python_tests",),
        "supported_profile_ids": ("offline-python-v1",),
        "image_revision": "image-001",
        "supervisor_revision": "supervisor-001",
    }
    values.update(overrides)
    return BackendDescriptor(**values)


def profile(**overrides):
    values = {
        "schema_version": 1,
        "profile_id": "offline-python-v1",
        "policy_revision": "policy-001",
        "required_isolation_class": "hardware_vm",
        "task_kinds": ("python_tests",),
        "network_mode": "disabled",
        "required_dimensions": ALL_DIMENSIONS,
        "maximum_limits": limits(),
    }
    values.update(overrides)
    return EnforcementProfile(**values)


def observation(**overrides):
    values = {
        "schema_version": 1,
        "backend_id": "hyperv-managed",
        "backend_version": 1,
        "state": "available",
        "evidence_revision": "evidence-001",
        "observed_at_epoch": 100.0,
        "expires_at_epoch": 200.0,
        "isolation_class": "hardware_vm",
        "profile_id": "offline-python-v1",
        "policy_revision": "policy-001",
        "image_revision": "image-001",
        "supervisor_revision": "supervisor-001",
        "enforced_dimensions": ALL_DIMENSIONS,
        "enforced_limits": limits(),
    }
    values.update(overrides)
    return BackendObservation(**values)


class SandboxBackendContractTests(unittest.TestCase):
    def evaluate(
        self, *, backend=None, policy=None, evidence=DEFAULT_EVIDENCE,
        requested=None, now=150.0,
    ):
        return evaluate_backend_readiness(
            backend or descriptor(),
            policy or profile(),
            observation() if evidence is DEFAULT_EVIDENCE else evidence,
            task_kind="python_tests",
            requested_limits=requested or limits(),
            now_epoch=now,
        )

    def test_contracts_are_immutable_bounded_and_strictly_versioned(self):
        item = descriptor()
        with self.assertRaises(FrozenInstanceError):
            item.backend_id = "changed"
        with self.assertRaises((TypeError, ValueError)):
            descriptor(schema_version=True)
        with self.assertRaises(ValueError):
            descriptor(schema_version=SANDBOX_BACKEND_SCHEMA_VERSION + 1)
        with self.assertRaises(ValueError):
            descriptor(supported_task_kinds=("python_tests", "python_tests"))
        with self.assertRaises(ValueError):
            descriptor(backend_id="Provider Says Secure")

    def test_limits_reject_boolean_nonfinite_zero_and_unsupported_network_modes(self):
        with self.assertRaises(TypeError):
            limits(cpu_cores=True)
        with self.assertRaises(ValueError):
            limits(wall_time_seconds=math.nan)
        with self.assertRaises(ValueError):
            limits(process_count=0)
        with self.assertRaises(ValueError):
            profile(network_mode="allow_all")

    def test_explicit_matching_evidence_can_produce_compatibility_readiness(self):
        result = self.evaluate()
        self.assertTrue(result.ready)
        self.assertEqual(result.reason, "ready")
        self.assertEqual(result.evidence_revision, "evidence-001")
        self.assertNotIn("grant", result.public_dict())
        self.assertNotIn("approval", result.public_dict())

    def test_backend_name_or_boolean_never_implies_readiness(self):
        missing = self.evaluate(evidence=None)
        malformed = self.evaluate(evidence=True)
        self.assertEqual(missing.reason, "observation_missing")
        self.assertEqual(malformed.reason, "observation_invalid")

    def test_observation_times_reject_boolean_nonfinite_and_excessive_lifetime(self):
        with self.assertRaises(TypeError):
            observation(observed_at_epoch=True)
        with self.assertRaises(ValueError):
            observation(expires_at_epoch=math.inf)
        with self.assertRaises(ValueError):
            observation(observed_at_epoch=100.0, expires_at_epoch=4000.1)

    def test_unprobed_unsupported_unavailable_and_stale_evidence_deny(self):
        expected = {
            "unprobed": "backend_unprobed",
            "unsupported": "backend_unsupported",
            "unavailable": "backend_unavailable",
        }
        for state, reason in expected.items():
            with self.subTest(state=state):
                self.assertEqual(self.evaluate(evidence=observation(state=state)).reason, reason)
        self.assertEqual(self.evaluate(evidence=observation(), now=200.0).reason, "observation_stale")
        self.assertEqual(self.evaluate(evidence=observation(), now=99.0).reason, "observation_stale")

    def test_exact_task_profile_and_revision_bindings_are_required(self):
        unsupported_task = evaluate_backend_readiness(
            descriptor(), profile(), observation(), task_kind="rust_tests",
            requested_limits=limits(), now_epoch=150.0,
        )
        self.assertEqual(unsupported_task.reason, "task_unsupported")
        self.assertEqual(
            self.evaluate(backend=descriptor(supported_profile_ids=("other-profile",))).reason,
            "profile_unsupported",
        )
        for changed in (
            {"backend_id": "other-backend"},
            {"backend_version": 2},
            {"policy_revision": "policy-002"},
            {"image_revision": "image-002"},
            {"supervisor_revision": "supervisor-002"},
            {"isolation_class": "container"},
        ):
            with self.subTest(changed=changed):
                self.assertEqual(self.evaluate(evidence=observation(**changed)).reason, "binding_mismatch")

    def test_missing_enforcement_or_insufficient_limits_deny(self):
        missing = tuple(item for item in ALL_DIMENSIONS if item != "network_isolation")
        self.assertEqual(
            self.evaluate(evidence=observation(enforced_dimensions=missing)).reason,
            "enforcement_missing",
        )
        requested = limits(memory_bytes=1024 * 1024 * 1024)
        self.assertEqual(self.evaluate(requested=requested).reason, "limits_unsupported")
        constrained = observation(enforced_limits=limits(stdout_bytes=1024))
        self.assertEqual(self.evaluate(evidence=constrained).reason, "limits_unsupported")

    def test_disabled_backend_and_zero_provider_operation_are_deterministic(self):
        disabled = descriptor(
            backend_id="disabled",
            isolation_class="disabled",
            guest_families=(),
            supported_task_kinds=(),
            supported_profile_ids=(),
        )
        result = evaluate_backend_readiness(
            disabled, profile(), None, task_kind="python_tests",
            requested_limits=limits(), now_epoch=150.0,
        )
        self.assertFalse(result.ready)
        self.assertEqual(result.reason, "backend_disabled")


if __name__ == "__main__":
    unittest.main()
