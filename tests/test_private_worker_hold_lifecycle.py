"""Fake-only C8i ordering, identity, and publication fences."""

from dataclasses import replace
import unittest

from scripts.private_worker_hold_lifecycle import (
    Cleanup,
    HoldReviewError,
    Observation,
    Step,
    review_held_capture,
)
from scripts.private_worker_mapping_observer import MappingObservation, PausedCanaryStamp


class HeldCaptureReviewTests(unittest.TestCase):
    def setUp(self):
        self.positive = PausedCanaryStamp(1, 100, "a" * 32, "b" * 32)
        self.negative = PausedCanaryStamp(2, 101, "a" * 32, "c" * 32)
        self.observations = tuple(
            Observation(step, self.positive) for step in (
                Step.ATTACHED_WITH_REQUIRED_OPTIONS, Step.EXPECTED_EXEC,
                Step.EXPECTED_ENTRY_STOP, Step.CAPTURE_STARTED,
                Step.CAPTURE_CLOSED_WHILE_HELD, Step.POSITIVE_EXIT_42_REAPED,
            )
        ) + (Observation(Step.NEGATIVE_EXIT_127_REAPED_WITHOUT_ENTRY, self.negative),)
        self.mapping = MappingObservation(1, 3)
        self.cleanup = Cleanup(True, True, True, True)

    def review(self, **overrides):
        return review_held_capture(**{
            "positive": self.positive, "negative": self.negative,
            "observations": self.observations, "mapping": self.mapping,
            "cleanup": self.cleanup, **overrides,
        })

    def alter(self, index, **overrides):
        return (self.observations[:index] + (replace(self.observations[index], **overrides),)
                + self.observations[index + 1:])

    def test_returns_completed_fake_summary(self):
        self.assertEqual(self.review(), MappingObservation(1, 3))

    def test_wrong_stop_resume_and_unsupported_tracing_refuse(self):
        for index, step in ((0, "unsupported"), (2, "unexpected_stop"), (4, "resume")):
            with self.subTest(step=step), self.assertRaises(HoldReviewError):
                self.review(observations=self.alter(index, step=step))

    def test_identity_or_stop_epoch_drift_refuses(self):
        for overrides in ({"pid": 22}, {"start_ticks": 500}, {"invocation": "d" * 32},
                          {"pause_nonce": "e" * 32}):
            with self.subTest(overrides=overrides), self.assertRaises(HoldReviewError):
                self.review(observations=self.alter(4, task=replace(self.positive, **overrides)))

    def test_cannot_replace_negative_control_with_positive(self):
        with self.assertRaises(HoldReviewError):
            self.review(observations=self.alter(6, task=self.positive))
        with self.assertRaises(HoldReviewError):
            self.review(negative=replace(self.negative, pid=self.positive.pid))
        with self.assertRaises(HoldReviewError):
            self.review(negative=replace(self.negative, pause_nonce=self.positive.pause_nonce))

    def test_early_exit_reentry_and_incomplete_transcript_refuse(self):
        events = self.observations
        for transcript in (self.alter(4, step=Step.POSITIVE_EXIT_42_REAPED),
                           self.alter(4, step=Step.CAPTURE_STARTED),
                           events[:4] + events[3:], events[:-1], list(events)):
            with self.subTest(transcript=transcript), self.assertRaises(HoldReviewError):
                self.review(observations=transcript)

    def test_cannot_publish_when_any_cleanup_check_failed(self):
        for flag in ("unit_inactive", "cgroup_empty", "fixture_removed", "parent_unchanged"):
            with self.subTest(flag=flag), self.assertRaises(HoldReviewError):
                self.review(cleanup=replace(self.cleanup, **{flag: False}))
        with self.assertRaises(HoldReviewError):
            self.review(cleanup=Cleanup(1, True, True, True))

    def test_invalid_mapping_summary_refuses(self):
        for summary in (None, MappingObservation(True, 1), MappingObservation(2, 1),
                        MappingObservation(1, 0), MappingObservation(1, 17)):
            with self.subTest(summary=summary), self.assertRaises(HoldReviewError):
                self.review(mapping=summary)
