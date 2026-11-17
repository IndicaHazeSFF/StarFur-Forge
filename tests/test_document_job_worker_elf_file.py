"""Test-owned ELF fixtures only; no installed executable or provider access."""
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf_file import (
    WorkerElfFileError, WorkerElfFileObservation, inspect_worker_elf_file,
)
from tests.test_document_job_worker_elf import fixture


@unittest.skipUnless(os.name == "posix", "POSIX directory-relative handles required")
class WorkerElfFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.root.chmod(0o700)
        self.path = self.root / "program.elf"
        self.raw = fixture()
        self.path.write_bytes(self.raw)
        self.path.chmod(0o500)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)

    def inspect(self, **changes):
        kwargs = dict(expected_uid=os.getuid(), max_bytes=4096, timeout_seconds=2)
        kwargs.update(changes)
        return inspect_worker_elf_file(self.fd, "program.elf", **kwargs)

    def deny(self, **changes):
        with self.assertRaisesRegex(WorkerElfFileError, "^worker ELF acquisition is unavailable$"):
            self.inspect(**changes)

    def test_metadata_only_immutable_and_caller_handle_kept(self):
        with patch("socket.socket", side_effect=AssertionError("no network")), \
             patch("subprocess.Popen", side_effect=AssertionError("no executable")):
            value = self.inspect()
        self.assertEqual(value.dependencies.needed, ("libc.so.6", "libstdc++.so.6"))
        self.assertEqual(value.identity[5], len(self.raw))
        self.assertNotIn("libc", repr(value))
        self.assertNotIn("program", repr(value))
        os.fstat(self.fd)
        with self.assertRaises(FrozenInstanceError):
            value.identity = ()
        self.assertEqual(self.path.read_bytes(), self.raw)

    def test_paths_and_wrong_types_refused_before_open(self):
        for name in ("../program.elf", "/tmp/program.elf", ".", "..", "a/b", "a:b", "", True):
            with patch("pipeline.document_job_worker_elf_file.os.dup") as acquire:
                with self.assertRaises(WorkerElfFileError):
                    inspect_worker_elf_file(self.fd, name, expected_uid=os.getuid(),
                                            max_bytes=4096, timeout_seconds=2)
                acquire.assert_not_called()

    def test_exact_nonblocking_no_follow_acquisition(self):
        original = os.open
        with patch("pipeline.document_job_worker_elf_file.os.open", wraps=original) as acquire:
            self.inspect()
        _, flags = acquire.call_args.args
        self.assertTrue(flags & os.O_NOFOLLOW)
        self.assertTrue(flags & os.O_NONBLOCK)
        self.assertIn("dir_fd", acquire.call_args.kwargs)

    def test_symlink_and_hardlink_denied(self):
        self.path.rename(self.root / "real")
        self.path.symlink_to("real")
        self.deny()
        self.path.unlink()
        os.link(self.root / "real", self.path)
        self.deny()

    def test_fifo_and_directory_deny_before_open(self):
        self.path.unlink()
        os.mkfifo(self.path)
        self.deny()
        self.path.unlink()
        self.path.mkdir()
        self.deny()

    def test_owner_and_unsafe_modes_refused(self):
        self.deny(expected_uid=os.getuid() + 1)
        for mode in (0o666, 0o4500, 0o2500, 0o1500):
            self.path.chmod(mode)
            self.deny()
        self.path.chmod(0o500)
        self.root.chmod(0o777)
        self.deny()

    def test_byte_time_and_type_limits(self):
        for value in (True, 0, 63, 64 * 1024 * 1024 + 1):
            self.deny(max_bytes=value)
        self.deny(max_bytes=len(self.raw) - 1)
        for value in (True, 0, -1, float("nan"), float("inf"), 121):
            self.deny(timeout_seconds=value)
        self.deny(_clock=lambda: float("nan"))
        self.deny(_clock=iter([10, 9]).__next__)
        self.deny(_clock=iter([0, 3]).__next__)

    def test_source_replacement_is_detected(self):
        original = os.read
        changed = False
        def read(fd, count):
            nonlocal changed
            part = original(fd, count)
            if not changed:
                changed = True
                self.path.rename(self.root / "old")
                self.path.write_bytes(self.raw)
                self.path.chmod(0o500)
            return part
        with patch("pipeline.document_job_worker_elf_file.os.read", side_effect=read):
            self.deny()

    def test_source_size_change_is_detected(self):
        original = os.read
        changed = False
        def read(fd, count):
            nonlocal changed
            part = original(fd, count)
            if not changed:
                changed = True
                self.path.chmod(0o600)
                self.path.write_bytes(b"x")
            return part
        with patch("pipeline.document_job_worker_elf_file.os.read", side_effect=read):
            self.deny()

    def test_deadline_after_parser_discards_observation(self):
        from pipeline.document_job_worker_elf import inspect_worker_elf
        ticks = [0]
        def parse(raw):
            value = inspect_worker_elf(raw)
            ticks[0] = 3
            return value
        with patch("pipeline.document_job_worker_elf_file.inspect_worker_elf", side_effect=parse):
            self.deny(_clock=lambda: ticks[0])

    def test_parse_failure_does_not_return_raw_bytes_or_path(self):
        self.path.chmod(0o600)
        self.path.write_bytes(b"PRIVATE" * 20)
        self.deny()

    def test_interrupt_closes_owned_handles_and_preserves_caller(self):
        closed, original = [], os.close
        def close(fd):
            closed.append(fd)
            original(fd)
        with patch("pipeline.document_job_worker_elf_file.os.read", side_effect=KeyboardInterrupt), \
             patch("pipeline.document_job_worker_elf_file.os.close", side_effect=close):
            with self.assertRaises(KeyboardInterrupt):
                self.inspect()
        self.assertEqual(len(closed), 2)
        os.fstat(self.fd)

    def test_close_failure_still_attempts_both_and_refuses_success(self):
        closed, original = [], os.close
        def close(fd):
            closed.append(fd)
            original(fd)
            if len(closed) == 1:
                raise OSError("PRIVATE")
        with patch("pipeline.document_job_worker_elf_file.os.close", side_effect=close):
            self.deny()
        self.assertEqual(len(closed), 2)
        os.fstat(self.fd)

    def test_direct_observation_constructor_revalidates_identity(self):
        value = self.inspect()
        for identity in ((), value.identity[:-1], (True,) + value.identity[1:]):
            with self.assertRaises(WorkerElfFileError):
                WorkerElfFileObservation(value.dependencies, identity)
