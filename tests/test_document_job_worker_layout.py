"""Pure synthetic layout fixtures; no installed files, loader or provider."""
from dataclasses import FrozenInstanceError, replace
import struct
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_alias_identity import review_worker_alias_identities
from pipeline.document_job_worker_dependencies import WorkerDependencyPlan, WorkerLibraryAlias
from pipeline.document_job_worker_elf import _inspect_metadata, LOADER
from pipeline.document_job_worker_elf_search import review_worker_elf_search
from pipeline.document_job_worker_elf_soname import review_worker_elf_soname
from pipeline.document_job_worker_image import WorkerImageInventory, WorkerImageMember
from pipeline.document_job_worker_layout import WorkerLayoutEdge, WorkerLayoutError, check_worker_proposed_layout
from tests.test_document_job_worker_elf_search import search_fixture


def example(*, misplaced=False, transitive=False, missing=False, mixed=False, rpath=False, extra=False,
            interpreter=False):
    specs = [(("app", "main"), "entrypoint", ("liba.so",), None),
             (("elsewhere", "liba.so") if misplaced else ("app", "liba.so"), "library",
              ("libb.so",) if transitive else (), None if missing else "liba.so")]
    if transitive: specs.append((("elsewhere", "libb.so"), "library", (), "libb.so"))
    if extra: specs.append((("build", "liba.so"), "plugin", (), "liba.so"))
    if interpreter: specs.append((tuple(LOADER.lstrip("/").split("/")), "interpreter", (), "ld-linux-x86-64.so.2"))
    members, identities = [], []
    for path, role, needs, name in specs:
        entries = tuple((1, n) for n in needs)
        if name: entries += ((14, name),)
        if needs: entries += ((15 if rpath else 29, "$ORIGIN:/build/llama-server-cpu/bin:" if mixed else "$ORIGIN"),)
        raw = bytearray(search_fixture(entries, needed=False))
        if not (interpreter and role == "entrypoint"):
            struct.pack_into("<I", raw, 120, 0)  # only the entrypoint may declare PT_INTERP
        raw = bytes(raw)
        metadata, _ = _inspect_metadata(raw, review_search=True)
        members.append(WorkerImageMember(path, len(raw), role, metadata, review_worker_elf_search(raw)))
        if role == "library": identities.append((path, review_worker_elf_soname(raw)))
    aliases = tuple(WorkerLibraryAlias(m.target[-1], m.target) for m in members if m.role == "library")
    plan = WorkerDependencyPlan(WorkerImageInventory(tuple(members)), aliases)
    edges = tuple(WorkerLayoutEdge(*row) for row in plan.edges)
    return plan, tuple(identities), edges


class WorkerLayoutTests(unittest.TestCase):
    def test_fixed_interpreter_is_separate_from_library_aliases(self):
        self.assertEqual(check_worker_proposed_layout(*example(interpreter=True)).edge_count, 1)

    def test_valid_transitive_edges_use_each_requesters_own_origin(self):
        plan, ids, _ = example(transitive=True)
        old, new = ("elsewhere", "libb.so"), ("app", "libb.so")
        inv = WorkerImageInventory(tuple(replace(m, target=new) if m.target == old else m
                                        for m in plan.inventory.members))
        plan = WorkerDependencyPlan(inv, tuple(replace(a, target=new) if a.target == old else a
                                              for a in plan.aliases))
        ids = tuple((new if p == old else p, value) for p, value in ids)
        self.assertEqual(check_worker_proposed_layout(plan, ids, tuple(WorkerLayoutEdge(*r) for r in plan.edges)).edge_count, 2)

    def test_consistent_subset_is_inert_redacted_immutable_and_not_permission(self):
        plan, ids, edges = example()
        with patch("builtins.open", side_effect=AssertionError), patch("subprocess.Popen", side_effect=AssertionError):
            value = check_worker_proposed_layout(plan, ids, edges)
        self.assertEqual(value.status, "internally_consistent_proposed_layout")
        self.assertEqual(value.edge_count, 1)
        self.assertNotIn("liba", repr(value)); self.assertFalse(hasattr(value, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError): value.edge_count = 0

    def test_matching_identity_in_wrong_directory_still_refuses(self):
        plan, ids, edges = example(misplaced=True)
        self.assertEqual(review_worker_alias_identities(plan, ids).outcomes[0][2], "declared_soname_matches")
        with self.assertRaisesRegex(WorkerLayoutError, "dependency_not_at_origin"):
            check_worker_proposed_layout(plan, ids, edges)

    def test_transitive_library_cannot_borrow_ancestor_search(self):
        with self.assertRaisesRegex(WorkerLayoutError, "dependency_not_at_origin"):
            check_worker_proposed_layout(*example(transitive=True))

    def test_missing_or_mismatched_soname_refuses(self):
        with self.assertRaisesRegex(WorkerLayoutError, "soname_not_matching"):
            check_worker_proposed_layout(*example(missing=True))
        plan, ids, edges = example()
        ids = ((ids[0][0], replace(ids[0][1], soname="libother.so")),)
        with self.assertRaisesRegex(WorkerLayoutError, "soname_not_matching"):
            check_worker_proposed_layout(plan, ids, edges)

    def test_mixed_and_rpath_not_promoted_by_c5_fixture(self):
        for changes in (dict(mixed=True), dict(rpath=True)):
            with self.assertRaisesRegex(WorkerLayoutError, "unsupported_search"):
                check_worker_proposed_layout(*example(**changes))

    def test_unassigned_extra_decoy_and_duplicate_copy_refuse(self):
        with self.assertRaisesRegex(WorkerLayoutError, "duplicate_declared_bytes|reserved_destination"):
            check_worker_proposed_layout(*example(extra=True))

    def test_exact_edge_coverage_no_duplicates_or_substitution(self):
        plan, ids, edges = example()
        for rows in ((), edges + edges, (replace(edges[0], target=("other", "liba.so")),), list(edges)):
            with self.assertRaises(WorkerLayoutError): check_worker_proposed_layout(plan, ids, rows)

    def test_interpreter_cannot_be_ordinary_alias(self):
        plan, ids, edges = example()
        member = next(m for m in plan.inventory.members if m.role == "library")
        # Existing plan refuses a forged interpreter before layout approval too.
        with self.assertRaises(ValueError):
            WorkerDependencyPlan(WorkerImageInventory(tuple(replace(m, role="interpreter") if m is member else m
                                for m in plan.inventory.members)), plan.aliases)

    def test_wrong_types_and_unbounded_assignment_refuse(self):
        plan, ids, edges = example()
        for bad in (None, True, "PRIVATE"):
            with self.assertRaises(WorkerLayoutError): check_worker_proposed_layout(bad, ids, edges)
        with self.assertRaises(WorkerLayoutError): check_worker_proposed_layout(plan, ids, edges * 2049)
