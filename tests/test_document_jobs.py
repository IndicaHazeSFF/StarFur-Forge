from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
import unittest

from pipeline.document_jobs import (
    ANNOTATION_JOB_STATES, AnnotationJobMetadata, AnnotationJobPolicyError,
    annotation_job_accessible, recover_annotation_job, resume_annotation_job,
)


class AnnotationJobPolicyTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 23, 12, tzinfo=UTC)

    def test_exact_fixed_deadline_and_aware_normalization(self):
        job = AnnotationJobMetadata(self.start.astimezone(timezone(timedelta(hours=-4))))
        self.assertEqual(job.submitted_at, self.start)
        self.assertEqual(job.expires_at, self.start + timedelta(hours=24))
        self.assertTrue(annotation_job_accessible(job, now=job.expires_at - timedelta(microseconds=1)))
        self.assertFalse(annotation_job_accessible(job, now=job.expires_at))
        with self.assertRaises(FrozenInstanceError):
            job.submitted_at = self.start + timedelta(hours=1)

    def test_restart_never_replays_queued_or_running_work(self):
        for state in ANNOTATION_JOB_STATES:
            with self.subTest(state=state):
                job = AnnotationJobMetadata(self.start, state)
                recovered = recover_annotation_job(job, now=self.start + timedelta(hours=1))
                expected = "interrupted" if state in {"queued", "running"} else state
                self.assertEqual(recovered.state, expected)
                self.assertEqual(recovered.expires_at, job.expires_at)
                self.assertEqual(recover_annotation_job(recovered, now=self.start + timedelta(hours=2)), recovered)

    def test_expiry_precedes_all_recovery_and_resume(self):
        for state in ANNOTATION_JOB_STATES:
            job = AnnotationJobMetadata(self.start, state)
            self.assertEqual(recover_annotation_job(job, now=job.expires_at).state, "expired")
            with self.assertRaises(AnnotationJobPolicyError):
                resume_annotation_job(job, now=job.expires_at)

    def test_resume_is_explicit_and_never_renews_retention(self):
        job = AnnotationJobMetadata(self.start, "running")
        recovered = recover_annotation_job(job, now=self.start + timedelta(hours=23))
        resumed = resume_annotation_job(recovered, now=self.start + timedelta(hours=23))
        self.assertEqual(resumed.state, "queued")
        self.assertEqual(resumed.expires_at, job.expires_at)
        self.assertEqual(job.state, "running")
        for state in ANNOTATION_JOB_STATES - {"interrupted"}:
            with self.assertRaises(AnnotationJobPolicyError):
                resume_annotation_job(AnnotationJobMetadata(self.start, state), now=self.start)

    def test_closed_schema_and_timestamps_fail_without_coercion(self):
        for kwargs in ({"schema_version": True}, {"schema_version": 2},
                       {"schema_version": 1.0}, {"state": "unknown"}, {"state": []}):
            with self.assertRaises(AnnotationJobPolicyError):
                AnnotationJobMetadata(self.start, **kwargs)
        for timestamp in (self.start.replace(tzinfo=None), "2026-10-23", None,
                          datetime.max.replace(tzinfo=UTC),
                          datetime.min.replace(tzinfo=timezone(timedelta(hours=1)))):
            with self.assertRaises(AnnotationJobPolicyError):
                AnnotationJobMetadata(timestamp)
        job = AnnotationJobMetadata(self.start)
        for now in (self.start - timedelta(seconds=1), self.start.replace(tzinfo=None)):
            with self.assertRaises(AnnotationJobPolicyError):
                recover_annotation_job(job, now=now)
        with self.assertRaises(AnnotationJobPolicyError):
            annotation_job_accessible({}, now=self.start)


if __name__ == "__main__":
    unittest.main()
