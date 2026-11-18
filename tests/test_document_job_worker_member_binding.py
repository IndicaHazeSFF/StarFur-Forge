"""Supplied synthetic observations only, not on-disk or sealed-image evidence."""
from dataclasses import FrozenInstanceError, replace
import stat
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf_file import WorkerElfFileObservation, WorkerElfIdentityObservation
from pipeline.document_job_worker_elf_soname import WorkerElfSonameReview
from pipeline.document_job_worker_member_binding import (
    WorkerExpectedMember, WorkerMemberBindingError, bind_worker_member_observations,
)
from tests.test_document_job_worker_layout import example


def inputs(**kw):
    plan, identities, edges = example(**kw)
    names = dict(identities); pins, observed = [], []
    for i, member in enumerate(plan.inventory.members):
        mode = stat.S_IFREG | 0o500
        pins.append(WorkerExpectedMember(member.target, member.dependencies.raw_sha256, member.byte_count, mode, 1000))
        identity = (1, i + 1, mode, 1000, 1, member.byte_count, 0, 0)
        value = WorkerElfIdentityObservation(WorkerElfFileObservation(member.dependencies, identity), member.search,
                    names.get(member.target, WorkerElfSonameReview(member.dependencies.raw_sha256, None)))
        observed.append((member.target, value))
    return plan, tuple(pins), tuple(observed), edges


class WorkerMemberBindingTests(unittest.TestCase):
    def test_inert_exact_canonical_binding_redacted_not_authority(self):
        plan, pins, obs, edges = inputs()
        with patch("builtins.open", side_effect=AssertionError), patch("subprocess.Popen", side_effect=AssertionError):
            a = bind_worker_member_observations(plan, pins, obs, edges)
            b = bind_worker_member_observations(plan, pins[::-1], obs[::-1], edges)
        self.assertEqual(a, b); self.assertEqual(a.total_bytes, sum(p.byte_count for p in pins))
        self.assertNotIn("app", repr(a)); self.assertFalse(hasattr(a, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError): a.member_count = 0

    def test_each_expected_pin_field_must_match_snapshot(self):
        plan, pins, obs, edges = inputs()
        for change in (dict(raw_sha256="f" * 64), dict(byte_count=pins[0].byte_count + 1),
                       dict(source_mode=stat.S_IFREG | 0o400), dict(source_uid=999)):
            with self.assertRaises(WorkerMemberBindingError):
                bind_worker_member_observations(plan, (replace(pins[0], **change), *pins[1:]), obs, edges)

    def test_missing_extra_duplicate_or_malformed_coverage_refuses(self):
        plan, pins, obs, edges = inputs()
        for p, o in ((pins[:1], obs), (pins, obs[:1]), (pins + pins[:1], obs), (pins, obs + obs[:1]),
                     (list(pins), obs), (pins, (None,)), (pins, (("PRIVATE", obs[0][1]),))):
            with self.assertRaisesRegex(WorkerMemberBindingError, "^worker member binding is unavailable$"):
                bind_worker_member_observations(plan, p, o, edges)

    def test_wrong_directory_still_fails_despite_matching_pins(self):
        with self.assertRaises(WorkerMemberBindingError): bind_worker_member_observations(*inputs(misplaced=True))

    def test_stat_identity_change_changes_observation_fingerprint(self):
        plan, pins, obs, edges = inputs()
        before = bind_worker_member_observations(plan, pins, obs, edges)
        target, value = obs[0]; identity = (*value.file.identity[:-1], 1)
        changed = replace(value, file=replace(value.file, identity=identity))
        after = bind_worker_member_observations(plan, pins, ((target, changed), *obs[1:]), edges)
        self.assertNotEqual(before.observation_fingerprint, after.observation_fingerprint)

    def test_reused_inode_for_different_targets_refuses(self):
        plan, pins, obs, edges = inputs()
        first, second = obs
        changed = replace(second[1], file=replace(second[1].file,
                          identity=first[1].file.identity[:2] + second[1].file.identity[2:]))
        with self.assertRaises(WorkerMemberBindingError):
            bind_worker_member_observations(plan, pins, (first, (second[0], changed)), edges)

    def test_unsafe_modes_sizes_paths_and_types_refuse(self):
        _, pins, _, _ = inputs()
        for kw in (dict(source_mode=stat.S_IFREG | 0o502), dict(source_mode=stat.S_IFDIR | 0o500),
                   dict(byte_count=True), dict(byte_count=63), dict(target=("..",)), dict(source_uid=True)):
            with self.assertRaises(WorkerMemberBindingError): replace(pins[0], **kw)
        with self.assertRaises(WorkerMemberBindingError): bind_worker_member_observations(None, (), (), ())
