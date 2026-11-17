"""Supplied synthetic bytes only; no installed artifact or loader execution."""
from dataclasses import FrozenInstanceError
from hashlib import sha256
import struct
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import WorkerElfError, inspect_worker_elf
from pipeline.document_job_worker_elf_search import review_worker_elf_search
from pipeline.document_job_worker_elf_soname import WorkerElfSonameReview, review_worker_elf_soname
from tests.test_document_job_worker_elf import fixture
from tests.test_document_job_worker_elf_search import search_fixture


class WorkerElfSonameTests(unittest.TestCase):
    def test_exact_declared_label_bound_to_same_bytes(self):
        for label in ("libfixture.so", "libggml-base.so.0.15.3", "ld-linux-x86-64.so.2"):
            raw = search_fixture(((14, label),), needed=False)
            value = review_worker_elf_soname(raw)
            self.assertEqual((value.raw_sha256, value.soname), (sha256(raw).hexdigest(), label))

    def test_absence_never_guesses_a_filename_or_needed_label(self):
        for raw in (fixture(), fixture(names=()), search_fixture(needed=False)):
            self.assertIsNone(review_worker_elf_soname(raw).soname)

    def test_mixed_search_description_never_changes_strict_denial(self):
        raw = search_fixture(((14, "libfixture.so"),
                              (29, "$ORIGIN:/build/llama-server-cpu/bin:")))
        self.assertEqual(review_worker_elf_soname(raw).soname, "libfixture.so")
        self.assertEqual(review_worker_elf_search(raw).category, "mixed_or_unsupported")
        with self.assertRaises(WorkerElfError):
            inspect_worker_elf(raw)

    def test_duplicate_soname_denies_even_identical_or_zero_first(self):
        for names in (("liba.so", "liba.so"), ("liba.so", "libb.so"), ("", "liba.so")):
            with self.assertRaisesRegex(WorkerElfError, "^worker ELF SONAME review is unavailable$"):
                review_worker_elf_soname(search_fixture(tuple((14, n) for n in names)))

    def test_invalid_label_and_no_path_normalization(self):
        for name in ("", "PRIVATE", "../liba.so", "/liba.so", "liba.so/other",
                     "liba.so\nPRIVATE", "liba.so ", "$ORIGIN/liba.so", "lib" + "a" * 129 + ".so"):
            with self.assertRaises(WorkerElfError):
                review_worker_elf_soname(search_fixture(((14, name),), needed=False))

    def test_unmapped_out_of_range_or_unterminated_soname_denies(self):
        raw = bytearray(search_fixture(((14, "liba.so"),), needed=False))
        for offset, number in ((392, 0x900000), (424, 999999)):
            changed = bytearray(raw); struct.pack_into("<Q", changed, offset, number)
            with self.assertRaises(WorkerElfError):
                review_worker_elf_soname(bytes(changed))
        raw[768 + len(b"\0liba.so")] = 65
        with self.assertRaises(WorkerElfError):
            review_worker_elf_soname(bytes(raw))

    def test_non_ascii_and_missing_string_table_deny(self):
        raw = bytearray(search_fixture(((14, "liba.so"),), needed=False))
        raw[769] = 255
        with self.assertRaises(WorkerElfError):
            review_worker_elf_soname(bytes(raw))
        raw = bytearray(search_fixture(((14, "liba.so"),), needed=False))
        struct.pack_into("<q", raw, 384, 99)
        with self.assertRaises(WorkerElfError):
            review_worker_elf_soname(bytes(raw))

    def test_static_image_and_malformed_input(self):
        raw = bytearray(fixture()); struct.pack_into("<H", raw, 56, 1)
        self.assertIsNone(review_worker_elf_soname(bytes(raw)).soname)
        for raw in (b"", b"PRIVATE", bytearray(fixture()), None):
            with self.assertRaisesRegex(WorkerElfError, "^worker ELF SONAME review is unavailable$"):
                review_worker_elf_soname(raw)

    def test_inert_immutable_redacted_and_not_eligibility(self):
        raw = search_fixture(((14, "libfixture.so"),))
        with patch("builtins.open", side_effect=AssertionError), \
             patch("subprocess.Popen", side_effect=AssertionError), \
             patch("socket.socket", side_effect=AssertionError):
            value = review_worker_elf_soname(raw)
        self.assertNotIn("libfixture", repr(value))
        self.assertFalse(hasattr(value, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError):
            value.soname = None
        for digest, name in (("PRIVATE", "liba.so"), ("a" * 64, True), ("a" * 64, "../liba.so")):
            with self.assertRaises(WorkerElfError):
                WorkerElfSonameReview(digest, name)
