from contextlib import contextmanager
from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from scripts.private_worker_cooperative_exit_abi import ExitInfoRefused
from scripts.private_worker_cooperative_startup import (
    Binding, Phase, StartupRefused, StartupReview, WorkerExit,
)
from scripts.private_worker_cooperative_supervisor import (
    CaseResults, PinnedWorker, Retirement, complete_acknowledged_attempt,
)


class CooperativeSupervisorTests(unittest.TestCase):
    def make_case(self):
        token = object()
        binding = Binding(token, "1" * 32, object())
        review = StartupReview(attempt=token, expires=100)
        review.charge(now=1, preflight=True)
        review.acknowledge_start(now=2, acknowledged=True)
        pin = PinnedWorker(binding, 17, (3, 9))
        owner = Mock()

        @contextmanager
        def acquire(deadline):
            owner.acquire(deadline)
            try:
                yield pin
            finally:
                owner.release(pin)

        owner.acquire_verified_pin.side_effect = acquire
        owner.recheck_pin.return_value = binding
        owner.read_cases.return_value = CaseResults(binding, 42, 127)
        owner.await_retirement.return_value = Retirement(binding, True, True, True, True, True)
        owner.observe_worker_exit.return_value = WorkerExit(binding, 20, True, True, 0)
        owner.cleanup_exact_fixture.return_value = True
        return review, pin, owner

    def run_attempt(self, review, owner):
        module = "scripts.private_worker_cooperative_supervisor"
        with patch(module + ".time.monotonic_ns", side_effect=owner.clock), patch(
                module + ".observe_worker_exit", owner.observe_worker_exit):
            complete_acknowledged_attempt(
                review, acquire_verified_pin=owner.acquire_verified_pin,
                recheck_pin=owner.recheck_pin, publish_go=owner.publish_go,
                read_cases=owner.read_cases, await_retirement=owner.await_retirement,
                cleanup_exact_fixture=owner.cleanup_exact_fixture,
            )

    def setup_attempt(self):
        review, pin, owner = self.make_case()
        owner.clock.return_value = 20
        return review, pin, owner

    def test_exact_pidfd_is_held_from_before_go_through_retirement(self):
        review, pin, owner = self.setup_attempt()
        self.run_attempt(review, owner)
        self.assertIs(review.phase, Phase.PASSED)
        self.assertEqual([c[0] for c in owner.mock_calls if c[0] != "clock"],
                         ["acquire_verified_pin", "acquire", "recheck_pin", "publish_go",
                          "read_cases", "await_retirement", "observe_worker_exit",
                          "release", "cleanup_exact_fixture"])
        owner.observe_worker_exit.assert_called_once_with(
            pin.pidfd, expected_identity=pin.identity, binding=pin.binding, expires_ns=100)
        self.assertIs(owner.publish_go.call_args.args[0].binding, pin.binding)
        with self.assertRaises(StartupRefused):
            self.run_attempt(review, owner)
        self.assertEqual(owner.publish_go.call_count, 1)

    def test_binding_replacement_refuses_before_go(self):
        review, pin, owner = self.setup_attempt()
        owner.recheck_pin.return_value = replace(pin.binding)
        with self.assertRaises(StartupRefused):
            self.run_attempt(review, owner)
        self.assertIs(review.phase, Phase.REFUSED)
        owner.publish_go.assert_not_called()
        owner.release.assert_called_once_with(pin)
        owner.cleanup_exact_fixture.assert_not_called()

    def test_ambiguous_go_or_missing_exit_retains_fixture_and_refuses_retry(self):
        for stage, error in (("publish_go", TimeoutError()), ("observe_worker_exit", ExitInfoRefused())):
            with self.subTest(stage=stage):
                review, pin, owner = self.setup_attempt()
                getattr(owner, stage).side_effect = error
                with self.assertRaises(type(error)):
                    self.run_attempt(review, owner)
                self.assertIs(review.phase, Phase.REFUSED)
                with self.assertRaises(StartupRefused):
                    self.run_attempt(review, owner)
                self.assertEqual(owner.publish_go.call_count, 1)
                owner.release.assert_called_once_with(pin)
                owner.cleanup_exact_fixture.assert_not_called()

    def test_wrong_cases_exit_or_teardown_never_cleans_fixture(self):
        for failure in ("cases", "exit", "teardown", "close"):
            with self.subTest(failure=failure):
                review, pin, owner = self.setup_attempt()
                if failure == "cases":
                    owner.read_cases.return_value = CaseResults(pin.binding, 42, 0)
                elif failure == "exit":
                    owner.observe_worker_exit.return_value = WorkerExit(pin.binding, 20, True, True, 9)
                elif failure == "teardown":
                    owner.await_retirement.return_value = replace(
                        owner.await_retirement.return_value, epoch_continuity=False)
                else:
                    owner.release.side_effect = OSError()
                with self.assertRaises((StartupRefused, OSError)):
                    self.run_attempt(review, owner)
                owner.cleanup_exact_fixture.assert_not_called()
                self.assertIs(review.phase, Phase.REFUSED)

    def test_expiry_during_handle_close_fences_cleanup(self):
        review, pin, owner = self.setup_attempt()
        owner.release.side_effect = lambda _pin: setattr(owner.clock, "return_value", 100)
        with self.assertRaises(StartupRefused):
            self.run_attempt(review, owner)
        owner.cleanup_exact_fixture.assert_not_called()
