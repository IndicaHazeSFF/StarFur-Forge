"""Mocked system calls only; no proc opens or native fixtures."""

import os
import signal
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from scripts.private_worker_cooperative_maps import (
    ChildHandles, bind_cooperative_child, observe_cooperative_maps,
)
from scripts.private_worker_mapping_observer import MAX_BYTES, MappingObservation, MappingObservationError
from tests.test_private_worker_mapping_observer import IDENTITY, SHAPE, maps


class MockedCooperativeOS(unittest.TestCase):
    def setUp(self):
        for i, name in enumerate(("P_PIDFD", "WEXITED", "WNOHANG", "WNOWAIT",
                                  "O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK")):
            if not hasattr(os, name):
                self.enterContext(patch.object(os, name, 1 << (i + 10), create=True))
        self.anchor = SimpleNamespace(st_mode=stat.S_IFDIR, st_dev=3, st_ino=82)
        self.child_maps = SimpleNamespace(st_mode=stat.S_IFREG, st_dev=3)
        for name, value in (("platform", patch("sys.platform", "linux")),
                            ("clock", patch("time.monotonic_ns", return_value=10)),
                            ("meta", patch("os.fstat", side_effect=self.stat_fd)),
                            ("wait", patch("os.waitid", return_value=None, create=True)),
                            ("acquire", patch("os.open", return_value=8)),
                            ("read", patch("os.read", side_effect=[maps(), b""])),
                            ("close", patch("os.close"))):
            setattr(self, name, self.enterContext(value))

    def stat_fd(self, fd):
        return {4: self.anchor, 8: self.child_maps}[fd]


class CooperativeMapsReadTests(MockedCooperativeOS):
    def observe(self, **overrides):
        return observe_cooperative_maps(4, **{
            "child_pidfd": 5, "task_identity": (3, 82), "deadline_ns": 1000,
            "identity": IDENTITY, "segments": SHAPE, **overrides,
        })

    def test_reads_only_fixed_nofollow_child_and_closes_only_own_fd(self):
        self.assertEqual(self.observe(), MappingObservation(1, len(SHAPE)))
        self.acquire.assert_called_once_with(
            "maps", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=4)
        self.close.assert_called_once_with(8)
        self.assertEqual(self.meta.call_count, 3)
        self.assertEqual(self.wait.call_count, 2)
        self.wait.assert_called_with(os.P_PIDFD, 5, os.WEXITED | os.WNOHANG | os.WNOWAIT)

    def test_expired_before_open_and_denied_open_have_no_fallback(self):
        with self.assertRaises(MappingObservationError):
            self.observe(deadline_ns=10)
        self.acquire.assert_not_called()
        self.acquire.side_effect = PermissionError("private detail")
        with self.assertRaisesRegex(MappingObservationError, "^cooperative maps observation refused$"):
            self.observe()
        self.assertEqual(self.acquire.call_count, 1)
        self.close.assert_not_called()

    def test_deadline_during_read_refuses_and_closes(self):
        self.clock.side_effect = [10, 10, 10, 10, 10, 10, 1000]
        with self.assertRaises(MappingObservationError):
            self.observe()
        self.close.assert_called_once_with(8)

    def test_overflow_is_probed_and_refused(self):
        self.read.side_effect = [b"x" * 4096] * (MAX_BYTES // 4096) + [b"x"]
        with self.assertRaises(MappingObservationError):
            self.observe()
        self.read.assert_called_with(8, 1)
        self.close.assert_called_once_with(8)

    def test_invalid_opened_type_and_final_anchor_drift_refuse(self):
        self.child_maps.st_mode = stat.S_IFIFO
        with self.assertRaises(MappingObservationError):
            self.observe()
        self.read.assert_not_called()
        self.child_maps.st_mode = stat.S_IFREG
        self.meta.side_effect = [self.anchor, self.child_maps,
                                 SimpleNamespace(st_mode=stat.S_IFDIR, st_dev=3, st_ino=99)]
        with self.assertRaises(MappingObservationError):
            self.observe()
        self.assertEqual(self.close.call_count, 2)

    def test_failed_close_cannot_publish_success(self):
        self.close.side_effect = OSError("close failed")
        with self.assertRaises(MappingObservationError):
            self.observe()

    def test_child_exit_or_lost_parentage_before_open_refuses(self):
        for result in (SimpleNamespace(si_status=0), ChildProcessError(), BlockingIOError()):
            self.wait.side_effect = [result]
            with self.subTest(result=result), self.assertRaises(MappingObservationError):
                self.observe()
        self.acquire.assert_not_called()

    def test_child_exit_during_capture_refuses_without_reaping(self):
        self.wait.side_effect = [None, SimpleNamespace(si_status=0)]
        with self.assertRaises(MappingObservationError):
            self.observe()
        self.assertEqual(self.wait.call_count, 2)
        self.wait.assert_called_with(os.P_PIDFD, 5, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        self.close.assert_called_once_with(8)


class CooperativeChildBindingTests(MockedCooperativeOS):
    def setUp(self):
        super().setUp()
        if not hasattr(os, "O_DIRECTORY"):
            self.enterContext(patch.object(os, "O_DIRECTORY", 1 << 20, create=True))
        if not hasattr(signal, "SIGCHLD"):
            self.enterContext(patch.object(signal, "SIGCHLD", 17, create=True))
        self.pidfd = self.enterContext(patch("os.pidfd_open", return_value=9, create=True))
        self.disposition = self.enterContext(patch("signal.getsignal", return_value=signal.SIG_DFL))
        self.child_maps = SimpleNamespace(st_mode=stat.S_IFDIR, st_dev=3, st_ino=83)

    def bind(self):
        return bind_cooperative_child(4, proc_identity=(3, 82), fork_pid=2, deadline_ns=1000)

    def test_pairs_exact_child_and_closes_only_acquired_handles(self):
        with self.bind() as pair:
            self.assertEqual(pair, ChildHandles(9, 8, (3, 83)))
            self.close.assert_not_called()
        self.pidfd.assert_called_once_with(2, 0)
        self.acquire.assert_called_once_with(
            "2", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=4)
        self.assertEqual(self.wait.call_count, 2)
        self.assertEqual(self.close.call_args_list, [call(8), call(9)])

    def test_no_path_lookup_if_child_not_pending_or_disposition_unsafe(self):
        self.wait.side_effect = ChildProcessError()
        with self.assertRaises(MappingObservationError), self.bind():
            self.fail("unexpected handle")
        self.close.assert_called_once_with(9)
        self.pidfd.reset_mock()
        self.disposition.return_value = signal.SIG_IGN
        with self.assertRaises(MappingObservationError), self.bind():
            self.fail("unexpected handle")
        self.acquire.assert_not_called()
        self.pidfd.assert_not_called()

    def test_exit_after_open_or_cleanup_failure_closes_both(self):
        self.wait.side_effect = [None, SimpleNamespace(si_status=0)]
        with self.assertRaises(MappingObservationError), self.bind():
            self.fail("unexpected handle")
        self.assertEqual(self.close.call_args_list, [call(8), call(9)])
        self.close.reset_mock()
        self.wait.side_effect = None
        self.close.side_effect = [OSError(), None]
        with self.assertRaises(MappingObservationError), self.bind():
            pass
        self.assertEqual(self.close.call_args_list, [call(8), call(9)])

    def test_wrong_filesystem_refuses_even_when_child_is_pending(self):
        self.child_maps.st_dev = 88
        with self.assertRaises(MappingObservationError), self.bind():
            self.fail("unexpected handle")
        self.assertEqual(self.close.call_args_list, [call(8), call(9)])
