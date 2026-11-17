"""Synthetic bytes only; no installed binary, loader or provider execution."""
from dataclasses import FrozenInstanceError
from hashlib import sha256
import struct
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import (
    ElfDependencies, WorkerElfError, inspect_worker_elf, LOADER,
)


def fixture(*, names=("libc.so.6", "libstdc++.so.6"), search_tag=None):
    raw = bytearray(1024)
    raw[:64] = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01" + b"\0" * 9,
                           3, 62, 1, 0, 64, 0, 0, 64, 56, 3, 0, 0, 0)
    rows = [(1, 5, 0, 0x400000, 0, len(raw), len(raw), 4096),
            (3, 4, 256, 0x400100, 0, len(LOADER) + 1, len(LOADER) + 1, 1)]
    strings = b"\0"
    dynamic = [(5, 0x400300), (10, 1 + sum(len(n.encode()) + 1 for n in names))]
    for name in names:
        dynamic.append((1, len(strings)))
        strings += name.encode() + b"\0"
    if search_tag is not None:
        dynamic.append((search_tag, 0))
    dynamic.append((0, 0))
    rows.append((2, 6, 384, 0x400180, 0, len(dynamic) * 16, len(dynamic) * 16, 8))
    for i, row in enumerate(rows):
        struct.pack_into("<IIQQQQQQ", raw, 64 + i * 56, *row)
    raw[256:256 + len(LOADER) + 1] = LOADER.encode() + b"\0"
    for i, row in enumerate(dynamic):
        struct.pack_into("<qQ", raw, 384 + i * 16, *row)
    raw[768:768 + len(strings)] = strings
    return bytes(raw)


class WorkerElfInspectionTests(unittest.TestCase):
    def test_only_system_v_and_gnu_abi_zero_versions_are_supported(self):
        for abi in (0, 3):
            raw = bytearray(fixture()); raw[7] = abi
            self.assertEqual(inspect_worker_elf(bytes(raw)).needed, ("libc.so.6", "libstdc++.so.6"))
        for abi in (1, 2, 9, 255):
            raw = bytearray(fixture()); raw[7] = abi
            with self.assertRaises(WorkerElfError):
                inspect_worker_elf(bytes(raw))
        raw = bytearray(fixture()); raw[7:9] = bytes((3, 1))
        with self.assertRaises(WorkerElfError):
            inspect_worker_elf(bytes(raw))

    def test_dynamic_dependency_labels_hash_and_immutable_redaction(self):
        raw = fixture()
        value = inspect_worker_elf(raw)
        self.assertEqual(value.needed, ("libc.so.6", "libstdc++.so.6"))
        self.assertEqual(value.interpreter, LOADER)
        self.assertEqual(value.object_kind, "shared_object")
        self.assertEqual(value.raw_sha256, sha256(raw).hexdigest())
        self.assertNotIn("libc", repr(value))
        with self.assertRaises(FrozenInstanceError):
            value.needed = ()

    def test_no_io_or_subprocess_is_needed(self):
        raw = fixture()
        with patch("builtins.open", side_effect=AssertionError), \
             patch("subprocess.Popen", side_effect=AssertionError):
            self.assertEqual(len(inspect_worker_elf(raw).needed), 2)

    def test_fixed_loader_dependency_does_not_require_lib_prefix(self):
        value = inspect_worker_elf(fixture(names=("libc.so.6", "ld-linux-x86-64.so.2")))
        self.assertEqual(value.needed, ("libc.so.6", "ld-linux-x86-64.so.2"))
        for name in ("ld-PRIVATE.so.2", "ld-linux-x86-64.so.3", "../ld-linux-x86-64.so.2"):
            with self.assertRaises(WorkerElfError):
                inspect_worker_elf(fixture(names=(name,)))

    def test_wrong_magic_arch_class_version_and_program_table_deny(self):
        for offset, value in ((0, b"MZ"), (4, b"\x01"), (5, b"\x02"),
                              (6, b"\x02"), (18, b"\x03\0"),
                              (32, struct.pack("<Q", 1000)), (56, b"\xff\xff")):
            with self.subTest(offset=offset):
                raw = bytearray(fixture())
                raw[offset:offset + len(value)] = value
                with self.assertRaises(WorkerElfError):
                    inspect_worker_elf(bytes(raw))

    def test_short_mutable_or_excessive_input_deny(self):
        for raw in (b"", b"ELF", bytearray(fixture()), "PRIVATE"):
            with self.assertRaisesRegex(WorkerElfError, "^worker ELF inspection is unavailable$"):
                inspect_worker_elf(raw)
        with patch("pipeline.document_job_worker_elf.MAX_ELF_BYTES", 100):
            with self.assertRaises(WorkerElfError):
                inspect_worker_elf(fixture())

    def test_rpath_and_runpath_deny_even_empty(self):
        for tag in (15, 29):
            with self.assertRaises(WorkerElfError):
                inspect_worker_elf(fixture(search_tag=tag))

    def test_duplicate_or_path_dependency_denies(self):
        for names in (("libc.so.6", "libc.so.6"), ("../libc.so.6",),
                      ("/tmp/libc.so.6",), ("libc.so.6\nPRIVATE",)):
            with self.assertRaises(WorkerElfError):
                inspect_worker_elf(fixture(names=names))

    def test_oversized_unmapped_or_unterminated_string_table_denies(self):
        for offset, value in ((392, 0x900000), (408, 2**32), (424, 2000)):
            raw = bytearray(fixture())
            struct.pack_into("<Q", raw, offset, value)
            with self.assertRaises(WorkerElfError):
                inspect_worker_elf(bytes(raw))
        raw = bytearray(fixture(names=("libc.so.6",)))
        raw[768:778] = b"x" * 10
        with self.assertRaises(WorkerElfError):
            inspect_worker_elf(bytes(raw))

    def test_missing_dynamic_terminator_denies(self):
        raw = bytearray(fixture())
        struct.pack_into("<qQ", raw, 448, 12, 0)
        with self.assertRaises(WorkerElfError):
            inspect_worker_elf(bytes(raw))

    def test_duplicate_dynamic_singleton_denies(self):
        raw = bytearray(fixture())
        struct.pack_into("<qQ", raw, 416, 5, 0x400300)
        with self.assertRaises(WorkerElfError):
            inspect_worker_elf(bytes(raw))

    def test_ambiguous_load_mapping_denies(self):
        raw = bytearray(fixture())
        # Replace the interpreter with a second overlapping PT_LOAD.
        struct.pack_into("<IIQQQQQQ", raw, 120, 1, 4, 0, 0x400000, 0, 1024, 1024, 4096)
        with self.assertRaises(WorkerElfError):
            inspect_worker_elf(bytes(raw))

    def test_static_executable_can_have_no_interpreter_or_dependencies(self):
        raw = bytearray(fixture())
        struct.pack_into("<H", raw, 16, 2)
        struct.pack_into("<H", raw, 56, 1)
        value = inspect_worker_elf(bytes(raw))
        self.assertEqual(value.object_kind, "executable")
        self.assertIsNone(value.interpreter)
        self.assertEqual(value.needed, ())

    def test_declared_metadata_is_validated_but_not_attested(self):
        with self.assertRaises(WorkerElfError):
            ElfDependencies("a" * 64, "shared_object", None, ("/PRIVATE",))
        with self.assertRaises(WorkerElfError):
            ElfDependencies("a" * 64, "shared_object", "/PRIVATE", ())
