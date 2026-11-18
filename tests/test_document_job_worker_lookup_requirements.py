"""Constructed metadata declarations only; no loader/filesystem inference."""
from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_dependencies import WorkerDependencyPlan, WorkerLibraryAlias
from pipeline.document_job_worker_elf_soname import WorkerElfSonameReview
from pipeline.document_job_worker_image import WorkerImageInventory
from pipeline.document_job_worker_launch_profile import propose_worker_launch_profile, UNRESOLVED
from pipeline.document_job_worker_lookup_requirements import review_worker_lookup_requirements, WorkerLookupRequirementError
from tests.test_document_job_worker_launch_profile import inputs as profile_inputs


def inputs():
    inv, forms = profile_inputs()
    members = tuple(replace(m, dependencies=replace(m.dependencies, needed=("liba.so",))) if m.role == 'entrypoint'
                    else replace(m, dependencies=replace(m.dependencies, needed=("ld-linux-x86-64.so.2",))) if m.role == 'library'
                    else m for m in inv.members)
    inv = WorkerImageInventory(members)
    providers = [m for m in members if m.role in ('library', 'interpreter')]
    aliases = tuple(WorkerLibraryAlias(m.target[-1], m.target) for m in providers)
    ids = tuple((m.target, WorkerElfSonameReview(m.dependencies.raw_sha256, m.target[-1])) for m in providers)
    plan = WorkerDependencyPlan(inv, aliases)
    return plan, forms, ids, propose_worker_launch_profile(inv, forms)


class WorkerLookupRequirementTests(unittest.TestCase):
    def test_private_library_and_resident_interpreter_requirements_only(self):
        args = inputs()
        with patch('builtins.open', side_effect=AssertionError), patch('subprocess.Popen', side_effect=AssertionError):
            a = review_worker_lookup_requirements(*args)
        self.assertEqual(a.dependency_count, 2); self.assertEqual(a.status, 'requirements_only')
        self.assertEqual(a.unresolved, UNRESOLVED); self.assertFalse(hasattr(a, 'eligible_to_execute'))
        with self.assertRaises(FrozenInstanceError): a.status = 'ready'

    def test_stale_profile_or_missing_form_refuses(self):
        plan, forms, ids, profile = inputs()
        with self.assertRaises(WorkerLookupRequirementError):
            review_worker_lookup_requirements(plan, forms, ids, replace(profile, loader_sha256='f'*64))
        with self.assertRaises(WorkerLookupRequirementError):
            review_worker_lookup_requirements(plan, forms[:-1], ids, profile)

    def test_absent_mismatched_or_wrong_hash_soname_refuses(self):
        plan, forms, ids, profile = inputs()
        for kw in (dict(soname=None), dict(soname='libwrong.so'), dict(raw_sha256='f'*64)):
            changed = ((ids[0][0], replace(ids[0][1], **kw)), *ids[1:])
            with self.assertRaises(WorkerLookupRequirementError):
                review_worker_lookup_requirements(plan, forms, changed, profile)

    def test_forged_cleared_gate_or_bad_types_cannot_become_permission(self):
        plan, forms, ids, profile = inputs()
        with self.assertRaises(ValueError): replace(profile, unresolved=())
        for value in (None, True, 'PRIVATE'):
            with self.assertRaises(WorkerLookupRequirementError): review_worker_lookup_requirements(value, forms, ids, profile)

    def test_canonical_order_without_actual_loader_semantics(self):
        plan, forms, ids, profile = inputs()
        a = review_worker_lookup_requirements(plan, forms, ids, profile)
        b = review_worker_lookup_requirements(plan, forms[::-1], ids[::-1], profile)
        self.assertEqual(a, b)
