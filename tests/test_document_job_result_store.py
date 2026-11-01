"""Ten provider-free result/checkpoint lifecycle smoke gates on disposable storage."""

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pipeline.document_intake import (
    DocumentAnnotationExecution, DocumentAnnotationFailure, DocumentAnnotationResult,
    extract_document_memory_candidates,
)
from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows support")
class AnnotationJobResultStoreSmokes(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime(2026, 10, 23, 12, tzinfo=UTC)
        self.owners = []
        self.addCleanup(self._close)
        for target in ("pipeline.db.connect", "socket.socket"):
            guard = mock.patch(target, side_effect=AssertionError("no external service or database"))
            guard.start()
            self.addCleanup(guard.stop)

    def _close(self):
        for store in reversed(self.owners):
            store.close()

    def store(self):
        store = AnnotationJobStore(self.root, clock=lambda: self.now)
        self.owners.append(store)
        return store

    def job(self, store, *, large=False):
        text = ("## First\n\n" + "Alpha. " * 220 + "\n\n## Second\n\n" + "Beta. " * 220
                if large else "A fixture person prefers tea.")
        job = store.submit(text, "fixture.md")
        document = store.read_source(job.job_id)
        if large:
            self.assertGreater(len(document.chunks), 1)
        return job, document

    def result(self, document):
        candidates = extract_document_memory_candidates(document, lambda chunk: {"proposals": [{
            "store": True, "subject": "Fixture person", "memory_type": "preference",
            "summary": f"Fixture observation {chunk.chunk_index}", "details": "Test-owned candidate",
            "importance": 0.5, "confidence": 0.9, "retention": "long_term",
        }]})
        return DocumentAnnotationResult(candidates, (), DocumentAnnotationExecution("fixture-model", len(document.chunks)))

    def chunk_result(self, document, chunk_id):
        return DocumentAnnotationResult(tuple(candidate for candidate in self.result(document).candidates
                                               if candidate.chunk_id == chunk_id), ())

    def test_result_expiring_during_decoding_is_not_returned(self):
        with self.store() as store:
            job, document = self.job(store)
            store.complete(store.mark_running(job.job_id), self.result(document))
            from pipeline.document_job_store import decode_annotation_job_result
            calls = 0

            def decode(*args, **kwargs):
                nonlocal calls
                result = decode_annotation_job_result(*args, **kwargs)
                calls += 1
                # Record validation decodes first; the returned projection
                # decodes again after the initial retention check.
                if calls == 2:
                    self.now = job.metadata.expires_at
                return result

            before = self.path(job).read_bytes()
            with mock.patch("pipeline.document_job_store.decode_annotation_job_result", side_effect=decode):
                with self.assertRaisesRegex(AnnotationJobStoreError, "expired"):
                    store.read_result(job.job_id)
            self.assertEqual(calls, 2)
            self.assertEqual(self.path(job).read_bytes(), before)

    def path(self, job):
        return self.root / (job.job_id + ".json")

    def test_01_result_survives_restart_without_replay_or_status_disclosure(self):
        with self.store() as store:
            job, document = self.job(store)
            legacy, _ = self.job(store)
            result = self.result(document)
            store.complete(store.mark_running(job.job_id), result)
            status = asdict(store.status(job.job_id))
            self.assertEqual(set(status), {"job_id", "metadata"})
            self.assertNotIn("Fixture observation", repr(status))
        legacy_record = json.loads(self.path(legacy).read_bytes())
        for field in ("storage_version", "result", "checkpoints"):
            del legacy_record[field]
        self.path(legacy).write_text(json.dumps(legacy_record), encoding="utf-8")
        with self.store() as recovered:
            self.assertEqual(recovered.status(job.job_id).metadata.state, "completed")
            self.assertEqual(recovered.status(legacy.job_id).metadata.state, "interrupted")
            self.assertEqual(recovered.read_result(job.job_id), result)
            detached = recovered.read_result(job.job_id)
            detached.candidates[0].proposal["summary"] = "Caller mutation"
            self.assertEqual(recovered.read_result(job.job_id), result)

    def test_02_stale_or_expired_completion_cannot_publish(self):
        with self.store() as store:
            job, document = self.job(store)
            old = store.mark_running(job.job_id)
            store.interrupt(old)
            store.resume(job.job_id)
            current = store.mark_running(job.job_id)
            before = self.path(job).read_bytes()
            with self.assertRaises(AnnotationJobStoreError):
                store.complete(old, self.result(document))
            self.assertEqual(self.path(job).read_bytes(), before)
            self.now = job.metadata.expires_at - timedelta(seconds=1)
            from pipeline import document_job_store
            encoded = document_job_store._encoded
            def expire_during_encoding(value):
                data = encoded(value)
                if type(value) is dict and value.get("state") == "completed":
                    self.now = job.metadata.expires_at
                return data
            with mock.patch("pipeline.document_job_store._encoded", side_effect=expire_during_encoding):
                with self.assertRaises(AnnotationJobStoreError):
                    store.complete(current, self.result(document))
            self.assertEqual(self.path(job).read_bytes(), before)
            self.now = job.metadata.expires_at
            with self.assertRaises(AnnotationJobStoreError):
                store.complete(current, self.result(document))
            self.assertEqual(self.path(job).read_bytes(), before)
            with self.assertRaises(AnnotationJobStoreError):
                store.read_result(job.job_id)

    def test_03_foreign_candidate_provenance_never_rewrites_running_record(self):
        with self.store() as store:
            job, document = self.job(store)
            attempt = store.mark_running(job.job_id)
            result = self.result(document)
            before = self.path(job).read_bytes()
            candidate = result.candidates[0]
            for altered in (replace(candidate, source_id="foreign"), replace(candidate, chunk_id="foreign"),
                            replace(candidate, observation_text="foreign"), replace(candidate, source_reference="foreign")):
                with self.assertRaises(AnnotationJobStoreError):
                    store.complete(attempt, replace(result, candidates=(altered,)))
                self.assertEqual(self.path(job).read_bytes(), before)
            store.complete(attempt, result)
            self.assertEqual(store.read_result(job.job_id), result)

    def test_04_corrupt_saved_result_refuses_recovery_without_rewrite(self):
        with self.store() as store:
            job, document = self.job(store)
            store.complete(store.mark_running(job.job_id), self.result(document))
        saved = self.path(job).read_bytes()
        for field, value in (("schema_version", 99), ("candidates", [{"chunk_id": "foreign", "proposal": {}}])):
            record = json.loads(saved)
            record["result"][field] = value
            payload = json.dumps(record).encode()
            self.path(job).write_bytes(payload)
            with self.assertRaises(AnnotationJobStoreError):
                self.store()
            self.assertEqual(self.path(job).read_bytes(), payload)
        self.path(job).write_bytes(saved)
        with self.store() as recovered:
            self.assertEqual(recovered.status(job.job_id).metadata.state, "completed")

    def test_05_results_obey_original_expiry_and_exact_deletion(self):
        unrelated = self.root / "operator-note.txt"
        unrelated.write_text("retain", encoding="utf-8")
        with self.store() as store:
            job, document = self.job(store)
            store.complete(store.mark_running(job.job_id), self.result(document))
            deleted, other = self.job(store)
            store.complete(store.mark_running(deleted.job_id), self.result(other))
            store.delete(deleted.job_id)
            self.assertFalse(self.path(deleted).exists())
            self.now = job.metadata.expires_at
            with self.assertRaises(AnnotationJobStoreError):
                store.read_result(job.job_id)
            self.assertEqual(store.cleanup_expired(), 1)
            self.assertFalse(self.path(job).exists())
            self.assertEqual(unrelated.read_text(), "retain")

    def test_06_restart_resume_keeps_completed_chunks_out_of_pending_plan(self):
        with self.store() as store:
            job, document = self.job(store, large=True)
            attempt = store.mark_running(job.job_id)
            first = document.chunks[0].chunk_id
            store.save_checkpoint(attempt, first, self.chunk_result(document, first))
            remaining = store.pending_chunk_ids(job.job_id)
            self.assertNotIn(first, remaining)
        with self.store() as recovered:
            self.assertEqual(recovered.status(job.job_id).metadata.state, "interrupted")
            self.assertEqual(recovered.pending_chunk_ids(job.job_id), remaining)
            resumed = recovered.resume(job.job_id)
            self.assertEqual(resumed.metadata.expires_at, job.metadata.expires_at)
            current = recovered.mark_running(job.job_id)
            for chunk_id in remaining:
                recovered.save_checkpoint(current, chunk_id, self.chunk_result(document, chunk_id))
            recovered.finish_checkpoints(current)
            self.assertEqual(len(recovered.read_result(job.job_id).candidates), len(document.chunks))
            self.assertEqual(recovered.pending_chunk_ids(job.job_id), ())

    def test_07_empty_success_and_failed_chunk_remain_distinct(self):
        with self.store() as store:
            job, document = self.job(store, large=True)
            attempt = store.mark_running(job.job_id)
            first = document.chunks[0]
            failure = DocumentAnnotationFailure(first.chunk_id, first.scene_index, first.chunk_index, 3)
            store.save_checkpoint(attempt, first.chunk_id, DocumentAnnotationResult((), (failure,)))
            for chunk in document.chunks[1:]:
                store.save_checkpoint(attempt, chunk.chunk_id, DocumentAnnotationResult((), ()))
            store.finish_checkpoints(attempt)
            result = store.read_result(job.job_id)
            self.assertEqual(result.candidates, ())
            self.assertEqual(result.failures, (failure,))
        with self.store() as recovered:
            self.assertEqual(recovered.read_result(job.job_id).failures, (failure,))

    def test_08_checkpoint_retry_is_idempotent_but_conflict_and_stale_attempt_deny(self):
        with self.store() as store:
            job, document = self.job(store)
            old = store.mark_running(job.job_id)
            chunk_id = document.chunks[0].chunk_id
            result = self.chunk_result(document, chunk_id)
            store.save_checkpoint(old, chunk_id, result)
            before = self.path(job).read_bytes()
            store.save_checkpoint(old, chunk_id, result)
            self.assertEqual(self.path(job).read_bytes(), before)
            with self.assertRaises(AnnotationJobStoreError):
                store.save_checkpoint(old, chunk_id, DocumentAnnotationResult((), ()))
            self.assertEqual(self.path(job).read_bytes(), before)
            store.interrupt(old)
            store.resume(job.job_id)
            fresh = store.mark_running(job.job_id)
            with self.assertRaises(AnnotationJobStoreError):
                store.save_checkpoint(old, chunk_id, result)
            store.finish_checkpoints(fresh)

    def test_09_incomplete_or_conflicting_finalization_never_publishes(self):
        with self.store() as store:
            job, document = self.job(store, large=True)
            attempt = store.mark_running(job.job_id)
            first = document.chunks[0].chunk_id
            store.save_checkpoint(attempt, first, self.chunk_result(document, first))
            before = self.path(job).read_bytes()
            with self.assertRaises(AnnotationJobStoreError):
                store.finish_checkpoints(attempt)
            with self.assertRaises(AnnotationJobStoreError):
                store.complete(attempt, DocumentAnnotationResult((), ()))
            self.assertEqual(self.path(job).read_bytes(), before)
            for chunk_id in store.pending_chunk_ids(job.job_id):
                store.save_checkpoint(attempt, chunk_id, self.chunk_result(document, chunk_id))
            with self.assertRaises(AnnotationJobStoreError):
                store.complete(attempt, DocumentAnnotationResult((), ()))
            store.finish_checkpoints(attempt)
            expected = replace(self.result(document), execution=None)
            self.assertEqual(store.read_result(job.job_id), expected)

    def test_10_failed_atomic_result_replace_keeps_prior_record(self):
        with self.store() as store:
            job, document = self.job(store)
            attempt = store.mark_running(job.job_id)
            before = self.path(job).read_bytes()
            with mock.patch("pipeline.document_job_store.os.replace", side_effect=OSError("private-marker")):
                with self.assertRaises(AnnotationJobStoreError) as caught:
                    store.complete(attempt, self.result(document))
            self.assertNotIn("private-marker", str(caught.exception))
            self.assertEqual(self.path(job).read_bytes(), before)
            self.assertEqual(list(self.root.glob(".annotation-job-*.pending")), [])
        with self.store() as recovered:
            self.assertEqual(recovered.status(job.job_id).metadata.state, "interrupted")
            with self.assertRaises(AnnotationJobStoreError):
                recovered.read_result(job.job_id)


if __name__ == "__main__":
    unittest.main()
