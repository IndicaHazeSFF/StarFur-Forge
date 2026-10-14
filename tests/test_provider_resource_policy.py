import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.provider_resource_policy import (
    CONTROL_CONCURRENCY,
    CONTROL_OUTPUT_TOKENS,
    CONTROL_VERIFIED_CANCELLATION,
    CONTROL_VRAM_BYTES,
    CONTROL_WALL_TIME,
    InferenceBackendResourceCapabilities,
    InferenceResourceProfile,
    evaluate_inference_resource_admission,
)


class ProviderResourcePolicyTests(unittest.TestCase):
    def profile(self, **changes):
        values = {
            "profile_id": "interactive",
            "max_wall_time_seconds": 30,
            "max_output_tokens": 256,
            "max_concurrent_requests": 1,
        }
        values.update(changes)
        return InferenceResourceProfile(**values)

    def capabilities(self, controls):
        return InferenceBackendResourceCapabilities("ollama.local", frozenset(controls))

    def test_exact_enforceable_controls_admit_without_starting_any_work(self):
        profile = self.profile()
        decision = evaluate_inference_resource_admission(
            profile,
            self.capabilities({
                CONTROL_WALL_TIME,
                CONTROL_OUTPUT_TOKENS,
                CONTROL_CONCURRENCY,
                CONTROL_VERIFIED_CANCELLATION,
            }),
        )
        self.assertTrue(decision.admitted)
        self.assertEqual([], decision.public_dict()["reasons"])

    def test_missing_requested_control_defers_fail_closed(self):
        profile = self.profile(max_vram_bytes=8 * 1024**3)
        decision = evaluate_inference_resource_admission(
            profile,
            self.capabilities({
                CONTROL_WALL_TIME,
                CONTROL_OUTPUT_TOKENS,
                CONTROL_CONCURRENCY,
                CONTROL_VERIFIED_CANCELLATION,
            }),
        )
        self.assertFalse(decision.admitted)
        self.assertEqual((f"control_unavailable:{CONTROL_VRAM_BYTES}",), decision.reasons)

    def test_unverified_cancellation_is_not_treated_as_enforced(self):
        decision = evaluate_inference_resource_admission(
            self.profile(),
            self.capabilities({CONTROL_WALL_TIME, CONTROL_OUTPUT_TOKENS, CONTROL_CONCURRENCY}),
        )
        self.assertEqual("deferred", decision.status)
        self.assertIn("control_unavailable:verified_cancellation", decision.reasons)

    def test_foreground_busy_defers_balanced_and_background_but_not_interactive(self):
        controls = {
            CONTROL_WALL_TIME,
            CONTROL_OUTPUT_TOKENS,
            CONTROL_CONCURRENCY,
            CONTROL_VERIFIED_CANCELLATION,
        }
        balanced = evaluate_inference_resource_admission(
            self.profile(profile_id="balanced"), self.capabilities(controls), foreground_busy=True,
        )
        interactive = evaluate_inference_resource_admission(
            self.profile(), self.capabilities(controls), foreground_busy=True,
        )
        self.assertEqual(("foreground_busy",), balanced.reasons)
        self.assertTrue(interactive.admitted)

    def test_contract_rejects_unknown_profiles_controls_and_unbounded_values(self):
        with self.assertRaises(ValueError):
            self.profile(profile_id="turbo")
        with self.assertRaises(ValueError):
            self.profile(max_wall_time_seconds=0)
        with self.assertRaises(ValueError):
            self.capabilities({"wishful_thinking"})


if __name__ == "__main__":
    unittest.main()
