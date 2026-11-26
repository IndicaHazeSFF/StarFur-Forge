"""Pure fixed byte-structure checks; no ELF materialization or loading."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import inspect_worker_elf
from pipeline.document_job_worker_elf_soname import review_worker_elf_soname
from pipeline.document_job_worker_elf_search import review_worker_elf_search

spec = importlib.util.spec_from_file_location('lookup_fixtures', Path(__file__).resolve().parents[1] / 'scripts/private_worker_lookup_fixture.py')
fixed = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixed)


class LookupFixtureTests(unittest.TestCase):
    def test_cooperative_fixture_changes_only_entry_code_and_ready_marker(self):
        original = fixed.main_bytes()
        with patch('builtins.open', side_effect=AssertionError), patch('subprocess.Popen', side_effect=AssertionError):
            raw = fixed.cooperative_main_bytes()
            self.assertEqual(raw, fixed.cooperative_main_bytes())
        self.assertEqual(raw[:0x400], original[:0x400])
        self.assertEqual(raw[0x600:0x9F0], original[0x600:0x9F0])
        self.assertEqual(raw[0x9F0:0x9F1], b'R')
        self.assertEqual(raw[0x9F1:], original[0x9F1:])
        self.assertEqual(inspect_worker_elf(raw).needed, ('libfixture.so',))

    def test_cooperative_entry_contract_success_and_fault_targets(self):
        raw = fixed.cooperative_main_bytes()
        code = raw[0x400:0x600]
        calls = [(struct.unpack_from('<I', code, i + 6)[0],
                  struct.unpack_from('<I', code, i + 1)[0])
                 for i in range(len(code) - 11)
                 if code[i] == 0xBF and code[i + 5] == 0xB8
                 and code[i + 10:i + 12] == b'\x0f\x05']
        self.assertEqual(calls, [(1, 4), (3, 4), (0, 5), (3, 5), (60, 112)])
        failure = code.index(bytes.fromhex("bf70000000b83c0000000f050f0b"))
        guards = [i for i in range(failure) if code[i:i + 2] == b'\x0f\x85']
        self.assertEqual(len(guards), 5)
        self.assertTrue(all(i + 6 + struct.unpack_from('<i', code, i + 2)[0] == failure
                            for i in guards))
        self.assertEqual(code[failure - 11:failure], bytes.fromhex("8b38b83c0000000f050f0b"))
        addresses = [(i, prefix) for i in range(failure)
                     for prefix in (b'\x48\x8d\x35', b'\x80\x3d', b'\x48\x8b\x05')
                     if code.startswith(prefix, i)]
        self.assertEqual([0x400 + i + len(prefix) + 4 + (prefix == b'\x80\x3d')
                          + struct.unpack_from('<i', code, i + len(prefix))[0]
                          for i, prefix in addresses], [0x9F0, 0x1300, 0x1300, 0x1200])
        self.assertEqual(code[addresses[2][0] + 6], ord('G'))

    def test_resident_request_is_a_bare_transitive_dependency_not_a_search_path(self):
        raw = fixed.resident_request_bytes()
        metadata = inspect_worker_elf(raw)
        self.assertEqual(len(raw), 8192)
        self.assertEqual(metadata.needed, ('libfixture-leaf.so', 'ld-linux-x86-64.so.2'))
        self.assertIsNone(metadata.interpreter)
        self.assertEqual(review_worker_elf_search(raw).category, 'no_search_tag')
        self.assertEqual(review_worker_elf_soname(raw).soname, 'libfixture.so')

    def test_resident_fixture_preserves_code_and_data_and_is_not_in_the_old_case(self):
        baseline = fixed.library_bytes()
        with patch('builtins.open', side_effect=AssertionError), patch('subprocess.Popen', side_effect=AssertionError):
            first = fixed.resident_request_bytes()
            self.assertEqual(first, fixed.resident_request_bytes())
        self.assertEqual(first[0x1200:], baseline[0x1200:])
        self.assertEqual(first[0x400:0x600], baseline[0x400:0x600])
        self.assertEqual(inspect_worker_elf(baseline).needed, ('libfixture-leaf.so',))
        self.assertEqual(inspect_worker_elf(fixed.main_bytes()).needed, ('libfixture.so',))

    def test_main_intermediate_leaf_have_no_search_and_exact_transitive_names(self):
        rows = ((fixed.main_bytes(), ('libfixture.so',), None),
                (fixed.library_bytes(), ('libfixture-leaf.so',), 'libfixture.so'),
                (fixed.leaf_bytes(), (), 'libfixture-leaf.so'))
        for raw, needed, soname in rows:
            self.assertEqual(len(raw), 8192)
            self.assertEqual(inspect_worker_elf(raw).needed, needed)
            self.assertEqual(review_worker_elf_search(raw).category, 'no_search_tag')
            self.assertEqual(review_worker_elf_soname(raw).soname, soname)

    def test_fixed_data_values_and_old_generators_unchanged(self):
        self.assertEqual(struct.unpack_from('<I', fixed.library_bytes(), 0x1200)[0], 42)
        self.assertEqual(struct.unpack_from('<I', fixed.library_bytes(decoy=True), 0x1200)[0], 13)
        self.assertEqual(struct.unpack_from('<I', fixed.leaf_bytes(), 0x1200)[0], 7)
        self.assertEqual(review_worker_elf_search(fixed.base.canary_bytes()).category, 'exact_origin')
        self.assertEqual(review_worker_elf_search(fixed.base.cwd_canary_bytes()).category, 'mixed_or_unsupported')

    def test_inert_repeatable_and_not_arbitrary_binary_transform(self):
        with patch('builtins.open', side_effect=AssertionError), patch('subprocess.Popen', side_effect=AssertionError):
            self.assertEqual(fixed.main_bytes(), fixed.main_bytes())
            self.assertEqual(fixed.library_bytes(), fixed.library_bytes())
            self.assertEqual(fixed.leaf_bytes(), fixed.leaf_bytes())
        with self.assertRaises(ValueError): fixed.library_bytes(decoy='yes')
