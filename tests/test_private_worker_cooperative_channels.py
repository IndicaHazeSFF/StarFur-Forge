"""Mocked role split and exact descriptor cleanup; no pipes are created."""

import os
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from scripts.private_worker_cooperative_channels import create_cooperative_channels
from scripts.private_worker_cooperative_fds import DescriptorReviewError, Direction, PipeEnd


class CooperativeChannelTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("sys.platform", "linux"))
        for i, name in enumerate(("O_CLOEXEC", "O_NONBLOCK")):
            if not hasattr(os, name):
                self.enterContext(patch.object(os, name, 1 << (16 + i), create=True))
        self.pipe = self.enterContext(patch("os.pipe2", side_effect=[(3, 4), (5, 6)], create=True))
        self.close = self.enterContext(patch("os.close"))
        self.enterContext(patch("os.get_blocking", return_value=False, create=True))
        self.enterContext(patch("os.fstat", side_effect=lambda fd: SimpleNamespace(
            st_dev=13, st_ino=20 if fd < 5 else 21)))
        self.observe = self.enterContext(patch(
            "scripts.private_worker_cooperative_channels.observe_owned_pipe_end",
            side_effect=lambda fd, created_identity: PipeEnd(
                fd, *created_identity, Direction.READ if fd in (3, 5) else Direction.WRITE,
                True, True)))

    def test_parent_borrows_only_its_own_ends(self):
        with create_cooperative_channels() as channels:
            self.assertEqual(tuple(end.fd for end in channels.retain_parent_ends()), (3, 6))
            self.assertEqual(self.close.call_args_list, [call(4), call(5)])
            with self.assertRaises(DescriptorReviewError):
                channels.transfer_child_ends()
        self.assertEqual(self.close.call_args_list, [call(4), call(5), call(3), call(6)])
        self.assertEqual(self.pipe.call_args_list, [call(os.O_CLOEXEC | os.O_NONBLOCK)] * 2)

    def test_child_transfers_ownership_without_double_close(self):
        with create_cooperative_channels() as channels:
            self.assertEqual(tuple(end.fd for end in channels.transfer_child_ends()), (4, 5))
        self.assertEqual(self.close.call_args_list, [call(3), call(6)])

    def test_creation_or_metadata_failure_closes_every_acquired_descriptor(self):
        self.pipe.side_effect = [(3, 4), OSError()]
        with self.assertRaises(DescriptorReviewError), create_cooperative_channels():
            self.fail("unexpected channels")
        self.assertEqual(self.close.call_args_list, [call(3), call(4)])
        self.close.reset_mock()
        self.pipe.side_effect = [(3, 4), (5, 6)]
        self.observe.side_effect = [*(
            PipeEnd(fd, 13, 20, direction, True, True)
            for fd, direction in ((3, Direction.READ), (4, Direction.WRITE))
        ), DescriptorReviewError()]
        with self.assertRaises(DescriptorReviewError), create_cooperative_channels():
            self.fail("unexpected channels")
        self.assertEqual(self.close.call_args_list, [call(3), call(4), call(5), call(6)])

    def test_close_failure_does_not_retry_descriptor_number(self):
        self.close.side_effect = [OSError(), None, None, None]
        with self.assertRaises(DescriptorReviewError), create_cooperative_channels() as channels:
            channels.retain_parent_ends()
        self.assertEqual(self.close.call_args_list, [call(4), call(5), call(3), call(6)])
