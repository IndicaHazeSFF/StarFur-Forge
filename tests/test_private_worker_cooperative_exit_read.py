import select
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts.private_worker_cooperative_exit_abi import ExitInfoRefused
from scripts.private_worker_cooperative_exit_read import observe_worker_exit
from scripts.private_worker_cooperative_startup import Binding, WorkerExit


@unittest.skipUnless(sys.platform == "linux", "Linux API names")
class CooperativeExitReaderTests(unittest.TestCase):
    def setUp(self):
        self.binding = Binding(object(), "1" * 32, object())
        self.clock = self.enterContext(patch("time.monotonic_ns", return_value=10))
        self.enterContext(patch("os.uname", return_value=SimpleNamespace(machine="x86_64")))
        self.stat = self.enterContext(patch("os.fstat", return_value=SimpleNamespace(st_dev=4, st_ino=8)))
        self.enterContext(patch("os.get_inheritable", return_value=False))
        self.poll = Mock()
        self.poll.poll.return_value = [(5, select.POLLIN | select.POLLHUP)]
        self.enterContext(patch("select.poll", return_value=self.poll))
        self.ioctl = self.enterContext(patch("fcntl.ioctl"))
        self.ioctl.side_effect = self.respond

    def respond(self, fd, request, buffer, mutate):
        self.assertEqual((fd, request, mutate), (5, 0xc040ff0b, True))
        self.assertEqual(bytes(buffer), b"\x08" + b"\0" * 63)
        struct.pack_into("<i", buffer, 60, 9)
        return 0

    def observe(self):
        return observe_worker_exit(5, expected_identity=(4, 8),
                                   binding=self.binding, expires_ns=20)

    def test_exact_query_returns_raw_exit_not_success(self):
        self.assertEqual(self.observe(), WorkerExit(self.binding, 10, True, True, 9))
        self.poll.poll.assert_called_once_with(0)
        self.assertEqual(self.ioctl.call_count, 1)

    def test_not_ready_wrong_handle_or_poll_error_never_queries(self):
        for events in ([], [(6, select.POLLIN)], [(5, select.POLLIN | select.POLLERR)]):
            self.poll.poll.return_value = events
            with self.assertRaises(ExitInfoRefused):
                self.observe()
        self.ioctl.assert_not_called()

    def test_handle_identity_checked_before_and_after(self):
        good = self.stat.return_value
        bad = SimpleNamespace(st_dev=4, st_ino=9)
        self.stat.return_value = bad
        with self.assertRaises(ExitInfoRefused):
            self.observe()
        self.ioctl.assert_not_called()
        self.stat.side_effect = [good, bad]
        with self.assertRaises(ExitInfoRefused):
            self.observe()
        self.assertEqual(self.ioctl.call_count, 1)

    def test_ioctl_error_or_expiry_refuses_without_retry(self):
        self.ioctl.side_effect = OSError("not supported")
        with self.assertRaises(ExitInfoRefused):
            self.observe()
        self.assertEqual(self.ioctl.call_count, 1)
        self.ioctl.side_effect = self.respond
        self.clock.side_effect = [10, 11, 20]
        with self.assertRaises(ExitInfoRefused):
            self.observe()
        self.assertEqual(self.ioctl.call_count, 2)

    def test_zero_sized_field_without_returned_exit_bit_refuses(self):
        def no_exit(fd, request, buffer, mutate):
            struct.pack_into("<Q", buffer, 0, 0)
            return 0
        self.ioctl.side_effect = no_exit
        with self.assertRaises(ExitInfoRefused):
            self.observe()
