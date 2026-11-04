"""Disposable synthetic blobs only; never installed model/service state."""
import os
from pathlib import Path
import tempfile
import unittest
from hashlib import sha256
from unittest.mock import patch

from pipeline.document_job_manifest import ManifestBlobDescriptor, MODEL_MEDIA
from pipeline.document_job_blob_measurement import measure_blob, BlobMeasurementError


@unittest.skipUnless(os.name == "posix", "POSIX directory-relative handles required")
class BlobMeasurementTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.data = b"synthetic weights only"
        self.digest = sha256(self.data).hexdigest()
        self.path = self.root / ("sha256-" + self.digest)
        self.path.write_bytes(self.data)
        self.desc = ManifestBlobDescriptor(MODEL_MEDIA, "sha256:" + self.digest, len(self.data))
        guard = patch("socket.socket", side_effect=AssertionError("no network"))
        guard.start(); self.addCleanup(guard.stop)

    def run_measure(self, **changes):
        args = dict(expected_uid=os.getuid(), max_bytes=1024, timeout_seconds=2)
        args.update(changes)
        return measure_blob(self.fd, self.desc, **args)

    def deny(self, **changes):
        with self.assertRaises(BlobMeasurementError) as error:
            self.run_measure(**changes)
        self.assertEqual(str(error.exception), "model blob measurement failed")

    def test_success_and_caller_handle_kept(self):
        self.assertEqual(self.run_measure(), self.digest)
        os.fstat(self.fd)
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_cleanup_failure_still_closes_both_handles(self):
        calls = []
        close = os.close
        def failed(fd):
            calls.append(fd)
            close(fd)
            if len(calls) == 1:
                raise OSError("sensitive OS detail")
        with patch("pipeline.document_job_blob_measurement.os.close", side_effect=failed):
            self.deny()
        self.assertEqual(len(calls), 2)
        os.fstat(self.fd)
        calls.clear()
        with patch("pipeline.document_job_blob_measurement.os.close", side_effect=failed), patch("pipeline.document_job_blob_measurement.os.read", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_measure()
        self.assertEqual(len(calls), 2)

    def test_path_replacement_is_detected(self):
        read = os.read
        changed = False
        def replace_path(fd, count):
            nonlocal changed
            data = read(fd, count)
            if not changed:
                changed = True
                self.path.rename(self.root / "old")
                self.path.write_bytes(self.data)
            return data
        with patch("pipeline.document_job_blob_measurement.os.read", side_effect=replace_path):
            self.deny()

    def test_fifo_does_not_block_open(self):
        self.path.unlink()
        os.mkfifo(self.path)
        self.deny()

    def test_clock_expiry_after_read_discards_hash(self):
        ticks = iter([0, 0, 0, 3])
        self.deny(_clock=ticks.__next__)

    def test_hash_size_and_budget_refusals(self):
        self.deny(max_bytes=len(self.data)-1)
        self.path.write_bytes(b"x" * len(self.data)); self.deny()
        self.path.write_bytes(b"x"); self.deny()
        self.deny(expected_uid=os.getuid()+1)

    def test_links_directory_and_writable_targets(self):
        self.path.unlink(); self.path.symlink_to("missing"); self.deny()
        self.path.unlink(); self.path.mkdir(); self.deny()
        self.path.rmdir(); self.path.write_bytes(self.data)
        os.link(self.path, self.root / "second"); self.deny()
        (self.root / "second").unlink()
        self.path.chmod(0o666); self.deny()
        self.path.chmod(0o600); self.root.chmod(0o777); self.deny()

    def test_clock_limits_and_invalid_inputs(self):
        for value in (0, -1, float("nan"), float("inf"), True, 121):
            self.deny(timeout_seconds=value)
        self.deny(max_bytes=True)
        self.deny(_clock=lambda: float("nan"))
        self.deny(_clock=iter([10, 9]).__next__)
        self.deny(_clock=iter([0, 3]).__next__)

    def test_changed_file_and_interrupt_cleanup(self):
        original = os.read
        def changed(fd, count):
            data = original(fd, count)
            self.path.write_bytes(self.data)
            return data
        with patch("pipeline.document_job_blob_measurement.os.read", side_effect=changed):
            self.deny()
        closed = []
        real_close = os.close
        def closing(fd):
            closed.append(fd); real_close(fd)
        with patch("pipeline.document_job_blob_measurement.os.read", side_effect=KeyboardInterrupt), patch("pipeline.document_job_blob_measurement.os.close", side_effect=closing):
            with self.assertRaises(KeyboardInterrupt): self.run_measure()
        self.assertEqual(len(closed), 2)
        os.fstat(self.fd)
