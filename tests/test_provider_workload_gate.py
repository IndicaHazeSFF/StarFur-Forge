import unittest
from pathlib import Path
import sys
import tempfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.provider_workload_gate import ProviderWorkloadGate
from pipeline.provider_process_gate import ProviderProcessGate


class ProviderWorkloadGateTests(unittest.TestCase):
    def test_capacity_is_immediate_exact_and_released_only_by_its_lease(self):
        gate = ProviderWorkloadGate({"ollama": 1}, id_factory=iter(("a" * 24, "b" * 24)).__next__)
        first = gate.try_acquire("ollama", 1)
        self.assertEqual("admitted", first.status)
        self.assertEqual(1, gate.active_count("ollama"))
        self.assertEqual("deferred", gate.try_acquire("ollama", 1).status)
        self.assertTrue(gate.release(first.lease))
        self.assertFalse(gate.release(first.lease))
        self.assertEqual(0, gate.active_count("ollama"))
        self.assertEqual("admitted", gate.try_acquire("ollama", 1).status)

    def test_existing_stricter_profile_closes_shared_capacity(self):
        gate = ProviderWorkloadGate({"ollama": 2})
        strict = gate.try_acquire("ollama", 1)
        self.assertEqual("admitted", strict.status)
        self.assertEqual("deferred", gate.try_acquire("ollama", 2).status)

    def test_unconfigured_provider_and_foreign_lease_fail_closed(self):
        first = ProviderWorkloadGate({"ollama": 1})
        second = ProviderWorkloadGate({"ollama": 1})
        admission = first.try_acquire("ollama", 1)
        with self.assertRaisesRegex(ValueError, "not configured"):
            first.try_acquire("other", 1)
        self.assertFalse(second.release(admission.lease))
        self.assertEqual(1, first.active_count("ollama"))

    def test_optional_process_gate_composes_without_exposing_its_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first = ProviderWorkloadGate(
                {"ollama": 1}, process_gate=ProviderProcessGate(root),
            )
            second = ProviderWorkloadGate(
                {"ollama": 1}, process_gate=ProviderProcessGate(root),
            )

            admitted = first.try_acquire("ollama", 1)
            self.assertEqual("admitted", admitted.status)
            self.assertEqual("deferred", second.try_acquire("ollama", 1).status)
            self.assertFalse(hasattr(admitted.lease, "descriptor"))
            self.assertTrue(first.release(admitted.lease))
            recovered = second.try_acquire("ollama", 1)
            self.assertEqual("admitted", recovered.status)
            self.assertTrue(second.release(recovered.lease))

    def test_process_gate_rejects_unsupported_multi_capacity_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "exactly one"):
                ProviderWorkloadGate(
                    {"ollama": 2},
                    process_gate=ProviderProcessGate(Path(directory).resolve()),
                )


if __name__ == "__main__":
    unittest.main()
