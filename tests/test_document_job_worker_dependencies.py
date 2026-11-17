"""Supplied declarations only; not runtime linker tests."""
from dataclasses import FrozenInstanceError, replace
import struct
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import inspect_worker_elf
from pipeline.document_job_worker_elf_search import review_worker_elf_search
from pipeline.document_job_worker_image import WorkerImageMember, WorkerImageInventory
from pipeline.document_job_worker_dependencies import (
    WorkerDependencyPlan, WorkerLibraryAlias, WorkerDependencyError,
)
from tests.test_document_job_worker_elf import fixture


def raw_elf(names=(), *, interpreter=False):
    raw = bytearray(fixture(names=names))
    if not interpreter:
        struct.pack_into("<I", raw, 64 + 56, 0)  # no PT_INTERP
    return bytes(raw)


def item(path, role, names=(), *, interpreter=False):
    raw = raw_elf(names, interpreter=interpreter)
    return WorkerImageMember(path, len(raw), role, inspect_worker_elf(raw), review_worker_elf_search(raw))


def example():
    a = item(("bin", "worker"), "entrypoint", ("libc.so.6",), interpreter=True)
    b = item(("lib", "libc-real.so.6"), "library", ("ld-linux-x86-64.so.2",))
    c = item(("lib64", "ld-linux-x86-64.so.2"), "interpreter")
    aliases = (WorkerLibraryAlias("libc.so.6", b.target),
               WorkerLibraryAlias("ld-linux-x86-64.so.2", c.target))
    return WorkerImageInventory((a, b, c)), aliases


class WorkerDependencyTests(unittest.TestCase):
    def test_canonical_assignments_order_independent_inert_and_redacted(self):
        inventory, aliases = example()
        with patch("builtins.open", side_effect=AssertionError), \
             patch("subprocess.Popen", side_effect=AssertionError):
            a, b = WorkerDependencyPlan(inventory, aliases), WorkerDependencyPlan(inventory, aliases[::-1])
            self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertEqual(len(a.edges), 2)
        self.assertNotIn("libc-real", repr(a))
        self.assertFalse(hasattr(a, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError):
            a.aliases = ()

    def test_missing_extra_duplicate_and_wrong_type_aliases_deny(self):
        inv, aliases = example()
        for value in ((), aliases[:1], aliases + aliases[:1], list(aliases),
                      aliases + (WorkerLibraryAlias("libextra.so", ("lib", "extra")),)):
            with self.assertRaises(WorkerDependencyError):
                WorkerDependencyPlan(inv, value)

    def test_missing_target_and_nonlibrary_provider_deny(self):
        inv, aliases = example()
        for p in (("lib", "missing"), ("bin", "worker")):
            with self.assertRaises(WorkerDependencyError):
                WorkerDependencyPlan(inv, (replace(aliases[0], target=p), aliases[1]))

    def test_exact_interpreter_binding_and_no_recursive_interpreter(self):
        inv, aliases = example()
        with self.assertRaises(WorkerDependencyError):
            WorkerDependencyPlan(WorkerImageInventory(inv.members[:2]), aliases)
        loader = next(m for m in inv.members if m.role == "interpreter")
        bad = replace(loader, dependencies=replace(loader.dependencies, interpreter="/lib64/ld-linux-x86-64.so.2"))
        with self.assertRaises(WorkerDependencyError):
            WorkerDependencyPlan(WorkerImageInventory(tuple(bad if m is loader else m for m in inv.members)), aliases)

    def test_unreferenced_libraries_deny_but_explicit_plugin_roots_are_descriptive(self):
        inv, aliases = example()
        extra = item(("lib", "unused.so"), "library")
        with self.assertRaises(WorkerDependencyError):
            WorkerDependencyPlan(WorkerImageInventory(inv.members + (extra,)), aliases)
        self.assertEqual(len(WorkerDependencyPlan(WorkerImageInventory(inv.members +
                         (replace(extra, role="plugin"),)), aliases).edges), 2)

    def test_dependency_cycles_terminate_and_require_reachability(self):
        a = item(("bin", "worker"), "entrypoint", ("liba.so",))
        b = item(("lib", "a"), "library", ("libb.so",))
        c = item(("lib", "b"), "library", ("liba.so",))
        value = WorkerDependencyPlan(WorkerImageInventory((a, b, c)),
                    (WorkerLibraryAlias("liba.so", b.target), WorkerLibraryAlias("libb.so", c.target)))
        self.assertEqual(len(value.edges), 3)

    def test_alias_names_and_target_paths_deny(self):
        for name in ("../libc.so.6", "libc.so.6/other", True, "", "PRIVATE"):
            with self.assertRaises(WorkerDependencyError):
                WorkerLibraryAlias(name, ("lib", "x"))
        for path in (("..",), ("/lib",), ("a/b",), ["lib"], ()):
            with self.assertRaises(WorkerDependencyError):
                WorkerLibraryAlias("libc.so.6", path)

    def test_static_declared_image_needs_no_loader(self):
        inv = WorkerImageInventory((item(("bin", "worker"), "entrypoint"),))
        value = WorkerDependencyPlan(inv, ())
        self.assertEqual(value.edges, ())
