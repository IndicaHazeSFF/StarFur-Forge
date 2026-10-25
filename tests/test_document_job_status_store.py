"""Five disposable provider-free progress/read-model smoke gates."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pipeline.document_intake import (
    DocumentAnnotationFailure, DocumentAnnotationResult, extract_document_memory_candidates,
)
from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows support")
class AnnotationJobProgressSmokes(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime(2026, 10, 24, 12, tzinfo=UTC)
        self.owners = []
        self.addCleanup(self._close)
        for target in ("pipeline.db.connect", "socket.socket"):
            patch = mock.patch(target, side_effect=AssertionError("no provider/database/network"))
            patch.start()
            self.addCleanup(patch.stop)

    def _close(self):
        for store in reversed(self.owners):
            store.close()

    def store(self):
        store = AnnotationJobStore(self.root, clock=lambda: self.now)
        self.owners.append(store)
        return store

    def job(self, store):
        content = "## First\n\n" + "Alpha. " * 240 + "\n\n## Second\n\n" + "Beta. " * 240
        job = store.submit(content, "private-fixture.md")
        document = store.read_source(job.job_id)
        self.assertGreater(len(document.chunks), 1)
        return job, document

    def candidate_result(self, document, chunk_id):
        candidates = extract_document_memory_candidates(document, lambda chunk: {"proposals": [{
            "store": True, "subject": "Fixture person", "memory_type": "preference",
            "summary": f"private-candidate-{chunk.chunk_index}", "details": "private-details",
            "importance": 0.5, "confidence": 0.9, "retention": "long_term",
        }]})
        return DocumentAnnotationResult(tuple(item for item in candidates if item.chunk_id == chunk_id), ())

    def bytes(self, job):
        return (self.root / (job.job_id + ".json")).read_bytes()

    def test_01_queued_progress_and_listing_are_content_free_and_read_only(self):
        with self.store() as store:
            job, document = self.job(store)
            before = self.bytes(job)
            progress = store.progress(job.job_id)
            self.assertEqual(progress.total_chunks, len(document.chunks))
            self.assertEqual(progress.pending_chunks, len(document.chunks))
            self.assertEqual((progress.checkpointed_chunks, progress.failed_chunks, progress.candidate_count), (0, 0, 0))
            self.assertFalse(progress.result_available)
            self.assertEqual(store.list_progress(), (progress,))
            self.assertEqual(self.bytes(job), before)
            payload = json.dumps(progress.to_public_dict())
            for private in ("private-fixture", "Alpha", "Beta", document.source_id, str(self.root), "source_reference", "domain"):
                self.assertNotIn(private, payload)
            detached = progress.to_public_dict()
            detached["candidate_count"] = 9
            self.assertEqual(store.progress(job.job_id).candidate_count, 0)

    def test_02_checkpoint_progress_distinguishes_saved_failed_and_empty(self):
        with self.store() as store:
            job, document = self.job(store)
            attempt = store.mark_running(job.job_id)
            first, second = document.chunks[:2]
            store.save_checkpoint(attempt, first.chunk_id, self.candidate_result(document, first.chunk_id))
            progress = store.progress(job.job_id)
            self.assertEqual((progress.checkpointed_chunks, progress.candidate_count, progress.failed_chunks), (1, 1, 0))
            failure = DocumentAnnotationFailure(second.chunk_id, second.scene_index, second.chunk_index, 3)
            store.save_checkpoint(attempt, second.chunk_id, DocumentAnnotationResult((), (failure,)))
            for chunk in document.chunks[2:]:
                store.save_checkpoint(attempt, chunk.chunk_id, DocumentAnnotationResult((), ()))
            progress = store.progress(job.job_id)
            self.assertEqual(progress.checkpointed_chunks, len(document.chunks))
            self.assertEqual((progress.pending_chunks, progress.failed_chunks, progress.candidate_count), (0, 1, 1))
            self.assertFalse(progress.result_available)
            store.finish_checkpoints(attempt)
            completed = store.progress(job.job_id)
            self.assertTrue(completed.result_available)
            self.assertEqual((completed.failed_chunks, completed.candidate_count), (1, 1))

    def test_03_restart_retains_counts_without_resuming_or_rewriting_on_read(self):
        with self.store() as store:
            pending, document = self.job(store)
            attempt = store.mark_running(pending.job_id)
            chunk = document.chunks[0]
            store.save_checkpoint(attempt, chunk.chunk_id, self.candidate_result(document, chunk.chunk_id))
            self.now += timedelta(seconds=1)
            done, _ = self.job(store)
            store.complete(store.mark_running(done.job_id), DocumentAnnotationResult((), ()))
        with self.store() as recovered:
            before_pending, before_done = self.bytes(pending), self.bytes(done)
            snapshots = recovered.list_progress()
            self.assertEqual([item.job_id for item in snapshots], [done.job_id, pending.job_id])
            progress = recovered.progress(pending.job_id)
            self.assertEqual(progress.metadata.state, "interrupted")
            self.assertEqual((progress.checkpointed_chunks, progress.candidate_count), (1, 1))
            complete = recovered.progress(done.job_id)
            self.assertEqual((complete.checkpointed_chunks, complete.pending_chunks), (0, 0))
            self.assertTrue(complete.result_available)
            self.assertEqual((self.bytes(pending), self.bytes(done)), (before_pending, before_done))

    def test_04_expiry_hides_progress_without_cleanup_or_retention_renewal(self):
        with self.store() as store:
            job, _ = self.job(store)
            before = self.bytes(job)
            self.now = job.metadata.expires_at - timedelta(seconds=1)
            original_document = store._document
            def expire_during_snapshot(record):
                document = original_document(record)
                self.now = job.metadata.expires_at
                return document
            with mock.patch.object(store, "_document", side_effect=expire_during_snapshot):
                with self.assertRaises(AnnotationJobStoreError):
                    store.progress(job.job_id)
            self.assertEqual(store.list_progress(), ())
            self.assertEqual(self.bytes(job), before)
            self.assertEqual(store.status(job.job_id).metadata.expires_at, job.metadata.expires_at)

    def test_05_malformed_state_and_aggregate_overflow_never_publish_partial_views(self):
        with self.store() as store:
            job, document = self.job(store)
            attempt = store.mark_running(job.job_id)
            first, second = document.chunks[:2]
            store.save_checkpoint(attempt, first.chunk_id, self.candidate_result(document, first.chunk_id))
            before = self.bytes(job)
            with mock.patch("pipeline.document_job_store.MAX_RESULT_CANDIDATES", 1):
                with self.assertRaises(AnnotationJobStoreError):
                    store.save_checkpoint(attempt, second.chunk_id, self.candidate_result(document, second.chunk_id))
            self.assertEqual(self.bytes(job), before)
            self.assertEqual(store.progress(job.job_id).candidate_count, 1)
            other, _ = self.job(store)
            path = self.root / (other.job_id + ".json")
            corrupted = json.loads(self.bytes(other))
            corrupted["checkpoints"] = [{"chunk_id": "foreign", "result": {}}]
            path.write_text(json.dumps(corrupted), encoding="utf-8")
            preserved = path.read_bytes()
            with self.assertRaises(AnnotationJobStoreError):
                store.list_progress()
            self.assertEqual(path.read_bytes(), preserved)
            self.assertEqual(self.bytes(job), before)


if __name__ == "__main__":
    unittest.main()
