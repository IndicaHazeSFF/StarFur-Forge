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
