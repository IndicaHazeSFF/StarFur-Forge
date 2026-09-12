from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_supervisor_readiness import (
    SUPERVISOR_ENFORCEMENT_DIMENSIONS,
    SupervisorTransportObservation,
    SupervisorTransportProfile,
    evaluate_supervisor_transport_readiness,
)


def profile(**overrides):
    values = {
        "schema_version": 1,
        "profile_id": "hyperv-offline-python",
        "backend_id": "hyperv-managed",
        "service_id": "starfur.sandbox.supervisor",
        "service_revision": "supervisor-v1",
        "transport_kind": "local-authenticated-ipc",
        "transport_revision": "transport-v1",
        "policy_revision": "policy-v1",
        "required_dimensions": tuple(SUPERVISOR_ENFORCEMENT_DIMENSIONS),
    }
    values.update(overrides)
    return SupervisorTransportProfile(**values)


def observation(**overrides):
    values = {
        "schema_version": 1,
        "evidence_revision": "evidence-v1",
        "state": "available",
        "observed_at": 1000.0,
        "expires_at": 1100.0,
        "profile_id": "hyperv-offline-python",
        "backend_id": "hyperv-managed",
        "service_id": "starfur.sandbox.supervisor",
        "service_revision": "supervisor-v1",
        "transport_kind": "local-authenticated-ipc",
        "transport_revision": "transport-v1",
        "policy_revision": "policy-v1",
        "verified_dimensions": tuple(SUPERVISOR_ENFORCEMENT_DIMENSIONS),
    }
    values.update(overrides)
    return SupervisorTransportObservation(**values)


def evaluate(value=None, *, host="prerequisites_met", now=1001.0):
    return evaluate_supervisor_transport_readiness(
        profile(), value, host_status=host, now=now,
    )


class SandboxSupervisorReadinessTests(unittest.TestCase):
    def test_complete_synthetic_evidence_is_ready_but_not_authority(self):
        result = evaluate(observation())
        self.assertTrue(result.ready)
        self.assertEqual("ready", result.reason)
        public = repr(result.public_dict()).casefold()
        self.assertNotIn("principal", public)
        self.assertNotIn("key", public)
        self.assertNotIn("grant", public)
        self.assertNotIn("approval", public)

    def test_host_state_denies_before_supervisor_evidence(self):
        expected = {
            "unprobed": "host_unprobed",
            "unsupported": "host_unsupported",
            "unavailable": "host_unavailable",
        }
        for state, reason in expected.items():
            with self.subTest(state=state):
                self.assertEqual(reason, evaluate(observation(), host=state).reason)

    def test_missing_and_declared_states_fail_closed(self):
        self.assertEqual("observation_missing", evaluate(None).reason)
        expected = {
            "unprobed": "supervisor_unprobed",
            "unsupported": "supervisor_unsupported",
            "unavailable": "supervisor_unavailable",
        }
        for state, reason in expected.items():
            with self.subTest(state=state):
                self.assertEqual(reason, evaluate(observation(state=state)).reason)

    def test_stale_future_and_mismatched_observations_deny(self):
        self.assertEqual("observation_stale", evaluate(observation(), now=1100.0).reason)
        self.assertEqual("observation_stale", evaluate(observation(), now=999.0).reason)
        for field in (
            "profile_id", "backend_id", "service_id", "service_revision",
            "transport_kind", "transport_revision", "policy_revision",
        ):
            with self.subTest(field=field):
                self.assertEqual(
                    "binding_mismatch",
                    evaluate(observation(**{field: "other-v1"})).reason,
                )

    def test_every_required_enforcement_dimension_must_be_verified(self):
        all_dimensions = tuple(SUPERVISOR_ENFORCEMENT_DIMENSIONS)
        for missing in all_dimensions:
            with self.subTest(missing=missing):
                supplied = tuple(item for item in all_dimensions if item != missing)
                self.assertEqual(
                    "enforcement_missing",
                    evaluate(observation(verified_dimensions=supplied)).reason,
                )

    def test_contracts_are_immutable_bounded_and_reject_unknown_claims(self):
        value = profile()
        with self.assertRaises(FrozenInstanceError):
            value.backend_id = "changed"
        with self.assertRaisesRegex(ValueError, "dimensions"):
            profile(required_dimensions=("secure",))
        with self.assertRaisesRegex(ValueError, "lifetime"):
            observation(expires_at=1400.1)
        with self.assertRaisesRegex(ValueError, "host status"):
            evaluate_supervisor_transport_readiness(
                value, observation(), host_status="healthy", now=1001.0,
            )

    def test_import_and_evaluation_have_no_probe_or_transport_side_effect(self):
        with patch("subprocess.run", side_effect=AssertionError("must not run")):
            result = evaluate(None, host="unsupported")
        self.assertEqual("host_unsupported", result.reason)


if __name__ == "__main__":
    unittest.main()
