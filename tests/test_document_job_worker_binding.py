"""Exact byte/attempt agreement over a disposable provider-free store."""
from dataclasses import replace
from datetime import UTC, datetime
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pipeline.document_intake import DocumentAnnotationResult
from pipeline.document_job_store import AnnotationJobStore
from pipeline.document_job_worker_binding import (
    WorkerChunkBindingError, bind_worker_chunk, revalidate_worker_chunk,
)
from pipeline.document_job_worker_protocol import WorkerRequest
from tests.document_job_fixtures import multi_chunk_text


@unittest.skipUnless(os.name == "posix", "private store requires POSIX")
class WorkerChunkBindingTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.now = datetime(2026, 11, 10, tzinfo=UTC)
        self.store = self.open_store("first")
        self.job = self.store.submit(multi_chunk_text() + " café", "private-fixture.md")
        self.attempt = self.store.mark_running(self.job.job_id)
        self.plan = self.store.work_plan(self.attempt)
        self.request = WorkerRequest("a" * 32, "b" * 32, "test:v1", "private test instructions",
                                     self.store.read_planned_chunk_text(self.plan), 4096, 256)
        self.record = self.root / "first" / (self.job.job_id + ".json")
        for target in ("pipeline.db.connect", "socket.socket", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("no external work"))
            guard.start()
            self.addCleanup(guard.stop)

    def open_store(self, name):
        root = self.root / name
        root.mkdir(mode=0o700)
        store = AnnotationJobStore(root, clock=lambda: self.now)
        self.addCleanup(store.close)
        return store

    def bind(self):
        return bind_worker_chunk(self.store, self.plan, self.request)

    def test_matching_request_remains_read_only_and_no_prose_retained(self):
        before = self.record.read_bytes()
        binding = self.bind()
        self.assertIsNone(revalidate_worker_chunk(binding, self.store, replace(self.request)))
        self.assertEqual(self.record.read_bytes(), before)
        for name in ("request", "chunk_text", "system_text", "wire_bytes"):
            self.assertFalse(hasattr(binding, name))
        for text in ("private", "Alpha", self.job.job_id, binding._request_digest):
            self.assertNotIn(text, repr(binding))

    def test_other_chunk_and_changed_bytes_refused_before_binding(self):
        document = self.store.read_source(self.job.job_id)
        for body in (self.request.chunk_text + " ", document.chunks[1].text):
            with self.assertRaisesRegex(WorkerChunkBindingError, "unavailable"):
                bind_worker_chunk(self.store, self.plan, replace(self.request, chunk_text=body))

    def test_every_wire_control_is_bound(self):
        binding = self.bind()
        for changes in ({"epoch": "c" * 32}, {"dispatch": "c" * 32}, {"model": "other:v1"},
                        {"system_text": "changed"}, {"context_size": 2048},
                        {"max_output_tokens": 128}, {"chunk_text": "different"}):
            with self.assertRaises(WorkerChunkBindingError):
                revalidate_worker_chunk(binding, self.store, replace(self.request, **changes))

    def test_checkpoint_drift_denies_old_plan_and_binding(self):
        binding = self.bind()
        self.store.save_checkpoint(self.attempt, self.plan.pending[0].chunk_id, DocumentAnnotationResult((), ()))
        with self.assertRaises(WorkerChunkBindingError):
            self.bind()
        with self.assertRaises(WorkerChunkBindingError):
            revalidate_worker_chunk(binding, self.store, self.request)

    def test_owner_expiry_and_closed_store_deny(self):
        binding = self.bind()
        other = self.open_store("other")
        with self.assertRaises(WorkerChunkBindingError):
            revalidate_worker_chunk(binding, other, self.request)
        self.now = self.plan.expires_at
        with self.assertRaises(WorkerChunkBindingError):
            revalidate_worker_chunk(binding, self.store, self.request)
        self.store.close()
        with self.assertRaises(WorkerChunkBindingError):
            revalidate_worker_chunk(binding, self.store, self.request)
