"""Synthetic review fixtures; no loader, installed artifact or provider."""
from dataclasses import FrozenInstanceError
from hashlib import sha256
import struct
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import inspect_worker_elf, WorkerElfError
from pipeline.document_job_worker_elf_search import review_worker_elf_search
from tests.test_document_job_worker_elf import fixture


def search_fixture(entries=((29, "$ORIGIN"),), *, needed=True):
    raw = bytearray(fixture(names=("libc.so.6",) if needed else ()))
    strings = b"\0libc.so.6\0" if needed else b"\0"
    refs = []
    for tag, value in entries:
        refs.append((tag, len(strings)))
        strings += value.encode("ascii") + b"\0"
    rows = [(5, 0x400300), (10, len(strings))]
    if needed:
        rows.append((1, 1))
    rows += refs + [(0, 0)]
    raw[384:768] = b"\0" * 384
    for i, row in enumerate(rows):
        struct.pack_into("<qQ", raw, 384 + i * 16, *row)
    struct.pack_into("<Q", raw, 64 + 2 * 56 + 32, len(rows) * 16)
    struct.pack_into("<Q", raw, 64 + 2 * 56 + 40, len(rows) * 16)
    raw[768:768 + len(strings)] = strings
    return bytes(raw)


class WorkerElfSearchTests(unittest.TestCase):
    def test_no_search_tag(self):
        self.assertEqual(review_worker_elf_search(fixture()).category, "no_search_tag")

    def test_exact_origin_classifies_each_tag_but_does_not_approve(self):
        for tag, name in ((15, "rpath"), (29, "runpath")):
            raw = search_fixture(((tag, "$ORIGIN"),))
            value = review_worker_elf_search(raw)
            self.assertEqual((value.category, value.tags), ("exact_origin", (name,)))
            self.assertEqual(value.raw_sha256, sha256(raw).hexdigest())
            with self.assertRaises(WorkerElfError):
                inspect_worker_elf(raw)

    def test_literal_installed_mixed_path_and_empty_components_not_normalized(self):
        for text in ("$ORIGIN:/build/llama-server-cpu/bin:", ":$ORIGIN",
                     "$ORIGIN:", "$ORIGIN::$ORIGIN", "", ".", "/build/bin",
                     "${ORIGIN}", "$ORIGIN/..", "$LIB", "$ORIGIN;$ORIGIN"):
            raw = search_fixture(((29, text),))
            self.assertEqual(review_worker_elf_search(raw).category, "mixed_or_unsupported")
            with self.assertRaises(WorkerElfError):
                inspect_worker_elf(raw)

    def test_conflicting_tag_kinds_are_not_exact_origin(self):
        value = review_worker_elf_search(search_fixture(((15, "$ORIGIN"), (29, "$ORIGIN"))))
        self.assertEqual((value.category, value.tags),
                         ("mixed_or_unsupported", ("rpath", "runpath")))

    def test_duplicate_same_tag_is_malformed(self):
        with self.assertRaises(WorkerElfError):
            review_worker_elf_search(search_fixture(((29, "$ORIGIN"), (29, "$ORIGIN"))))

    def test_search_without_needed_is_still_parsed(self):
        self.assertEqual(review_worker_elf_search(search_fixture(needed=False)).category, "exact_origin")
        raw = bytearray(search_fixture(needed=False))
        struct.pack_into("<Q", raw, 384 + 2 * 16 + 8, 999999)
        with self.assertRaises(WorkerElfError):
            review_worker_elf_search(bytes(raw))

    def test_bad_string_offset_and_unterminated_string_deny(self):
        raw = bytearray(search_fixture())
        struct.pack_into("<Q", raw, 384 + 3 * 16 + 8, 999999)
        with self.assertRaises(WorkerElfError):
            review_worker_elf_search(bytes(raw))
        raw = bytearray(search_fixture())
        raw[768 + len(b"\0libc.so.6\0$ORIGIN")] = 65
        with self.assertRaises(WorkerElfError):
            review_worker_elf_search(bytes(raw))

    def test_missing_table_and_controls_deny(self):
        raw = bytearray(search_fixture(needed=False))
        struct.pack_into("<q", raw, 384, 99)
        for value in (bytes(raw), search_fixture(((29, "private\n"),)), b"PRIVATE", bytearray(fixture())):
            with self.assertRaisesRegex(WorkerElfError, "^worker ELF search review is unavailable$"):
                review_worker_elf_search(value)

    def test_inert_immutable_redacted_output(self):
        raw = search_fixture()
        with patch("builtins.open", side_effect=AssertionError), \
             patch("subprocess.Popen", side_effect=AssertionError), \
             patch("socket.socket", side_effect=AssertionError):
            value = review_worker_elf_search(raw)
        self.assertNotIn("ORIGIN", repr(value))
        self.assertFalse(hasattr(value, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError):
            value.category = "no_search_tag"
