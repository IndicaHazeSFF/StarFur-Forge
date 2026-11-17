"""Exact same-acquisition identity over test-owned POSIX ELF fixtures only."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import _parse_metadata
from pipeline.document_job_worker_elf_file import (
    WorkerElfFileError, WorkerElfIdentityObservation, inspect_worker_elf_file,
    review_worker_elf_file, review_worker_elf_identity_file,
)
from tests.test_document_job_worker_elf_search import search_fixture


@unittest.skipUnless(os.name == "posix", "POSIX directory handles required")
class WorkerElfIdentityFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.root.chmod(0o700)
        self.path = self.root / "unrelated-name"
        self.raw = search_fixture(((14, "libfixture.so"), (29, "$ORIGIN")))
        self.path.write_bytes(self.raw); self.path.chmod(0o500)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)

    def review(self, **changes):
        args = dict(expected_uid=os.getuid(), max_bytes=4096, timeout_seconds=2)
        args.update(changes)
        return review_worker_elf_identity_file(self.fd, self.path.name, **args)

    def put(self, raw):
        self.path.chmod(0o600); self.path.write_bytes(raw); self.path.chmod(0o500)

    def test_one_parse_same_byte_hash_and_redacted_immutable_observation(self):
        with patch("pipeline.document_job_worker_elf_file._parse_metadata", wraps=_parse_metadata) as parsed, \
             patch("subprocess.Popen", side_effect=AssertionError), \
             patch("socket.socket", side_effect=AssertionError):
            value = self.review()
        self.assertEqual(parsed.call_count, 1)
        self.assertEqual(value.soname.soname, "libfixture.so")
        self.assertEqual(value.search.category, "exact_origin")
        self.assertEqual(value.file.dependencies.raw_sha256, sha256(self.raw).hexdigest())
        self.assertEqual(value.soname.raw_sha256, value.search.raw_sha256)
        self.assertEqual(value.search.raw_sha256, value.file.dependencies.raw_sha256)
        self.assertNotIn("libfixture", repr(value))
        self.assertFalse(hasattr(value, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError):
            value.soname = None
        os.fstat(self.fd)

    def test_absence_is_explicit_not_inferred_from_basename(self):
        self.put(search_fixture())
        self.assertIsNone(self.review().soname.soname)

    def test_duplicate_soname_new_review_refuses_without_changing_old_review(self):
        self.put(search_fixture(((14, "liba.so"), (14, "liba.so"))))
        with self.assertRaisesRegex(WorkerElfFileError, "^worker ELF acquisition is unavailable$"):
            self.review()
        # Legacy descriptive review never claimed to assess SONAME.
        value = review_worker_elf_file(self.fd, self.path.name, expected_uid=os.getuid(),
                                      max_bytes=4096, timeout_seconds=2)
        self.assertEqual(value.search.category, "no_search_tag")

    def test_strict_search_refusal_unchanged_for_mixed_metadata(self):
        self.put(search_fixture(((14, "libfixture.so"), (29, "$ORIGIN:/build/llama-server-cpu/bin:"))))
        self.assertEqual(self.review().search.category, "mixed_or_unsupported")
        with self.assertRaises(WorkerElfFileError):
            inspect_worker_elf_file(self.fd, self.path.name, expected_uid=os.getuid(),
                                    max_bytes=4096, timeout_seconds=2)

    def test_symlink_hardlink_and_writable_file_refused(self):
        self.path.rename(self.root / "original"); self.path.symlink_to("original")
        with self.assertRaises(WorkerElfFileError): self.review()
        self.path.unlink(); os.link(self.root / "original", self.path)
        with self.assertRaises(WorkerElfFileError): self.review()
        self.path.unlink(); (self.root / "original").rename(self.path)
        self.path.chmod(0o502)
        with self.assertRaises(WorkerElfFileError): self.review()

    def test_final_identity_replacement_after_parse_refuses(self):
        def parse(raw, **kw):
            value = _parse_metadata(raw, **kw)
            self.path.rename(self.root / "old")
            self.path.write_bytes(self.raw); self.path.chmod(0o500)
            return value
        with patch("pipeline.document_job_worker_elf_file._parse_metadata", side_effect=parse):
            with self.assertRaises(WorkerElfFileError): self.review()

    def test_final_deadline_includes_identity_parse(self):
        tick = [0]
        def parse(raw, **kw):
            value = _parse_metadata(raw, **kw); tick[0] = 3; return value
        with patch("pipeline.document_job_worker_elf_file._parse_metadata", side_effect=parse):
            with self.assertRaises(WorkerElfFileError): self.review(_clock=lambda: tick[0])

    def test_parse_interrupt_closes_owned_handles_not_caller(self):
        original, closed = os.close, []
        def close(fd): closed.append(fd); original(fd)
        with patch("pipeline.document_job_worker_elf_file._parse_metadata", side_effect=KeyboardInterrupt), \
             patch("pipeline.document_job_worker_elf_file.os.close", side_effect=close):
            with self.assertRaises(KeyboardInterrupt): self.review()
        self.assertEqual(len(closed), 2); os.fstat(self.fd)

    def test_constructed_mismatched_observations_refuse(self):
        value = self.review()
        for named in (None, replace(value.soname, raw_sha256="f" * 64)):
            with self.assertRaises(WorkerElfFileError):
                WorkerElfIdentityObservation(value.file, value.search, named)
