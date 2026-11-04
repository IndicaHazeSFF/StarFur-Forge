"""Synthetic manifest acquisition; no installed models or services."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from hashlib import sha256

from tests.test_document_job_manifest import encode, fixture
from pipeline.document_job_manifest_file import read_manifest_file, ManifestFileError


@unittest.skipUnless(os.name == "posix", "POSIX handles required")
class ManifestFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.path = self.root / "test-tag"
        self.raw = encode(fixture())
        self.path.write_bytes(self.raw)
        guard = patch("socket.socket", side_effect=AssertionError("no network"))
        guard.start(); self.addCleanup(guard.stop)

    def read(self, name="test-tag", **changes):
        args = dict(expected_uid=os.getuid(), timeout_seconds=2)
        args.update(changes)
        return read_manifest_file(self.fd, name, **args)

    def deny(self, name="test-tag", **changes):
        with self.assertRaises(ManifestFileError) as error: self.read(name, **changes)
        self.assertEqual(str(error.exception), "model manifest acquisition failed")

    def test_read_hash_and_no_payload_output(self):
        result = self.read()
        self.assertEqual(result.raw_bytes_sha256, sha256(self.raw).hexdigest())
        self.assertFalse(hasattr(result, "raw"))
        os.fstat(self.fd)

    def test_invalid_names_are_rejected_before_open(self):
        with patch("pipeline.document_job_manifest_file.os.dup", side_effect=AssertionError("no open")):
            for name in ("../test-tag", "..", ".", "/test-tag", "a/b", "a\\b", "", "é", "x"*129): self.deny(name)

    def test_malformed_oversize_and_ownership_deny(self):
        self.deny(expected_uid=os.getuid()+1)
        for raw in (b"{}", b"x"*65537, b"\xff\xff", self.raw+b"{}"):
            self.path.write_bytes(raw); self.deny()

    def test_links_fifo_and_permissions_deny(self):
        self.path.unlink(); self.path.symlink_to("missing"); self.deny()
        self.path.unlink(); os.mkfifo(self.path); self.deny()
        self.path.unlink(); self.path.write_bytes(self.raw)
        os.link(self.path, self.root / "alias"); self.deny()
        (self.root / "alias").unlink(); self.path.chmod(0o666); self.deny()

    def test_changed_path_and_expired_parse_deny(self):
        read = os.read
        replaced = False
        def changed(fd, count):
            nonlocal replaced
            data = read(fd, count)
            if not replaced:
                replaced = True
                self.path.rename(self.root / "old"); self.path.write_bytes(self.raw)
            return data
        with patch("pipeline.document_job_manifest_file.os.read", side_effect=changed): self.deny()
        self.deny(_clock=lambda: float("nan"))
        clock = [0]
        from pipeline.document_job_manifest import decode_model_manifest
        def slow(raw):
            result = decode_model_manifest(raw); clock[0] = 3; return result
        with patch("pipeline.document_job_manifest_file.decode_model_manifest", side_effect=slow):
            self.deny(_clock=lambda: clock[0])

    def test_interruption_and_close_failure_cleanup(self):
        close = os.close; calls = []
        def closing(fd):
            calls.append(fd); close(fd)
            if len(calls)==1: raise OSError("sensitive")
        with patch("pipeline.document_job_manifest_file.os.close", side_effect=closing): self.deny()
        self.assertEqual(len(calls), 2)
        calls.clear()
        with patch("pipeline.document_job_manifest_file.os.close", side_effect=closing), patch("pipeline.document_job_manifest_file.os.read", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.read()
        self.assertEqual(len(calls), 2)
        os.fstat(self.fd)
