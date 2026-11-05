"""Synthetic exact config-file acquisition; never installed artifacts."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from hashlib import sha256
from unittest.mock import patch

from tests.test_document_job_config import fixture
from pipeline.document_job_manifest import ParsedModelManifest, ManifestBlobDescriptor, CONFIG_MEDIA, MODEL_MEDIA
from pipeline.document_job_config_file import read_model_config, ConfigFileError


MODEL_BYTES = b"synthetic model weights"


def config_fixture(extra=None):
    model = ManifestBlobDescriptor(MODEL_MEDIA, "sha256:"+sha256(MODEL_BYTES).hexdigest(), len(MODEL_BYTES))
    value = fixture(); value["rootfs"]["diff_ids"] = [model.digest]
    value.update(extra or {})
    raw = json.dumps(value).encode()
    config = ManifestBlobDescriptor(CONFIG_MEDIA, "sha256:"+sha256(raw).hexdigest(), len(raw))
    return raw, ParsedModelManifest("a"*64, config, (model,), len(raw)+len(MODEL_BYTES))


@unittest.skipUnless(os.name == "posix", "POSIX handles required")
class ConfigFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw, self.manifest = config_fixture()
        self.path = self.root / self.manifest.config.digest.replace(":", "-")
        self.path.write_bytes(self.raw)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        guard = patch("socket.socket", side_effect=AssertionError("no network"))
        guard.start(); self.addCleanup(guard.stop)

    def read(self, **changes):
        args = dict(expected_uid=os.getuid(), timeout_seconds=2); args.update(changes)
        return read_model_config(self.fd, self.manifest, **args)

    def deny(self, **changes):
        with self.assertRaises(ConfigFileError) as error: self.read(**changes)
        self.assertEqual(str(error.exception), "model config acquisition failed")

    def test_exact_bytes_to_redacted_metadata(self):
        value = self.read(); self.assertEqual(value.raw_bytes_sha256, sha256(self.raw).hexdigest())
        self.assertNotIn("qwen3", repr(value)); self.assertFalse(hasattr(value, "raw")); os.fstat(self.fd)

    def test_owner_permissions_size_and_hash_denials(self):
        self.deny(expected_uid=os.getuid()+1)
        self.path.chmod(0o666); self.deny(); self.path.chmod(0o600)
        self.path.write_bytes(b"x"*len(self.raw)); self.deny()
        self.path.write_bytes(b"x"); self.deny()

    def test_symlink_hardlink_fifo_refusals(self):
        self.path.unlink(); self.path.symlink_to("missing"); self.deny()
        self.path.unlink(); os.mkfifo(self.path); self.deny()
        self.path.unlink(); self.path.write_bytes(self.raw)
        os.link(self.path, self.root / "alias"); self.deny()

    def test_replacement_during_read_denies(self):
        read = os.read; changed = False
        def replaced(fd, count):
            nonlocal changed
            data = read(fd, count)
            if not changed:
                changed = True
                self.path.rename(self.root / "old"); self.path.write_bytes(self.raw)
            return data
        with patch("pipeline.document_job_config_file.os.read", side_effect=replaced): self.deny()

    def test_expiry_after_decode_and_bad_clock_denials(self):
        from pipeline.document_job_config import decode_model_config
        clock = [0]
        def slow(*args):
            value = decode_model_config(*args); clock[0] = 3; return value
        with patch("pipeline.document_job_config_file.decode_model_config", side_effect=slow): self.deny(_clock=lambda:clock[0])
        self.deny(_clock=lambda:float("nan")); self.deny(timeout_seconds=True)

    def test_interrupt_and_close_failure_cleanup(self):
        close = os.close; calls = []
        def closing(fd):
            calls.append(fd); close(fd)
            if len(calls)==1: raise OSError("sensitive")
        with patch("pipeline.document_job_config_file.os.close", side_effect=closing): self.deny()
        self.assertEqual(len(calls), 2); calls.clear()
        with patch("pipeline.document_job_config_file.os.read", side_effect=KeyboardInterrupt), patch("pipeline.document_job_config_file.os.close", side_effect=closing):
            with self.assertRaises(KeyboardInterrupt): self.read()
        self.assertEqual(len(calls), 2); os.fstat(self.fd)
