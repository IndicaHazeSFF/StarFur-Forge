"""Synthetic event sequences only; no native resource creation."""

from dataclasses import replace
import unittest

from scripts.private_worker_cooperative_review import (
    CooperativeReviewError, Event, Step, review_cooperative_mapping,
)
from scripts.private_worker_hold_lifecycle import Cleanup
from scripts.private_worker_mapping_observer import ACCEPTANCE_NS, MAX_BYTES, MappingObservation
from tests.test_private_worker_mapping_observer import IDENTITY, SHAPE, maps


class CooperativeReviewTests(unittest.TestCase):
    def setUp(self):
        self.positive, self.negative = object(), object()
        p, n = self.positive, self.negative
        self.events = (
            Event(Step.CHANNEL_OWNERSHIP_CHECKED, p, 0),
            Event(Step.READY, p, 1, b"R"),
            Event(Step.READY_EOF, p, 2, b""),
            Event(Step.CAPTURE_OPEN, p, 3),
            Event(Step.CAPTURE_CLOSED, p, 4),
            Event(Step.RELEASE, p, 5, b"G"),
            Event(Step.EXIT_REAPED, p, 6, 42),
            Event(Step.CHANNEL_OWNERSHIP_CHECKED, n, 7),
            Event(Step.NO_READY_EOF, n, 8, b""),
            Event(Step.EXIT_REAPED, n, 9, 127),
        )

    def review(self, **overrides):
        return review_cooperative_mapping(**{
            "positive": self.positive, "negative": self.negative, "events": self.events,
            "snapshot": maps(), "identity": IDENTITY, "segments": SHAPE,
            "cleanup": Cleanup(True, True, True, True), **overrides,
        })

    def changed(self, index, **kwargs):
        return self.events[:index] + (replace(self.events[index], **kwargs),) + self.events[index+1:]

    def test_exact_controls_and_cleanup_return_only_mapping_summary(self):
        self.assertEqual(self.review(), MappingObservation(1, len(SHAPE)))

    def test_wrong_duplicate_and_early_tokens_refuse(self):
        for events in (self.changed(1, payload=b"RR"), self.changed(1, payload=b""),
                       self.changed(5, payload=b"R"), self.changed(3, step=Step.RELEASE),
                       self.changed(2, step=Step.READY, payload=b"R")):
            with self.subTest(events=events), self.assertRaises(CooperativeReviewError):
                self.review(events=events)

    def test_leaked_writer_or_failure_before_capture_refuses(self):
        for events in (self.events[:2] + self.events[3:],
                       self.changed(0, step=None), self.changed(2, payload=None),
                       self.changed(4, step=Step.EXIT_REAPED, payload=42)):
            with self.subTest(events=events), self.assertRaises(CooperativeReviewError):
                self.review(events=events)

    def test_capture_deadline_and_nonmonotonic_clock_refuse(self):
        late = tuple(replace(e, time_ns=e.time_ns + ACCEPTANCE_NS - 1) if i >= 4 else e
                     for i, e in enumerate(self.events))
        for events in (late, self.changed(4, time_ns=2)):
            with self.assertRaises(CooperativeReviewError):
                self.review(events=events)

    def test_negative_cannot_emit_ready_or_reuse_positive_binding(self):
        for events in (self.changed(8, step=Step.READY, payload=b"R"),
                       self.changed(9, case=self.positive), self.changed(9, payload=42)):
            with self.assertRaises(CooperativeReviewError):
                self.review(events=events)
        with self.assertRaises(CooperativeReviewError):
            self.review(negative=self.positive)

    def test_without_verified_cleanup_refuses(self):
        for flag in ("unit_inactive", "cgroup_empty", "fixture_removed", "parent_unchanged"):
            with self.assertRaises(CooperativeReviewError):
                self.review(cleanup=replace(Cleanup(True, True, True, True), **{flag: False}))

    def test_maps_bounds_and_exact_identity_still_apply(self):
        for bad in (b"x" * (MAX_BYTES + 1), maps(inode=999), maps() + maps(0x200000)):
            with self.assertRaises(CooperativeReviewError):
                self.review(snapshot=bad)
