"""Pure comparison of supplied metadata, never loader or filesystem tests."""
from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_alias_identity import (
    WorkerAliasIdentityError, WorkerAliasIdentityReview, review_worker_alias_identities,
)
from pipeline.document_job_worker_dependencies import WorkerDependencyPlan
from pipeline.document_job_worker_elf_soname import WorkerElfSonameReview
from pipeline.document_job_worker_image import WorkerImageInventory
from tests.test_document_job_worker_dependencies import example, item


def inputs():
    inventory, aliases = example()
    plan = WorkerDependencyPlan(inventory, aliases)
    hashes = {member.target: member.dependencies.raw_sha256 for member in inventory.members}
    observations = tuple((a.target, WorkerElfSonameReview(hashes[a.target], a.name)) for a in aliases)
    return plan, observations


class WorkerAliasIdentityTests(unittest.TestCase):
    def test_exact_same_hash_alias_comparison_canonical_inert_and_redacted(self):
        plan, observations = inputs()
        with patch("builtins.open", side_effect=AssertionError), \
             patch("subprocess.Popen", side_effect=AssertionError), \
             patch("socket.socket", side_effect=AssertionError):
            a = review_worker_alias_identities(plan, observations)
            b = review_worker_alias_identities(plan, observations[::-1])
        self.assertEqual(a, b)
        self.assertEqual(a.plan_fingerprint, plan.fingerprint)
        self.assertEqual([row[2] for row in a.outcomes], ["declared_soname_matches"] * 2)
        self.assertNotIn("libc", repr(a))
        self.assertFalse(hasattr(a, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError):
            a.outcomes = ()

    def test_missing_and_different_labels_are_explicit_not_accepted_or_guessed(self):
        plan, observations = inputs()
        for name, status in ((None, "declared_soname_absent"),
                             ("libother.so", "declared_soname_differs"),
                             ("libC.so.6", "declared_soname_differs")):
            first = (observations[0][0], replace(observations[0][1], soname=name))
            value = review_worker_alias_identities(plan, (first, observations[1]))
            row = next(row for row in value.outcomes if row[1] == first[0])
            self.assertEqual(row[2], status)

    def test_mismatched_raw_hash_refuses_even_when_name_matches(self):
        plan, observations = inputs()
        first = (observations[0][0], replace(observations[0][1], raw_sha256="f" * 64))
        with self.assertRaisesRegex(WorkerAliasIdentityError, "^worker alias identity review is unavailable$"):
            review_worker_alias_identities(plan, (first, observations[1]))

    def test_exact_coverage_requires_no_missing_extra_or_duplicate_target(self):
        plan, observations = inputs()
        extra = (("bin", "worker"), observations[0][1])
        for values in ((), observations[:1], observations + (extra,), observations + observations[:1],
                       list(observations), (observations[0], ("PRIVATE", observations[1][1]))):
            with self.assertRaises(WorkerAliasIdentityError):
                review_worker_alias_identities(plan, values)

    def test_malformed_sidecars_and_plan_refuse_content_free(self):
        plan, observations = inputs()
        for values in ((None,), ((observations[0][0], None),),
                       (((["lib"],), observations[0][1]),), tuple(observations * 40)):
            with self.assertRaisesRegex(WorkerAliasIdentityError, "^worker alias identity review is unavailable$"):
                review_worker_alias_identities(plan, values)
        with self.assertRaises(WorkerAliasIdentityError):
            review_worker_alias_identities(None, observations)

    def test_empty_alias_static_plan_needs_no_identity_sidecars(self):
        plan = WorkerDependencyPlan(WorkerImageInventory((item(("bin", "worker"), "entrypoint"),)), ())
        self.assertEqual(review_worker_alias_identities(plan, ()).outcomes, ())

    def test_constructed_output_validates_closed_statuses_and_duplicate_names(self):
        row = ("libc.so.6", ("lib", "target"), "declared_soname_matches")
        for fingerprint, rows in (("PRIVATE", (row,)), ("a" * 64, [row]),
                                  ("a" * 64, (row, row)),
                                  ("a" * 64, ((row[0], row[1], "safe_to_execute"),)),
                                  ("a" * 64, (("../libc.so.6", row[1], row[2]),))):
            with self.assertRaises(WorkerAliasIdentityError):
                WorkerAliasIdentityReview(fingerprint, rows)
