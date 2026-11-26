from dataclasses import replace
import unittest

from scripts.private_worker_cooperative_launch_plan import (
    FIXTURES, POLICY, LaunchPlan, LaunchPlanRefused, bind_launch_plan,
)


class CooperativeLaunchPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = LaunchPlan((
            ("pipeline/document_job_worker_elf.py", "a"*64),
            ("scripts/private_worker_loader_smoke.py", "b"*64),
        ), tuple((name, "c"*64) for name in FIXTURES), "d"*64, POLICY)

    def test_digest_stable_for_independent_equal_manifest(self):
        first = bind_launch_plan(expected=self.plan, observed=replace(self.plan))
        self.assertRegex(first, r"^[a-f0-9]{64}$")
        self.assertEqual(first, bind_launch_plan(expected=replace(self.plan), observed=self.plan))

    def test_source_removal_extra_or_content_change_refuses(self):
        for sources in (
            self.plan.sources[:-1],
            self.plan.sources + (("scripts/private_worker_root_smoke.py", "b"*64),),
            (self.plan.sources[0], (self.plan.sources[1][0], "e"*64)),
        ):
            with self.subTest(sources=sources), self.assertRaises(LaunchPlanRefused):
                bind_launch_plan(expected=self.plan, observed=replace(self.plan, sources=sources))

    def test_identical_invalid_manifests_refuse(self):
        for bad in (
            replace(self.plan, fixtures=self.plan.fixtures[:-1]),
            replace(self.plan, policy=POLICY[:-1] + ("no-new-privileges=no",)),
            replace(self.plan, sources=self.plan.sources[::-1]),
            replace(self.plan, sources=self.plan.sources + self.plan.sources[-1:]),
            replace(self.plan, sources=(("scripts/../private_worker_x.py", "a"*64),)),
            replace(self.plan, command_spec_sha256="0"*64),
        ):
            with self.subTest(bad=bad), self.assertRaises(LaunchPlanRefused):
                bind_launch_plan(expected=bad, observed=bad)

    def test_spec_and_fixture_change_refuse(self):
        for bad in (replace(self.plan, command_spec_sha256="e"*64),
                    replace(self.plan, fixtures=(("leaf", "f"*64), *self.plan.fixtures[1:]))):
            with self.subTest(bad=bad), self.assertRaises(LaunchPlanRefused):
                bind_launch_plan(expected=self.plan, observed=bad)
