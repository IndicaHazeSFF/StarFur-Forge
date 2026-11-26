from dataclasses import replace
import unittest

from scripts.private_worker_cooperative_startup import (
    Binding, Phase, StartupRefused, StartupReview, WorkerExit, go_is_current,
)


class CooperativeStartupTests(unittest.TestCase):
    def setUp(self):
        self.attempt = object()
        self.binding = Binding(self.attempt, "1" * 32, object())
        self.review = StartupReview(attempt=self.attempt, expires=100)

    def acknowledge(self):
        self.review.charge(now=10, preflight=True)
        self.review.acknowledge_start(now=20, acknowledged=True)

    def bind(self):
        self.acknowledge()
        self.review.bind(now=30, binding=self.binding, ready=True, pin_verified=True)

    def issue(self):
        self.bind()
        return self.review.issue_go(now=40, current=self.binding)

    def result(self):
        self.issue()
        self.review.result(now=50, binding=self.binding, positive=42, negative=127)

    def retire(self, **overrides):
        fields = dict(now=60, binding=self.binding,
                      worker_exit=WorkerExit(self.binding, 55, True, True, 0),
                      descendants_exited=True, unit_collected=True, cgroup_absent=True,
                      parent_unchanged=True, epoch_continuity=True)
        self.review.retire(**(fields | overrides))

    def test_clean_self_exit_needs_retirement_and_fixture_cleanup(self):
        self.result()
        self.retire()
        self.assertIs(self.review.phase, Phase.RETIRED)
        self.review.finish(now=70, fixture_cleanup_verified=True)
        self.assertIs(self.review.phase, Phase.PASSED)

    def test_collected_unit_and_good_cases_do_not_substitute_for_exact_exit(self):
        for field, value in (
            ("readable", False), ("exit_present", False), ("exit_present", 1),
            ("raw_status", 1 << 8), ("raw_status", 42 << 8), ("raw_status", 9),
            ("raw_status", False), ("at", 49), ("at", 61),
        ):
            with self.subTest(field=field, value=value):
                self.setUp()
                self.result()
                observation = replace(WorkerExit(self.binding, 55, True, True, 0), **{field: value})
                with self.assertRaises(StartupRefused):
                    self.retire(worker_exit=observation)
                self.assertIs(self.review.phase, Phase.REFUSED)

    def test_missing_or_rebound_exit_evidence_refuses(self):
        for missing in (True, False):
            self.setUp()
            self.result()
            result = None if missing else WorkerExit(replace(self.binding), 55, True, True, 0)
            with self.assertRaises(StartupRefused):
                self.retire(worker_exit=result)

    def test_clean_worker_exit_cannot_hide_incomplete_cleanup(self):
        for field in ("descendants_exited", "unit_collected", "cgroup_absent", "parent_unchanged"):
            with self.subTest(field=field):
                self.setUp()
                self.result()
                with self.assertRaises(StartupRefused):
                    self.retire(**{field: False})

    def test_lost_start_reply_cannot_retry_or_adopt_late_worker(self):
        self.review.charge(now=10, preflight=True)
        with self.assertRaises(StartupRefused):
            self.review.acknowledge_start(now=20, acknowledged=False)
        self.assertTrue(self.review.charged)
        with self.assertRaises(StartupRefused):
            self.review.charge(now=30, preflight=True)
        with self.assertRaises(StartupRefused):
            self.review.bind(now=30, binding=self.binding, ready=True, pin_verified=True)
        self.assertIs(self.review.phase, Phase.REFUSED)

    def test_interruption_does_not_replenish_charge(self):
        for after_charge in (False, True):
            with self.subTest(after_charge=after_charge):
                self.setUp()
                if after_charge:
                    self.review.charge(now=10, preflight=True)
                with self.assertRaises(StartupRefused):
                    self.review.refuse()
                self.assertIs(self.review.charged, after_charge)
                with self.assertRaises(StartupRefused):
                    self.review.charge(now=20, preflight=True)

    def test_missing_ready_then_late_ready_is_terminal(self):
        self.acknowledge()
        with self.assertRaises(StartupRefused):
            self.review.bind(now=30, binding=self.binding, ready=False, pin_verified=True)
        with self.assertRaises(StartupRefused):
            self.review.bind(now=40, binding=self.binding, ready=True, pin_verified=True)

    def test_delayed_activation_and_wrong_epochs_refuse(self):
        for now, epoch in ((100, "1"*32), (30, "0"*32), (30, "unknown")):
            with self.subTest(now=now, epoch=epoch):
                self.setUp()
                self.acknowledge()
                with self.assertRaises(StartupRefused):
                    self.review.bind(now=now, binding=Binding(self.attempt, epoch, object()),
                                     ready=True, pin_verified=True)

    def test_epoch_replacement_before_release_and_collection(self):
        self.bind()
        with self.assertRaises(StartupRefused):
            self.review.issue_go(now=40, current=Binding(self.attempt, "2"*32, object()))
        self.setUp()
        self.result()
        with self.assertRaises(StartupRefused):
            self.retire(epoch_continuity=False)
        with self.assertRaises(StartupRefused):
            self.review.finish(now=70, fixture_cleanup_verified=True)

    def test_go_uses_same_absolute_expiry_and_binding(self):
        go = self.issue()
        self.assertTrue(go_is_current(go, binding=self.binding, expires=100, now=99))
        self.assertFalse(go_is_current(go, binding=self.binding, expires=100, now=100))
        self.assertFalse(go_is_current(go, binding=self.binding, expires=200, now=101))
        with self.assertRaises(StartupRefused):
            self.review.issue_go(now=41, current=self.binding)

    def test_disconnect_after_go_and_late_retirement_do_not_promote_failure(self):
        self.issue()
        with self.assertRaises(StartupRefused):
            self.review.refuse()
        with self.assertRaises(StartupRefused):
            self.review.result(now=50, binding=self.binding, positive=42, negative=127)
        self.setUp()
        self.result()
        with self.assertRaises(StartupRefused):
            self.retire(now=100)
        self.assertIs(self.review.phase, Phase.REFUSED)
