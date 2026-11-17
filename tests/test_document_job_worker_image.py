"""Pure supplied image metadata, no installed artifacts or file creation."""
from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import inspect_worker_elf
from pipeline.document_job_worker_elf_search import review_worker_elf_search
from pipeline.document_job_worker_image import WorkerImageMember, WorkerImageInventory, WorkerImageError
from tests.test_document_job_worker_elf import fixture
from tests.test_document_job_worker_elf_search import search_fixture


def member(target=("bin", "worker"), role="entrypoint", raw=None, size=1024):
    raw = fixture() if raw is None else raw
    return WorkerImageMember(target, size, role, inspect_worker_elf(raw), review_worker_elf_search(raw))


class WorkerImageInventoryTests(unittest.TestCase):
    def test_deterministic_order_fingerprint_and_metadata_only(self):
        a, b = member(), member(("lib", "libc.so.6"), "library")
        with patch("builtins.open", side_effect=AssertionError), \
             patch("subprocess.Popen", side_effect=AssertionError), \
             patch("socket.socket", side_effect=AssertionError):
            first, second = WorkerImageInventory((a, b)), WorkerImageInventory((b, a))
            self.assertEqual(first, second)
            self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.total_bytes, 2048)
        self.assertNotIn("libc.so.6", repr(first))
        self.assertNotIn("entrypoint", repr(first))
        self.assertFalse(hasattr(first, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError):
            first.members = ()

    def test_path_components_are_not_host_paths_or_normalized(self):
        for p in ((), (".",), ("..",), ("/bin",), ("a/b",), ("C:",),
                  ("a\\b",), ("",), (True,), ("a" * 129,), ["bin"], ("a",) * 9):
            with self.assertRaises(WorkerImageError):
                member(p)

    def test_file_directory_conflict_and_case_duplicates_deny(self):
        for target in (("bin", "worker"), ("BIN", "Worker"), ("bin",), ("bin", "worker", "child")):
            with self.assertRaises(WorkerImageError):
                WorkerImageInventory((member(), member(target, "library")))

    def test_exactly_one_entrypoint_is_required(self):
        for rows in ((), (member(role="library"),),
                     (member(), member(("bin", "other")))):
            with self.assertRaises(WorkerImageError):
                WorkerImageInventory(rows)

    def test_member_and_aggregate_byte_bounds(self):
        for n in (True, 0, 63, 64 * 1024 * 1024 + 1):
            with self.assertRaises(WorkerImageError):
                member(size=n)
        rows = tuple(member(("bin", str(i)), "entrypoint" if i == 0 else "library",
                            size=64 * 1024 * 1024) for i in range(5))
        with self.assertRaises(WorkerImageError):
            WorkerImageInventory(rows)
        self.assertEqual(WorkerImageInventory(rows[:4]).total_bytes, 256 * 1024 * 1024)

    def test_member_count_bound_and_wrong_types(self):
        rows = tuple(member(("bin", str(i)), "entrypoint" if i == 0 else "library")
                     for i in range(65))
        for value in (rows, list(rows[:1]), (object(),)):
            with self.assertRaises(WorkerImageError):
                WorkerImageInventory(value)
        self.assertEqual(len(WorkerImageInventory(rows[:64]).members), 64)

    def test_metadata_hashes_must_match(self):
        a = member()
        wrong = replace(a.search, raw_sha256="f" * 64)
        with self.assertRaises(WorkerImageError):
            replace(a, search=wrong)
        for role in ("cpu_verified", "host", True):
            with self.assertRaises(WorkerImageError):
                replace(a, role=role)

    def test_declaration_changes_change_fingerprint(self):
        a = member()
        for changed in (replace(a, target=("bin", "other")), replace(a, byte_count=2048),
                        replace(a, dependencies=replace(a.dependencies, needed=()))):
            self.assertNotEqual(WorkerImageInventory((a,)).fingerprint,
                                WorkerImageInventory((changed,)).fingerprint)

    def test_mixed_search_review_is_not_promoted_to_eligibility(self):
        # Inventory can describe an unaccepted proposal without certifying it.
        from pipeline.document_job_worker_elf import _inspect_metadata
        raw = search_fixture(((29, "$ORIGIN:/build/llama-server-cpu/bin:"),))
        a = WorkerImageMember(("lib", "plugin.so"), len(raw), "entrypoint",
                              _inspect_metadata(raw, review_search=True)[0],
                              review_worker_elf_search(raw))
        value = WorkerImageInventory((a,))
        self.assertEqual(value.members[0].search.category, "mixed_or_unsupported")
        self.assertFalse(hasattr(value, "ready"))
