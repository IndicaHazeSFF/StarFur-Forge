"""Mock-only positive readiness/capture/release regressions."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import os

from scripts.private_worker_cooperative_exchange import (
    ReleaseAttempt, ReleaseState, capture_and_release, observe_missing_leaf,
)
from scripts.private_worker_cooperative_maps import ChildHandles
from scripts.private_worker_mapping_observer import MappingObservation, MappingObservationError


class CooperativeExchangeTests(unittest.TestCase):
    def setUp(self):
        m = "scripts.private_worker_cooperative_exchange"
        self.enterContext(patch("sys.platform", "linux"))
        self.clock = self.enterContext(patch("time.monotonic_ns", return_value=10))
        self.poll = Mock()
        self.poll.poll.return_value = [(4, 1)]
        self.enterContext(patch(f"{m}.select", SimpleNamespace(
            poll=lambda: self.poll, POLLIN=1, POLLHUP=16)))
        self.blocking = self.enterContext(patch("os.get_blocking", return_value=False))
        self.read = self.enterContext(patch("os.read", side_effect=[b"R", b""]))
        self.write = self.enterContext(patch("os.write", return_value=1))
        self.capture = self.enterContext(patch(f"{m}.observe_cooperative_maps",
                                               return_value=MappingObservation(1, 2)))
        self.pending = self.enterContext(patch(f"{m}._pending", return_value=True))

    def exchange(self, attempt=None):
        return capture_and_release(child=ChildHandles(6, 7, (3, 9)),
                                   ready_reader=4, release_writer=5, deadline_ns=1000,
                                   identity=(8, 1, 77), segments=(),
                                   attempt=ReleaseAttempt() if attempt is None else attempt)

    def test_capture_precedes_exact_release(self):
        self.capture.side_effect = lambda *a, **kw: (
            self.write.assert_not_called() or MappingObservation(1, 2))
        self.assertEqual(self.exchange(), MappingObservation(1, 2))
        self.capture.assert_called_once_with(7, child_pidfd=6, task_identity=(3, 9),
                                             deadline_ns=1000, identity=(8, 1, 77), segments=())
        self.pending.assert_called_once_with(6)
        self.write.assert_called_once_with(5, b"G")

    def test_extra_marker_or_early_eof_never_releases(self):
        for data in ([b"RR"], [b""], [b"R", b"R"]):
            self.read.side_effect = data
            with self.subTest(data=data), self.assertRaises(MappingObservationError):
                self.exchange()
        self.capture.assert_not_called()
        self.write.assert_not_called()

    def test_missing_eof_or_poll_failure_never_releases(self):
        self.poll.poll.side_effect = [[(4, 1)], []]
        with self.assertRaises(MappingObservationError):
            self.exchange()
        self.capture.assert_not_called()
        self.write.assert_not_called()

    def test_capture_failure_exit_and_expiry_never_release(self):
        self.capture.side_effect = MappingObservationError("rejected")
        with self.assertRaises(MappingObservationError):
            self.exchange()
        self.capture.side_effect = None
        self.read.side_effect = [b"R", b""]
        self.pending.return_value = False
        with self.assertRaises(MappingObservationError):
            self.exchange()
        self.pending.return_value = True
        self.read.side_effect = [b"R", b""]
        self.clock.side_effect = [10] * 7 + [1000]
        with self.assertRaises(MappingObservationError):
            self.exchange()
        self.write.assert_not_called()

    def test_failed_write_is_not_retried_or_reported_as_success(self):
        attempt = ReleaseAttempt()
        self.write.side_effect = BrokenPipeError()
        with self.assertRaises(MappingObservationError):
            self.exchange(attempt)
        self.assertIs(attempt.state, ReleaseState.WRITE_UNCONFIRMED)
        with self.assertRaises(MappingObservationError):
            self.exchange(attempt)
        self.write.assert_called_once_with(5, b"G")

    def test_late_write_is_recorded_even_though_acceptance_refuses(self):
        attempt = ReleaseAttempt()

        def late_write(*args):
            self.assertIs(attempt.state, ReleaseState.WRITE_UNCONFIRMED)
            self.clock.return_value = 1000
            return 1

        self.write.side_effect = late_write
        with self.assertRaises(MappingObservationError):
            self.exchange(attempt)
        self.assertIs(attempt.state, ReleaseState.BYTE_WRITTEN)
        with self.assertRaises(MappingObservationError):
            self.exchange(attempt)
        self.write.assert_called_once_with(5, b"G")

    def test_early_refusal_is_no_write_but_attempt_cannot_be_reused(self):
        attempt = ReleaseAttempt()
        self.read.side_effect = [b""]
        with self.assertRaises(MappingObservationError):
            self.exchange(attempt)
        self.assertIs(attempt.state, ReleaseState.NO_WRITE)
        self.read.side_effect = [b"R", b""]
        with self.assertRaises(MappingObservationError):
            self.exchange(attempt)
        self.read.assert_called_once()
        self.write.assert_not_called()

    def negative(self):
        return observe_missing_leaf(child_pidfd=6, ready_reader=4, deadline_ns=1000)

    def set_negative(self):
        self.read.side_effect = [b""]
        self.poll.poll.side_effect = [[(4, 16)], [(6, 1)]]
        for i, name in enumerate(("P_PIDFD", "WEXITED", "WNOHANG", "WNOWAIT", "CLD_EXITED")):
            if not hasattr(os, name):
                self.enterContext(patch.object(os, name, 1 << (8 + i), create=True))
        return self.enterContext(patch("os.waitid", create=True,
             return_value=SimpleNamespace(si_code=os.CLD_EXITED, si_status=127)))

    def test_negative_observes_exact_child_without_reaping_or_releasing(self):
        wait = self.set_negative()
        self.assertIsNone(self.negative())
        wait.assert_called_once_with(os.P_PIDFD, 6, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        self.write.assert_not_called()
        self.capture.assert_not_called()

    def test_negative_readiness_or_timeout_refuses_before_wait(self):
        wait = self.set_negative()
        self.read.side_effect = [b"R"]
        with self.assertRaises(MappingObservationError):
            self.negative()
        self.read.side_effect = [b""]
        self.poll.poll.side_effect = [[(4, 16)], []]
        with self.assertRaises(MappingObservationError):
            self.negative()
        wait.assert_not_called()
        self.write.assert_not_called()

    def test_negative_expiry_after_observation_does_not_consume_status(self):
        wait = self.set_negative()
        def observe(*args):
            self.clock.return_value = 1000
            return SimpleNamespace(si_code=os.CLD_EXITED, si_status=127)

        wait.side_effect = observe
        with self.assertRaises(MappingObservationError):
            self.negative()
        wait.assert_called_once_with(os.P_PIDFD, 6, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        self.write.assert_not_called()

    def test_negative_wrong_exit_or_signal_refuses_without_releasing(self):
        wait = self.set_negative()
        for row in (None, SimpleNamespace(si_code=os.CLD_EXITED, si_status=42),
                    SimpleNamespace(si_code=-1, si_status=127)):
            self.read.side_effect = [b""]
            self.poll.poll.side_effect = [[(4, 16)], [(6, 1)]]
            wait.return_value = row
            with self.subTest(row=row), self.assertRaises(MappingObservationError):
                self.negative()
        self.write.assert_not_called()
