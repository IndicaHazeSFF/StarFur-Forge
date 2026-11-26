"""Mocked metadata only: no pipe allocation, process launch, or native probe."""

import os
import stat
import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

from scripts.private_worker_cooperative_fd_read import observe_owned_pipe_end
from scripts.private_worker_cooperative_fds import DescriptorReviewError, Direction, PipeEnd


class OwnedPipeReadTests(unittest.TestCase):
    def observe(self, rows, flags, fd=4, identity=(3, 90), platform="linux"):
        with (patch("sys.platform", platform),
              patch.dict("sys.modules", {"fcntl": SimpleNamespace(
                  F_GETFL=30, F_GETFD=31, FD_CLOEXEC=1)}),
              patch("os.fstat", side_effect=rows) as metadata,
              patch("os.read", side_effect=AssertionError("must not read pipe bytes"))):
            fcntl = __import__("fcntl")
            with patch.object(fcntl, "fcntl", side_effect=flags, create=True) as get:
                row = observe_owned_pipe_end(fd, created_identity=identity)
            self.assertEqual(get.call_args_list, [
                call(fd, 30), call(fd, 31), call(fd, 30), call(fd, 31),
            ])
            self.assertEqual(metadata.call_count, 2)
            return row

    def setUp(self):
        self.pipe = SimpleNamespace(st_mode=stat.S_IFIFO, st_dev=3, st_ino=90)

    def test_only_observes_the_expected_handle_and_flags(self):
        self.assertEqual(self.observe([self.pipe] * 2, [os.O_WRONLY, 0] * 2),
                         PipeEnd(4, 3, 90, Direction.WRITE, False, True))
        self.assertEqual(self.observe([self.pipe] * 2, [os.O_RDONLY | os.O_NONBLOCK, 1] * 2),
                         PipeEnd(4, 3, 90, Direction.READ, True, True))

    def test_nonpipe_or_identity_drift_refuses(self):
        for row in (SimpleNamespace(st_mode=stat.S_IFREG, st_dev=3, st_ino=90),
                    SimpleNamespace(st_mode=stat.S_IFIFO, st_dev=3, st_ino=91)):
            with self.assertRaises(DescriptorReviewError):
                self.observe([self.pipe, row], [os.O_WRONLY, 0])

    def test_invalid_flags_drift_and_io_error_refuse(self):
        for flags in ([os.O_RDWR, 0], [os.O_WRONLY | os.O_APPEND, 0],
                      [os.O_WRONLY, 2], [os.O_WRONLY, 0, os.O_WRONLY, 1],
                      [OSError("raw detail")]):
            with self.subTest(flags=flags), self.assertRaisesRegex(
                    DescriptorReviewError, "^owned cooperative pipe inspection refused$"):
                self.observe([self.pipe] * 2, flags)

    def test_invalid_inputs_and_wrong_platform_refuse_without_metadata(self):
        for kwargs in ({"fd": True}, {"identity": (True, 90)}, {"identity": (3, 0)},
                       {"platform": "win32"}):
            with self.assertRaises(DescriptorReviewError):
                self.observe([], [], **kwargs)
