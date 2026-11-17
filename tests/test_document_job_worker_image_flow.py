"""Required POSIX fixture seam: exact read -> inventory -> declared assignments.

Not a loader/execution or private-input smoke. Only temporary synthetic ELF files.
"""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest

from pipeline.document_job_worker_elf_file import inspect_worker_elf_file, WorkerElfFileError
from pipeline.document_job_worker_elf_search import review_worker_elf_search
from pipeline.document_job_worker_image import WorkerImageInventory, WorkerImageMember, WorkerImageError
from pipeline.document_job_worker_dependencies import WorkerDependencyPlan, WorkerLibraryAlias, WorkerDependencyError
from tests.test_document_job_worker_dependencies import raw_elf
from tests.test_document_job_worker_elf_search import search_fixture


@unittest.skipUnless(os.name == "posix", "POSIX fixture acquisition required")
class WorkerImageFixtureFlowTests(unittest.TestCase):
    def test_exact_files_compose_without_materializing_or_launching_image(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.chmod(0o700)
            raw_a, raw_b = raw_elf(("libexample.so",)), raw_elf()
            a, b = root / "entry", root / "library"
            a.write_bytes(raw_a); b.write_bytes(raw_b)
            a.chmod(0o500); b.chmod(0o400)
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                left = inspect_worker_elf_file(fd, "entry", expected_uid=os.getuid(), max_bytes=4096, timeout_seconds=2)
                right = inspect_worker_elf_file(fd, "library", expected_uid=os.getuid(), max_bytes=4096, timeout_seconds=2)
                entry = WorkerImageMember(("bin", "worker"), len(raw_a), "entrypoint", left.dependencies, review_worker_elf_search(raw_a))
                library = WorkerImageMember(("lib", "example-real.so"), len(raw_b), "library", right.dependencies, review_worker_elf_search(raw_b))
                inv = WorkerImageInventory((entry, library))
                plan = WorkerDependencyPlan(inv, (WorkerLibraryAlias("libexample.so", library.target),))
                self.assertEqual(plan.edges, ((entry.target, "libexample.so", library.target),))
                with self.assertRaises(WorkerDependencyError):
                    WorkerDependencyPlan(inv, ())
                with self.assertRaises(WorkerImageError):
                    replace(entry, search=replace(entry.search, raw_sha256="f" * 64))
                self.assertEqual(sorted(p.name for p in root.iterdir()), ["entry", "library"])
                self.assertEqual((a.read_bytes(), b.read_bytes()), (raw_a, raw_b))
            finally:
                os.close(fd)

    def test_origin_review_does_not_bypass_exact_file_denial(self):
        raw = search_fixture()
        self.assertEqual(review_worker_elf_search(raw).category, "exact_origin")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); root.chmod(0o700)
            p = root / "origin"; p.write_bytes(raw); p.chmod(0o500)
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(WorkerElfFileError):
                    inspect_worker_elf_file(fd, "origin", expected_uid=os.getuid(), max_bytes=4096, timeout_seconds=2)
            finally:
                os.close(fd)
