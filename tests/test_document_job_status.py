from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
import unittest

from pipeline.document_jobs import AnnotationJobMetadata
from pipeline.document_job_status import AnnotationJobProgress, AnnotationJobProgressError


class AnnotationJobProgressTests(unittest.TestCase):
    def setUp(self):
        self.metadata = AnnotationJobMetadata(datetime(2026, 10, 24, tzinfo=UTC))
        self.progress = AnnotationJobProgress("AJ-" + "a" * 32, self.metadata, 4, 0, 4, 0, 0, False)

    def test_snapshot_is_immutable_and_export_is_detached_and_allowlisted(self):
        exported = self.progress.to_public_dict()
        self.assertEqual(set(exported), {
            "schema_version", "job_id", "state", "submitted_at", "expires_at",
            "total_chunks", "checkpointed_chunks", "pending_chunks", "candidate_count",
            "failed_chunks", "result_available",
        })
        exported["pending_chunks"] = 900
        self.assertEqual(self.progress.to_public_dict()["pending_chunks"], 4)
        with self.assertRaises(FrozenInstanceError):
            self.progress.pending_chunks = 0

    def test_invalid_counts_schema_and_identifiers_are_not_coerced(self):
        for values in ({"pending_chunks": True}, {"failed_chunks": -1}, {"candidate_count": float("nan")},
                       {"total_chunks": 100001}, {"candidate_count": 4097}, {"schema_version": True},
                       {"schema_version": 2}, {"job_id": "../outside"}, {"result_available": 1}):
            with self.assertRaises(AnnotationJobProgressError):
                replace(self.progress, **values)

    def test_completion_availability_and_counts_must_agree(self):
        completed = replace(self.metadata, state="completed")
        accepted = replace(self.progress, metadata=completed, pending_chunks=0,
                           result_available=True, candidate_count=3, failed_chunks=1)
        self.assertTrue(accepted.result_available)
        for values in ({"result_available": True}, {"checkpointed_chunks": 2},
                       {"failed_chunks": 1}, {"candidate_count": 1}, {"pending_chunks": 3}):
            with self.assertRaises(AnnotationJobProgressError):
                replace(self.progress, **values)
        with self.assertRaises(AnnotationJobProgressError):
            replace(accepted, checkpointed_chunks=2)


if __name__ == "__main__":
    unittest.main()
