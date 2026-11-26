from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.private_worker_cooperative_reap import (
    ReapAttempt, ReapState, consume_observed_exit,
)
from scripts.private_worker_mapping_observer import MappingObservationError


class CooperativeReapTests(unittest.TestCase):
    def setUp(self):
        self.clock = self.enterContext(patch("time.monotonic_ns", return_value=10))
        self.wait = Mock()

    def consume(self, attempt):
        return consume_observed_exit(attempt=attempt, deadline_ns=100,
                                     wait_once=self.wait, exited_code=1)

    def test_exact_pidfd_and_both_exit_codes(self):
        for status in (42, 127):
            with self.subTest(status=status):
                self.wait.reset_mock()
                self.wait.return_value = SimpleNamespace(si_code=1, si_status=status)
                attempt = ReapAttempt(child_pidfd=8, expected_exit=status)
                self.assertIsNone(self.consume(attempt))
                self.assertIs(attempt.state, ReapState.STATUS_CONSUMED)
                with self.assertRaises(MappingObservationError):
                    self.consume(attempt)
                self.wait.assert_called_once_with(8)

    def test_wrong_exit_signal_and_malformed_status_are_still_consumed(self):
        for row in (SimpleNamespace(si_code=1, si_status=127),
                    SimpleNamespace(si_code=2, si_status=42), object()):
            self.wait.return_value = row
            attempt = ReapAttempt(child_pidfd=8, expected_exit=42)
            with self.assertRaises(MappingObservationError):
                self.consume(attempt)
            self.assertIs(attempt.state, ReapState.STATUS_CONSUMED)

    def test_late_return_cannot_hide_reap(self):
        def wait(pidfd):
            self.assertIs(attempt.state, ReapState.WAIT_UNCONFIRMED)
            self.clock.return_value = 100
            return SimpleNamespace(si_code=1, si_status=42)

        attempt = ReapAttempt(child_pidfd=8, expected_exit=42)
        self.wait.side_effect = wait
        with self.assertRaises(MappingObservationError):
            self.consume(attempt)
        self.assertIs(attempt.state, ReapState.STATUS_CONSUMED)
        with self.assertRaises(MappingObservationError):
            self.consume(attempt)
        self.wait.assert_called_once_with(8)

    def test_wait_error_and_no_status_are_not_proof_of_reap(self):
        self.wait.return_value = None
        attempt = ReapAttempt(child_pidfd=8, expected_exit=42)
        with self.assertRaises(MappingObservationError):
            self.consume(attempt)
        self.assertIs(attempt.state, ReapState.NO_STATUS)
        self.wait.side_effect = InterruptedError()
        attempt = ReapAttempt(child_pidfd=8, expected_exit=42)
        with self.assertRaises(MappingObservationError):
            self.consume(attempt)
        self.assertIs(attempt.state, ReapState.WAIT_UNCONFIRMED)
        with self.assertRaises(MappingObservationError):
            self.consume(attempt)
        self.assertEqual(self.wait.call_count, 2)

    def test_expiry_before_wait_does_not_touch_child(self):
        attempt = ReapAttempt(child_pidfd=8, expected_exit=42)
        self.clock.return_value = 100
        with self.assertRaises(MappingObservationError):
            self.consume(attempt)
        self.assertIs(attempt.state, ReapState.NO_WAIT)
        self.wait.assert_not_called()
