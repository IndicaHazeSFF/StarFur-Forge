"""Fifteen disposable processor gates (groups B/C/D); no live providers."""

from dataclasses import replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from tests.document_job_fixtures import make_application, multi_chunk_text, proposal_response
from pipeline.document_annotation import DocumentAnnotationDeferredError
from pipeline.document_intake import (
    DocumentAnnotationResult, extract_document_memory_candidates_resilient,
)
from pipeline.document_job_processor import AnnotationJobProcessor, AnnotationJobProcessorError, AnnotationJobStep
from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError


class FakeChunkRuntime:
    def __init__(self):
        self.calls = []
        self.annotation_calls = 0
        self.hook = None
        self.malformed = False

    def result(self, document, chunk_id):
        chunk = next(item for item in document.chunks if item.chunk_id == chunk_id)
        def annotate(_chunk):
            self.annotation_calls += 1
            return {"proposals": "malformed"} if self.malformed else {"proposals": []}
        return extract_document_memory_candidates_resilient(replace(document, chunks=(chunk,)), annotate)

    def annotate_document_chunk(self, document, chunk_id):
        self.calls.append(chunk_id)
        return self.hook(document, chunk_id) if self.hook is not None else self.result(document, chunk_id)


class AnnotationJobProcessorContracts(unittest.TestCase):
    def test_closed_outcomes_reject_raw_reasons_and_invalid_counts(self):
        self.assertEqual(AnnotationJobStep("checkpointed", "chunk_saved", 1).checkpointed_chunks, 1)
        for values in (("failed", "private provider prose", 0), ("checkpointed", "chunk_saved", 0),
                       ("completed", "result_saved", True), ("unknown", "raw", 0)):
            with self.assertRaises(AnnotationJobProcessorError):
                AnnotationJobStep(*values)

    def test_no_runtime_or_store_is_constructed_from_untrusted_inputs(self):
        with self.assertRaises(AnnotationJobProcessorError):
            AnnotationJobProcessor({}, {})


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows support")
class AnnotationJobProcessorSmokes(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime(2026, 10, 25, 12, tzinfo=UTC)
        self.owners = []
        self.addCleanup(self._close)
        for target in ("pipeline.db.connect", "socket.socket"):
            guard = mock.patch(target, side_effect=AssertionError("no database/network"))
            guard.start()
            self.addCleanup(guard.stop)
        self.store = self.open_store()
        self.runtime = FakeChunkRuntime()
        self.processor = AnnotationJobProcessor(self.store, self.runtime)

    def open_store(self):
        store = AnnotationJobStore(self.root, clock=lambda: self.now)
        self.owners.append(store)
        return store

    def _close(self):
        for store in reversed(self.owners):
            store.close()

    def job(self, store=None):
        store = store if store is not None else self.store
        job = store.submit(multi_chunk_text(), "fixture.md")
        document = store.read_source(job.job_id)
        self.assertGreater(len(document.chunks), 1)
        return job, document

    def record(self, job):
        return json.loads((self.root / (job.job_id + ".json")).read_bytes())

    def test_b06_explicit_start_and_one_step_never_auto_finish(self):
        job, document = self.job()
        handle = self.processor.start(job.job_id)
        self.assertEqual(self.runtime.calls, [])
        with self.assertRaises(AnnotationJobProcessorError):
            self.processor.step(replace(handle))
        self.assertEqual(self.store.status(job.job_id).metadata.state, "running")
        outcome = self.processor.step(handle)
        self.assertEqual((outcome.status, outcome.checkpointed_chunks), ("checkpointed", 1))
        self.assertEqual(self.runtime.calls, [document.chunks[0].chunk_id])
        self.assertEqual(self.store.progress(job.job_id).checkpointed_chunks, 1)
        self.assertEqual(self.processor.finish(handle).reason, "chunks_pending")
        self.assertFalse(self.store.progress(job.job_id).result_available)

    def test_b07_restart_requires_resume_and_skips_saved_chunks(self):
        job, document = self.job()
        old = self.processor.start(job.job_id)
        self.processor.step(old)
        self.store.close()
        recovered = self.open_store()
        runtime = FakeChunkRuntime()
        processor = AnnotationJobProcessor(recovered, runtime)
        with self.assertRaises(AnnotationJobStoreError):
            processor.start(job.job_id)
        self.assertEqual(runtime.calls, [])
        recovered.resume(job.job_id)
        fresh = processor.start(job.job_id)
        self.assertEqual(processor.step(fresh).status, "checkpointed")
        self.assertEqual(runtime.calls, [document.chunks[1].chunk_id])
        self.assertEqual(recovered.progress(job.job_id).checkpointed_chunks, 2)

    def test_b08_empty_extraction_is_checkpoint_not_quality_or_memory(self):
        job, _document = self.job()
        handle = self.processor.start(job.job_id)
        self.assertEqual(self.processor.step(handle).status, "checkpointed")
        progress = self.store.progress(job.job_id)
        self.assertEqual((progress.checkpointed_chunks, progress.candidate_count, progress.failed_chunks), (1, 0, 0))
        self.assertEqual(self.runtime.annotation_calls, 1)
        self.assertIsNone(self.record(job)["result"])

    def test_b09_bounded_malformed_extraction_is_saved_as_failed_chunk(self):
        job, _document = self.job()
        self.runtime.malformed = True
        handle = self.processor.start(job.job_id)
        self.assertEqual(self.processor.step(handle).status, "checkpointed")
        self.assertEqual(self.runtime.annotation_calls, 3)
        progress = self.store.progress(job.job_id)
        self.assertEqual((progress.failed_chunks, progress.candidate_count), (1, 0))
        checkpoint = self.record(job)["checkpoints"][0]["result"]
        self.assertEqual(checkpoint["failures"][0]["attempts"], 3)
        self.assertEqual(checkpoint["candidates"], [])

    def test_b10_typed_deferral_never_retries_or_checkpoints(self):
        job, _document = self.job()
        handle = self.processor.start(job.job_id)
        before = self.record(job)
        for reason in ("focus_mode", "provider_capacity_busy", "provider_unavailable", "route_unavailable"):
            def deferred(_document, _chunk_id):
                raise DocumentAnnotationDeferredError(reason)
            self.runtime.hook = deferred
            calls = len(self.runtime.calls)
            outcome = self.processor.step(handle)
            self.assertEqual((outcome.status, outcome.reason), ("deferred", reason))
            self.assertEqual(len(self.runtime.calls), calls + 1)
            self.assertEqual(self.record(job), before)
        self.runtime.hook = None
        self.assertEqual(self.processor.step(handle).status, "checkpointed")

    def test_c11_ctrl_c_preserves_prior_checkpoint_and_fences_run(self):
        job, _document = self.job()
        app, session, provider = make_application()
        processor = AnnotationJobProcessor(self.store, app)
        handle = processor.start(job.job_id)
        processor.step(handle)
        def interrupted():
            raise KeyboardInterrupt
        provider.hook = interrupted
        with self.assertRaises(KeyboardInterrupt):
            processor.step(handle)
        self.assertEqual(self.store.status(job.job_id).metadata.state, "interrupted")
        self.assertEqual(self.store.progress(job.job_id).checkpointed_chunks, 1)
        self.assertEqual(app._workload_gate.active_count("ollama"), 0)
        self.assertEqual(session.provider_lifecycle.snapshot().state, "error")
        self.assertEqual(session.provider_lifecycle.snapshot().error, "annotation_interrupted")
        with self.assertRaises(AnnotationJobProcessorError):
            processor.step(handle)
        self.assertEqual(len(provider.calls), 2)

    def test_c12_interrupt_during_call_discards_late_output(self):
        job, _document = self.job()
        handle = self.processor.start(job.job_id)
        def late(document, chunk_id):
            self.assertEqual(self.processor.interrupt(handle).status, "interrupted")
            return self.runtime.result(document, chunk_id)
        self.runtime.hook = late
        self.assertEqual(self.processor.step(handle).status, "interrupted")
        self.assertEqual(self.store.progress(job.job_id).checkpointed_chunks, 0)
        self.assertEqual(self.store.status(job.job_id).metadata.state, "interrupted")

    def test_c13_concurrent_step_cannot_duplicate_provider_use(self):
        job, _document = self.job()
        handle = self.processor.start(job.job_id)
        entered, release = threading.Event(), threading.Event()
        outcomes, errors = [], []
        def blocked(document, chunk_id):
            entered.set()
            if not release.wait(5):
                raise AssertionError("fake runtime did not receive release")
            return self.runtime.result(document, chunk_id)
        def worker():
            try:
                outcomes.append(self.processor.step(handle))
            except BaseException as error:
                errors.append(type(error).__name__)
        self.runtime.hook = blocked
        thread = threading.Thread(target=worker)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.processor.step(handle).reason, "step_busy")
            self.assertEqual(self.processor.finish(handle).reason, "step_busy")
            self.assertEqual(len(self.runtime.calls), 1)
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(outcomes[0].status, "checkpointed")

    def test_c14_replaced_attempt_rejects_old_output_and_preserves_fresh_run(self):
        job, _document = self.job()
        old = self.processor.start(job.job_id)
        fresh_handles = []
        def replaced(document, chunk_id):
            self.store.interrupt(old._attempt)
            self.store.resume(job.job_id)
            fresh_handles.append(self.processor.start(job.job_id))
            return self.runtime.result(document, chunk_id)
        self.runtime.hook = replaced
        self.assertEqual(self.processor.step(old).status, "failed")
        self.assertEqual(self.store.status(job.job_id).metadata.state, "running")
        self.assertEqual(self.store.progress(job.job_id).checkpointed_chunks, 0)
        self.runtime.hook = None
        self.assertEqual(self.processor.step(fresh_handles[0]).status, "checkpointed")

    def test_c15_expiry_during_call_cannot_save_late_checkpoint(self):
        job, _document = self.job()
        handle = self.processor.start(job.job_id)
        def expired(document, chunk_id):
            self.now = job.metadata.expires_at
            return self.runtime.result(document, chunk_id)
        self.runtime.hook = expired
        self.assertEqual(self.processor.step(handle).status, "failed")
        self.assertEqual(self.record(job)["checkpoints"], [])
        self.assertIsNone(self.record(job)["result"])
        with self.assertRaises(AnnotationJobStoreError):
            self.store.read_result(job.job_id)

    def test_d16_finish_is_explicit_and_never_generates_missing_work(self):
        job, document = self.job()
        handle = self.processor.start(job.job_id)
        self.assertEqual(self.processor.finish(handle).reason, "chunks_pending")
        self.assertEqual(self.runtime.calls, [])
        for _chunk in document.chunks:
            self.assertEqual(self.processor.step(handle).status, "checkpointed")
        self.assertFalse(self.store.progress(job.job_id).result_available)
        calls = len(self.runtime.calls)
        self.assertEqual(self.processor.step(handle).status, "ready")
        self.assertEqual(self.processor.finish(handle).status, "completed")
        self.assertEqual(len(self.runtime.calls), calls)
        self.assertEqual(self.store.read_result(job.job_id).candidates, ())
        with self.assertRaises(AnnotationJobProcessorError):
            self.processor.finish(handle)

    def test_d17_provider_failure_releases_application_capacity_and_keeps_saved_work(self):
        app, _session, provider = make_application()
        processor = AnnotationJobProcessor(self.store, app)
        job, _document = self.job()
        handle = processor.start(job.job_id)
        processor.step(handle)
        def failure():
            raise RuntimeError("private-provider-detail")
        provider.hook = failure
        outcome = processor.step(handle)
        # The existing adapter converts request exceptions into a bounded
        # failed-chunk result after three attempts, not an escaped exception.
        self.assertEqual((outcome.status, outcome.reason), ("checkpointed", "chunk_saved"))
        self.assertNotIn("private-provider-detail", repr(outcome))
        self.assertEqual(app._workload_gate.active_count("ollama"), 0)
        progress = self.store.progress(job.job_id)
        self.assertEqual((progress.checkpointed_chunks, progress.failed_chunks), (2, 1))
        self.assertEqual(len(provider.calls), 4)
        self.assertEqual(self.store.status(job.job_id).metadata.state, "running")
        # A truly escaped runtime failure must still release the application's
        # held capacity and fence the processor without losing earlier work.
        provider.hook = None
        second, _document = self.job()
        other = processor.start(second.job_id)
        processor.step(other)
        with mock.patch("pipeline.application.extract_document_memory_candidates_resilient",
                        side_effect=RuntimeError("private-runtime-detail")):
            outcome = processor.step(other)
        self.assertEqual((outcome.status, outcome.reason), ("failed", "annotation_failed"))
        self.assertEqual(app._workload_gate.active_count("ollama"), 0)
        self.assertEqual(self.store.progress(second.job_id).checkpointed_chunks, 1)
        self.assertEqual(self.store.status(second.job_id).metadata.state, "interrupted")
        self.assertNotIn("private-runtime-detail", repr(outcome))

    def test_d18_malformed_or_foreign_result_never_checkpoints(self):
        for foreign in (False, True):
            job, _document = self.job()
            handle = self.processor.start(job.job_id)
            def invalid(document, chunk_id):
                if not foreign:
                    return {"private-provider-output": "invalid"}
                from pipeline.document_intake import extract_document_memory_candidates
                candidates = extract_document_memory_candidates(document, lambda _chunk: proposal_response())
                return DocumentAnnotationResult((replace(candidates[0], source_id="foreign"),), ())
            self.runtime.hook = invalid
            outcome = self.processor.step(handle)
            self.assertEqual(outcome.status, "failed")
            self.assertEqual(self.store.progress(job.job_id).checkpointed_chunks, 0)
            self.assertNotIn("private-provider-output", repr(outcome))

    def test_d19_storage_failure_never_retries_and_restart_preserves_saved_outcomes(self):
        job, document = self.job()
        handle = self.processor.start(job.job_id)
        before = self.record(job)
        with mock.patch("pipeline.document_job_store.os.replace", side_effect=OSError("private-storage-detail")):
            outcome = self.processor.step(handle)
        self.assertEqual((outcome.status, outcome.reason), ("failed", "storage_failed"))
        self.assertEqual(self.record(job), before)
        self.assertEqual(len(self.runtime.calls), 1)
        with self.assertRaises(AnnotationJobProcessorError):
            self.processor.step(handle)
        self.store.interrupt(handle._attempt)
        self.store.resume(job.job_id)
        fresh = self.processor.start(job.job_id)
        for _chunk in document.chunks:
            self.processor.step(fresh)
        calls = len(self.runtime.calls)
        with mock.patch("pipeline.document_job_store.os.replace", side_effect=OSError("private-storage-detail")):
            outcome = self.processor.finish(fresh)
        self.assertEqual(outcome.reason, "storage_failed")
        self.assertEqual(len(self.runtime.calls), calls)
        self.store.close()
        recovered = self.open_store()
        self.assertEqual(recovered.progress(job.job_id).checkpointed_chunks, len(document.chunks))
        recovered.resume(job.job_id)
        processor = AnnotationJobProcessor(recovered, self.runtime)
        restored = processor.start(job.job_id)
        self.assertEqual(processor.finish(restored).status, "completed")
        self.assertEqual(len(self.runtime.calls), calls)

    def test_d20_full_application_store_flow_stays_explicit_and_noncanonical(self):
        app, session, provider = make_application()
        provider.response = proposal_response()
        processor = AnnotationJobProcessor(self.store, app)
        job, document = self.job()
        handle = processor.start(job.job_id)
        session.focus_mode_set(True)
        self.assertEqual(processor.step(handle).reason, "focus_mode")
        session.focus_mode_set(False)
        held = app._workload_gate.try_acquire("ollama", 1)
        self.assertEqual(processor.step(handle).reason, "provider_capacity_busy")
        self.assertEqual(provider.calls, [])
        self.assertTrue(app._workload_gate.release(held.lease))
        for _chunk in document.chunks:
            self.assertEqual(processor.step(handle).status, "checkpointed")
        self.assertEqual(processor.finish(handle).status, "completed")
        result = self.store.read_result(job.job_id)
        self.assertEqual(len(result.candidates), len(document.chunks))
        self.assertIsNone(result.execution)
        self.assertEqual(provider.probes, 0)
        self.assertEqual(app._workload_gate.active_count("ollama"), 0)
        self.store.close()
        with self.open_store() as recovered:
            self.assertEqual(recovered.read_result(job.job_id), result)
        self.assertEqual(len(provider.calls), len(document.chunks))


if __name__ == "__main__":
    unittest.main()
