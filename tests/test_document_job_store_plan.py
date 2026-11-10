"""Disposable store-plan fixtures; no providers or production storage."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pipeline.document_intake import DocumentAnnotationResult
from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError
from tests.document_job_fixtures import multi_chunk_text


@unittest.skipUnless(os.name == "posix", "private store requires POSIX")
class AnnotationJobWorkPlanTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime(2026, 11, 9, tzinfo=UTC)
        self.store = AnnotationJobStore(self.root, clock=lambda: self.now)
        self.addCleanup(self.store.close)
        self.job = self.store.submit(multi_chunk_text() + " café", "fixture.md")
        self.attempt = self.store.mark_running(self.job.job_id)
        self.path = self.root / (self.job.job_id + ".json")
        for target in ("pipeline.db.connect", "socket.socket", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("no external work"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_exact_order_hash_expiry_and_no_source_return(self):
        before = self.path.read_bytes()
        document = self.store.read_source(self.job.job_id)
        plan = self.store.work_plan(self.attempt)
        self.assertIs(plan.attempt, self.attempt)
        self.assertEqual(plan.expires_at, self.job.metadata.expires_at)
        self.assertEqual([item.chunk_id for item in plan.pending], [c.chunk_id for c in document.chunks])
        self.assertGreater(len(plan.pending), 1)
        for item, chunk in zip(plan.pending, document.chunks, strict=True):
            raw = chunk.text.encode("utf-8")
            self.assertEqual((item.text_sha256, item.byte_count), (sha256(raw).hexdigest(), len(raw)))
            self.assertFalse(hasattr(item, "text"))
        for secret in ("Alpha", "fixture.md", self.job.job_id, plan.prepared_digest):
            self.assertNotIn(secret, repr(plan))
        self.assertEqual(self.path.read_bytes(), before)

    def test_saved_chunks_excluded_without_retention_renewal(self):
        before = self.store.work_plan(self.attempt)
        self.store.save_checkpoint(self.attempt, before.pending[0].chunk_id, DocumentAnnotationResult((), ()))
        after = self.store.work_plan(self.attempt)
        self.assertEqual(after.pending, before.pending[1:])
        self.assertEqual(after.expires_at, before.expires_at)
        self.assertEqual(after.prepared_digest, before.prepared_digest)

    def test_wrong_owner_interruption_and_restart_deny(self):
        with self.assertRaises(AnnotationJobStoreError):
            self.store.work_plan(replace(self.attempt, owner_epoch="wrong"))
        self.store.interrupt(self.attempt)
        with self.assertRaises(AnnotationJobStoreError):
            self.store.work_plan(self.attempt)
        self.store.resume(self.job.job_id)
        second = self.store.mark_running(self.job.job_id)
        self.store.close()
        with AnnotationJobStore(self.root, clock=lambda: self.now) as reopened:
            with self.assertRaises(AnnotationJobStoreError):
                reopened.work_plan(second)

    def test_expiry_during_plan_projection_denies_without_write(self):
        original = self.store._work_plan
        before = self.path.read_bytes()

        def project(*args):
            plan = original(*args)
            self.now = self.job.metadata.expires_at
            return plan

        with patch.object(self.store, "_work_plan", side_effect=project):
            with self.assertRaisesRegex(AnnotationJobStoreError, "expired"):
                self.store.work_plan(self.attempt)
        self.assertEqual(self.path.read_bytes(), before)

    def test_reads_only_next_chunk_and_does_not_reserve_or_write(self):
        before = self.path.read_bytes()
        plan = self.store.work_plan(self.attempt)
        document = self.store.read_source(self.job.job_id)
        self.assertEqual(self.store.read_planned_chunk_text(plan), document.chunks[0].text)
        self.assertEqual(self.store.read_planned_chunk_text(plan), document.chunks[0].text)
        self.assertEqual(self.path.read_bytes(), before)

    def test_refuses_changed_checkpoint_plan_and_accepts_fresh_projection(self):
        plan = self.store.work_plan(self.attempt)
        self.store.save_checkpoint(self.attempt, plan.pending[0].chunk_id, DocumentAnnotationResult((), ()))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(AnnotationJobStoreError, "changed"):
            self.store.read_planned_chunk_text(plan)
        fresh = self.store.work_plan(self.attempt)
        self.assertEqual(self.store.read_planned_chunk_text(fresh), self.store.read_source(self.job.job_id).chunks[1].text)
        self.assertEqual(self.path.read_bytes(), before)

    def test_refuses_changed_identity_expiry_order_or_missing_chunks(self):
        plan = self.store.work_plan(self.attempt)
        changed_chunk = replace(plan.pending[0], text_sha256="0" * 64)
        for value in (None, replace(plan, pending=()), replace(plan, pending=plan.pending[1:]),
                      replace(plan, pending=(changed_chunk, *plan.pending[1:])),
                      replace(plan, pending=tuple(reversed(plan.pending))),
                      replace(plan, expires_at=plan.expires_at + timedelta(seconds=1)),
                      replace(plan, prepared_digest="0" * 64)):
            with self.subTest(kind=type(value)), self.assertRaises(AnnotationJobStoreError):
                self.store.read_planned_chunk_text(value)

    def test_interrupted_attempt_refuses_old_plan(self):
        plan = self.store.work_plan(self.attempt)
        self.store.interrupt(self.attempt)
        self.store.resume(self.job.job_id)
        current = self.store.mark_running(self.job.job_id)
        with self.assertRaises(AnnotationJobStoreError):
            self.store.read_planned_chunk_text(plan)
        self.assertTrue(self.store.read_planned_chunk_text(self.store.work_plan(current)))

    def test_expiry_during_revalidation_does_not_return_text(self):
        plan = self.store.work_plan(self.attempt)
        original = self.store._work_plan
        before = self.path.read_bytes()

        def project(*args):
            value = original(*args)
            self.now = plan.expires_at
            return value

        with patch.object(self.store, "_work_plan", side_effect=project):
            with self.assertRaisesRegex(AnnotationJobStoreError, "expired"):
                self.store.read_planned_chunk_text(plan)
        self.assertEqual(self.path.read_bytes(), before)
