"""Review-only exact-file acquisition over disposable synthetic ELF bytes."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf_file import (
    review_worker_elf_file, inspect_worker_elf_file, WorkerElfFileError,
    WorkerElfReviewObservation,
)
from tests.test_document_job_worker_elf_search import search_fixture


@unittest.skipUnless(os.name == "posix", "POSIX directory handles required")
class WorkerElfReviewFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.root.chmod(0o700)
        self.path = self.root / "file.elf"
        self.raw = search_fixture()
        self.path.write_bytes(self.raw); self.path.chmod(0o500)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)

    def review(self, **changes):
        args = dict(expected_uid=os.getuid(), max_bytes=4096, timeout_seconds=2)
        args.update(changes)
        return review_worker_elf_file(self.fd, "file.elf", **args)

    def test_same_acquired_bytes_bind_file_and_search_without_authority(self):
        with patch("subprocess.Popen", side_effect=AssertionError), patch("socket.socket", side_effect=AssertionError):
            value = self.review()
        self.assertEqual(value.search.category, "exact_origin")
        self.assertEqual(value.file.dependencies.raw_sha256, sha256(self.raw).hexdigest())
        self.assertEqual(value.file.dependencies.raw_sha256, value.search.raw_sha256)
        self.assertNotIn("ORIGIN", repr(value))
        self.assertFalse(hasattr(value, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError):
            value.search = None
        os.fstat(self.fd)

    def test_both_installed_search_forms_still_refused_by_strict_c2(self):
        for text, category in (("$ORIGIN", "exact_origin"),
                               ("$ORIGIN:/build/llama-server-cpu/bin:", "mixed_or_unsupported")):
            self.path.chmod(0o600); self.path.write_bytes(search_fixture(((29, text),)))
            self.path.chmod(0o500)
            self.assertEqual(self.review().search.category, category)
            with self.assertRaises(WorkerElfFileError):
                inspect_worker_elf_file(self.fd, "file.elf", expected_uid=os.getuid(), max_bytes=4096, timeout_seconds=2)

    def test_symlink_is_not_followed(self):
        self.path.rename(self.root / "real")
        self.path.symlink_to("real")
        with self.assertRaises(WorkerElfFileError):
            self.review()

    def test_parse_time_replacement_is_caught_by_final_identity_check(self):
        from pipeline.document_job_worker_elf_search import _make_review
        def make(metadata, search):
            result = _make_review(metadata, search)
            self.path.rename(self.root / "old")
            self.path.write_bytes(self.raw); self.path.chmod(0o500)
            return result
        with patch("pipeline.document_job_worker_elf_file._make_review", side_effect=make):
            with self.assertRaises(WorkerElfFileError):
                self.review()

    def test_final_review_deadline_is_enforced(self):
        from pipeline.document_job_worker_elf_search import _make_review
        ticks = [0]
        def make(metadata, search):
            result = _make_review(metadata, search); ticks[0] = 3
            return result
        with patch("pipeline.document_job_worker_elf_file._make_review", side_effect=make):
            with self.assertRaises(WorkerElfFileError):
                self.review(_clock=lambda: ticks[0])

    def test_interrupt_closes_owned_handles_preserving_caller(self):
        original, closed = os.close, []
        def close(fd):
            closed.append(fd); original(fd)
        with patch("pipeline.document_job_worker_elf_file.os.read", side_effect=KeyboardInterrupt), \
             patch("pipeline.document_job_worker_elf_file.os.close", side_effect=close):
            with self.assertRaises(KeyboardInterrupt):
                self.review()
        self.assertEqual(len(closed), 2); os.fstat(self.fd)

    def test_constructed_mismatched_hashes_refuse(self):
        value = self.review()
        with self.assertRaises(WorkerElfFileError):
            WorkerElfReviewObservation(value.file, replace(value.search, raw_sha256="f" * 64))

    def test_search_is_parsed_without_needed_and_malformed_bytes_redacted(self):
        self.path.chmod(0o600); self.path.write_bytes(search_fixture(needed=False)); self.path.chmod(0o500)
        self.assertEqual(self.review().file.dependencies.needed, ())
        self.path.chmod(0o600); self.path.write_bytes(b"PRIVATE" * 20)
        with self.assertRaisesRegex(WorkerElfFileError, "^worker ELF acquisition is unavailable$"):
            self.review()
