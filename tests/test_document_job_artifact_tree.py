"""Anchored-tree/race fixtures own all files; no real models/services."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch

from pipeline.document_job_artifact_tree import measure_model_tree, ArtifactTreeError
from pipeline.document_job_manifest import ROOT_MEDIA, CONFIG_MEDIA, MODEL_MEDIA
from pipeline.document_job_blob_measurement import measure_blob_set


@unittest.skipUnless(os.name == "posix", "POSIX handles required")
class ArtifactTreeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.anchor = Path(temp.name)
        self.root = self.anchor / "models"
        self.blobs = self.root / "blobs"
        self.directory = self.root / "manifests/registry.ollama.ai/library/test-model"
        self.blobs.mkdir(parents=True); self.directory.mkdir(parents=True)
        entries = []
        for media, data in ((CONFIG_MEDIA, b"synthetic config"), (MODEL_MEDIA, b"synthetic model")):
            digest = sha256(data).hexdigest()
            (self.blobs / ("sha256-"+digest)).write_bytes(data)
            entries.append(dict(mediaType=media, digest="sha256:"+digest, size=len(data)))
        self.raw = json.dumps(dict(schemaVersion=2, mediaType=ROOT_MEDIA,
                                   config=entries[0], layers=[entries[1]])).encode()
        self.path = self.directory / "v1"; self.path.write_bytes(self.raw)
        self.fd = os.open(self.anchor, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        guard = patch("socket.socket", side_effect=AssertionError("no network"))
        guard.start(); self.addCleanup(guard.stop)

    def measure(self, parts=("models",), model="test-model:v1", **changes):
        args = dict(expected_uid=os.getuid(), max_bytes=1000, timeout_seconds=2)
        args.update(changes)
        return measure_model_tree(self.fd, parts, model, **args)

    def deny(self, *args, **kw):
        with self.assertRaises(ArtifactTreeError) as error: self.measure(*args, **kw)
        self.assertEqual(str(error.exception), "model artifact tree measurement failed")

    def test_exact_layout_and_caller_handle_survives(self):
        parsed, hashes = self.measure()
        self.assertEqual(parsed.raw_bytes_sha256, sha256(self.raw).hexdigest())
        self.assertEqual(len(hashes), 2)
        os.fstat(self.fd)

    def test_invalid_selection_denies_before_io(self):
        with patch("pipeline.document_job_artifact_tree.os.dup", side_effect=AssertionError("no I/O")):
            for parts in ((), ("..",), ("/models",), ("models/other",), ["models"], ("x",)*9): self.deny(parts)
            for name in ("test-model", "../test:v1", "host/name:v1", "test:v1:2", "Test:v1", "test:cloud", "test:é"):
                self.deny(model=name)

    def test_symlink_at_each_tree_level_denies(self):
        paths = [self.root, self.blobs, *reversed(list(self.directory.parents)[:3]), self.directory]
        # Each replacement is restored within the disposable fixture.
        for path in paths:
            old = path.with_name(path.name+"-saved")
            path.rename(old); path.symlink_to(old, target_is_directory=True)
            try: self.deny()
            finally: path.unlink(); old.rename(path)

    def test_permissions_owner_missing_and_budget_denials(self):
        self.deny(expected_uid=os.getuid()+1)
        self.deny(max_bytes=1)
        self.deny(timeout_seconds=0)
        self.deny(_clock=lambda: float("nan"))
        self.blobs.chmod(0o777); self.deny(); self.blobs.chmod(0o755)
        self.path.unlink(); self.deny()

    def test_parent_replacement_after_measurement_denies(self):
        def replaced(*args, **kw):
            result = measure_blob_set(*args, **kw)
            self.root.rename(self.anchor / "old-models")
            self.root.mkdir()
            return result
        with patch("pipeline.document_job_artifact_tree.measure_blob_set", side_effect=replaced): self.deny()

    def test_replacement_between_stat_and_open_cannot_follow_link(self):
        opening = os.open
        replaced = False
        def race(name, flags, *args, **kw):
            nonlocal replaced
            if not replaced and name == "models":
                replaced = True
                old = self.anchor / "original-models"
                self.root.rename(old); self.root.symlink_to(old, target_is_directory=True)
            return opening(name, flags, *args, **kw)
        with patch("pipeline.document_job_artifact_tree.os.open", side_effect=race), patch("pipeline.document_job_artifact_tree.os.read", side_effect=AssertionError("no payload read")):
            self.deny()
        self.assertTrue(replaced)

    def test_cross_device_child_is_rejected_before_open(self):
        original = os.stat
        def cross_device(name, *args, **kw):
            info = original(name, *args, **kw)
            if name == "models" and "dir_fd" in kw:
                return SimpleNamespace(st_mode=info.st_mode, st_uid=info.st_uid, st_dev=info.st_dev+1)
            return info
        with patch("pipeline.document_job_artifact_tree.os.stat", side_effect=cross_device): self.deny()

    def test_identical_manifest_replacement_denies(self):
        def replaced(*args, **kw):
            result = measure_blob_set(*args, **kw)
            self.path.rename(self.directory / "old")
            self.path.write_bytes(self.raw)
            return result
        with patch("pipeline.document_job_artifact_tree.measure_blob_set", side_effect=replaced): self.deny()

    def test_interrupt_and_failed_close_attempt_all_cleanup(self):
        calls = []; close = os.close
        def closing(fd):
            calls.append(fd); close(fd)
            if len(calls)==1: raise OSError("sensitive cleanup")
        with patch("pipeline.document_job_artifact_tree.os.close", side_effect=closing): self.deny()
        self.assertGreaterEqual(len(calls), 7)
        calls.clear()
        with patch("pipeline.document_job_artifact_tree.measure_blob_set", side_effect=KeyboardInterrupt), patch("pipeline.document_job_artifact_tree.os.close", side_effect=lambda fd: (calls.append(fd), close(fd))[-1]):
            with self.assertRaises(KeyboardInterrupt): self.measure()
        self.assertGreaterEqual(len(calls), 7)
        os.fstat(self.fd)
