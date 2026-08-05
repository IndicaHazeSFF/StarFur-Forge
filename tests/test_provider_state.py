import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.provider_state import ProviderLifecycle, ProviderLifecycleState

class ProviderLifecycleTests(unittest.TestCase):
    def test_generation_lifecycle_is_deterministic(self):
        lifecycle = ProviderLifecycle("Fake", "test-model")
        self.assertEqual(lifecycle.public_dict()["state"], "disconnected")
        lifecycle.begin_generation(stream=False)
        self.assertEqual(lifecycle.public_dict()["state"], "generating")
        lifecycle.finish()
        self.assertEqual(lifecycle.public_dict()["state"], "idle")
        self.assertEqual(lifecycle.public_dict()["previous_state"], "generating")

    def test_streaming_and_error_are_visible(self):
        lifecycle = ProviderLifecycle("Fake", "test-model")
        lifecycle.begin_generation(stream=True)
        self.assertEqual(lifecycle.snapshot().state, "streaming")
        lifecycle.fail("offline")
        snapshot = lifecycle.public_dict()
        self.assertEqual(snapshot["state"], "error")
        self.assertEqual(snapshot["error"], "offline")

    def test_invalid_transition_is_rejected(self):
        lifecycle = ProviderLifecycle("Fake", "test-model")
        with self.assertRaises(ValueError):
            lifecycle.transition(ProviderLifecycleState.STREAMING)

if __name__ == "__main__":
    unittest.main()