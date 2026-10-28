"""Ten disposable durable configuration-evidence gates; no live providers."""

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests.document_job_fixtures import make_application, multi_chunk_text
from pipeline.document_intake import DocumentAnnotationFailure, DocumentAnnotationResult
from pipeline.document_job_processor import AnnotationJobProcessor
from pipeline.document_job_runtime import AnnotationJobRuntimeError, AnnotationRuntimeEvidence
from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError


class AnnotationRuntimeEvidenceContracts(unittest.TestCase):
    def test_coverage_never_turns_missing_evidence_into_uniformity(self):
        for values in ((0, 0, 0), (2, 0, 0), (2, 1, 1), (2, 2, 2)):
            self.assertFalse(AnnotationRuntimeEvidence(*values).to_public_dict()["uniform_declared_configuration"])
        self.assertTrue(AnnotationRuntimeEvidence(2, 2, 1).to_public_dict()["uniform_declared_configuration"])
        for values in ((True, 1, 1), (1, 2, 1), (2, 1, 0), (1, 0, 1), (100001, 1, 1)):
            with self.assertRaises(AnnotationJobRuntimeError):
                AnnotationRuntimeEvidence(*values)


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows support")
class AnnotationRuntimeEvidenceSmokes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime.now(UTC)
        self.owners = []
        self.addCleanup(self.close)
        self.store = self.open_store()
        self.job = self.store.submit(multi_chunk_text(), "fixture.md")
        self.document = self.store.read_source(self.job.job_id)
        self.app, self.session, self.provider = make_application()
        for target in ("pipeline.db.connect", "socket.socket"):
            guard = mock.patch(target, side_effect=AssertionError("no database/network"))
            guard.start()
            self.addCleanup(guard.stop)

    def open_store(self):
        store = AnnotationJobStore(self.root, clock=lambda: self.now)
        self.owners.append(store)
        return store

    def close(self):
        for store in reversed(self.owners):
            store.close()

    def path(self):
        return self.root / (self.job.job_id + ".json")

    def record(self):
        return json.loads(self.path().read_bytes())

    def bound(self):
        runtime = self.app.bind_annotation_job_runtime()
        return AnnotationJobProcessor(self.store, runtime), runtime

    def test_01_bound_processor_atomically_saves_matching_configuration(self):
        processor, runtime = self.bound()
        run = processor.start(self.job.job_id)
        self.assertEqual(processor.step(run).status, "checkpointed")
        record = self.record()
        self.assertEqual(record["storage_version"], 3)
        checkpoint = record["checkpoints"][0]
        self.assertEqual(checkpoint["runtime_fingerprint"], runtime.configuration_fingerprint)
        self.assertEqual(checkpoint["chunk_id"], self.document.chunks[0].chunk_id)
        self.assertEqual(self.store.runtime_evidence(self.job.job_id), AnnotationRuntimeEvidence(1, 1, 1))
        self.assertEqual(len(self.provider.calls), 1)

    def test_02_restart_preserves_evidence_and_reads_do_not_rewrite_or_resume(self):
        processor, runtime = self.bound()
        run = processor.start(self.job.job_id)
        processor.step(run)
        saved = self.record()["checkpoints"]
        self.store.close()
        self.store = self.open_store()
        before = self.path().read_bytes()
        self.assertEqual(self.store.runtime_evidence(self.job.job_id), AnnotationRuntimeEvidence(1, 1, 1))
        self.assertEqual(self.store.status(self.job.job_id).metadata.state, "interrupted")
        self.assertEqual(self.record()["checkpoints"], saved)
        self.assertEqual(self.path().read_bytes(), before)
        self.assertEqual(self.store.status(self.job.job_id).metadata.expires_at, self.job.metadata.expires_at)
        self.assertEqual(len(self.provider.calls), 1)

    def test_03_explicit_rebind_exposes_mixed_configuration_without_redo(self):
        processor, old = self.bound()
        run = processor.start(self.job.job_id)
        processor.step(run)
        saved = self.record()["checkpoints"][0]
        self.session.active_model = "new-fixture-model"
        self.assertEqual(processor.step(run).reason, "runtime_binding_changed")
        self.store.resume(self.job.job_id)
        fresh, new = self.bound()
        self.assertNotEqual(old.configuration_fingerprint, new.configuration_fingerprint)
        run = fresh.start(self.job.job_id)
        for _ in self.document.chunks[1:]:
            self.assertEqual(fresh.step(run).status, "checkpointed")
        self.assertEqual(fresh.finish(run).status, "completed")
        count = len(self.document.chunks)
        self.assertEqual(self.store.runtime_evidence(self.job.job_id), AnnotationRuntimeEvidence(count, count, 2))
        self.assertFalse(self.store.runtime_evidence(self.job.job_id).to_public_dict()["uniform_declared_configuration"])
        self.assertEqual(self.record()["checkpoints"][0], saved)
        self.assertEqual(len(self.provider.calls), count)

    def test_04_legacy_records_remain_unknown_and_unmodified_on_read(self):
        attempt = self.store.mark_running(self.job.job_id)
        for chunk in self.document.chunks:
            self.store.save_checkpoint(attempt, chunk.chunk_id, DocumentAnnotationResult((), ()))
        self.store.finish_checkpoints(attempt)
        self.assertEqual(self.record()["storage_version"], 2)
        before = self.path().read_bytes()
        count = len(self.document.chunks)
        self.assertEqual(self.store.runtime_evidence(self.job.job_id), AnnotationRuntimeEvidence(count, 0, 0))
        self.assertEqual(self.path().read_bytes(), before)
        # A source-only legacy record has no manufactured checkpoint history.
        other = self.store.submit("Legacy fixture.", "legacy.md")
        other_path = self.root / (other.job_id + ".json")
        record = json.loads(other_path.read_bytes())
        record["state"] = "interrupted"
        for field in ("storage_version", "result", "checkpoints"):
            record.pop(field)
        other_path.write_text(json.dumps(record), encoding="utf-8")
        before = other_path.read_bytes()
        self.assertEqual(self.store.runtime_evidence(other.job_id), AnnotationRuntimeEvidence(0, 0, 0))
        self.assertEqual(other_path.read_bytes(), before)

    def test_05_exact_retry_is_idempotent_but_configuration_conflict_denies(self):
        attempt = self.store.mark_running(self.job.job_id)
        first = self.document.chunks[0].chunk_id
        empty = DocumentAnnotationResult((), ())
        self.store.save_checkpoint(attempt, first, empty, runtime_fingerprint="a" * 64)
        before = self.path().read_bytes()
        self.store.save_checkpoint(attempt, first, empty, runtime_fingerprint="a" * 64)
        self.assertEqual(self.path().read_bytes(), before)
        with self.assertRaises(AnnotationJobStoreError):
            self.store.save_checkpoint(attempt, first, empty, runtime_fingerprint="b" * 64)
        self.assertEqual(self.path().read_bytes(), before)
        self.store.interrupt(attempt)
        self.store.resume(self.job.job_id)
        self.store.mark_running(self.job.job_id)
        before = self.path().read_bytes()
        with self.assertRaises(AnnotationJobStoreError):
            self.store.save_checkpoint(attempt, first, empty, runtime_fingerprint="a" * 64)
        self.assertEqual(self.path().read_bytes(), before)

    def test_06_unknown_evidence_cannot_be_backfilled_or_known_evidence_stripped(self):
        attempt = self.store.mark_running(self.job.job_id)
        first, second = [chunk.chunk_id for chunk in self.document.chunks[:2]]
        empty = DocumentAnnotationResult((), ())
        self.store.save_checkpoint(attempt, first, empty)
        before = self.path().read_bytes()
        with self.assertRaises(AnnotationJobStoreError):
            self.store.save_checkpoint(attempt, first, empty, runtime_fingerprint="a" * 64)
        self.assertEqual(self.path().read_bytes(), before)
        self.store.save_checkpoint(attempt, second, empty, runtime_fingerprint="b" * 64)
        self.assertEqual(self.record()["storage_version"], 3)
        self.assertNotIn("runtime_fingerprint", self.record()["checkpoints"][0])
        before = self.path().read_bytes()
        with self.assertRaises(AnnotationJobStoreError):
            self.store.save_checkpoint(attempt, second, empty)
        self.assertEqual(self.path().read_bytes(), before)
        self.assertEqual(self.store.runtime_evidence(self.job.job_id), AnnotationRuntimeEvidence(2, 1, 1))

    def test_07_invalid_or_version_confused_evidence_never_rewrites_state(self):
        attempt = self.store.mark_running(self.job.job_id)
        chunk_id = self.document.chunks[0].chunk_id
        empty = DocumentAnnotationResult((), ())
        for invalid in ("A" * 64, "x", True, 4, {}):
            before = self.path().read_bytes()
            with self.assertRaises(AnnotationJobStoreError):
                self.store.save_checkpoint(attempt, chunk_id, empty, runtime_fingerprint=invalid)
            self.assertEqual(self.path().read_bytes(), before)
        self.store.save_checkpoint(attempt, chunk_id, empty, runtime_fingerprint="a" * 64)
        original = self.record()
        self.store.close()
        for version, value, extra in ((2, "a" * 64, False), (3, None, False),
                                      (3, "private provider text", False), (3, "a" * 64, True), (4, "a" * 64, False)):
            record = json.loads(json.dumps(original))
            record["storage_version"] = version
            record["checkpoints"][0]["runtime_fingerprint"] = value
            if extra:
                record["checkpoints"][0]["model"] = "untrusted model label"
            self.path().write_text(json.dumps(record), encoding="utf-8")
            before = self.path().read_bytes()
            with self.assertRaises(AnnotationJobStoreError):
                self.open_store()
            self.assertEqual(self.path().read_bytes(), before)

    def test_08_expiry_denies_evidence_even_when_time_changes_during_read(self):
        processor, _ = self.bound()
        run = processor.start(self.job.job_id)
        processor.step(run)
        before = self.path().read_bytes()
        original = AnnotationRuntimeEvidence
        def expire(*args):
            evidence = original(*args)
            self.now = self.job.metadata.expires_at
            return evidence
        with mock.patch("pipeline.document_job_store.AnnotationRuntimeEvidence", side_effect=expire):
            with self.assertRaises(AnnotationJobStoreError):
                self.store.runtime_evidence(self.job.job_id)
        self.assertEqual(self.path().read_bytes(), before)
        with self.assertRaises(AnnotationJobStoreError):
            self.store.runtime_evidence(self.job.job_id)

    def test_09_atomic_write_failure_keeps_previous_record_and_schema(self):
        attempt = self.store.mark_running(self.job.job_id)
        before = self.path().read_bytes()
        with mock.patch("pipeline.document_job_store.os.replace", side_effect=OSError("synthetic fault")):
            with self.assertRaises(AnnotationJobStoreError):
                self.store.save_checkpoint(attempt, self.document.chunks[0].chunk_id,
                                           DocumentAnnotationResult((), ()), runtime_fingerprint="a" * 64)
        self.assertEqual(self.path().read_bytes(), before)
        self.assertEqual(self.record()["storage_version"], 2)
        self.assertEqual(list(self.root.glob("*.pending")), [])
        self.assertEqual(self.store.runtime_evidence(self.job.job_id), AnnotationRuntimeEvidence(0, 0, 0))

    def test_10_failed_or_empty_results_do_not_become_quality_and_cli_leaks_no_hash(self):
        attempt = self.store.mark_running(self.job.job_id)
        first = self.document.chunks[0]
        failure = DocumentAnnotationFailure(first.chunk_id, first.scene_index, first.chunk_index, 3)
        self.store.save_checkpoint(attempt, first.chunk_id, DocumentAnnotationResult((), (failure,)), runtime_fingerprint="a" * 64)
        for chunk in self.document.chunks[1:]:
            self.store.save_checkpoint(attempt, chunk.chunk_id, DocumentAnnotationResult((), ()), runtime_fingerprint="a" * 64)
        self.store.finish_checkpoints(attempt)
        evidence = self.store.runtime_evidence(self.job.job_id).to_public_dict()
        self.assertTrue(evidence["uniform_declared_configuration"])
        self.assertEqual(len(self.store.read_result(self.job.job_id).failures), 1)
        self.assertEqual(self.store.progress(self.job.job_id).candidate_count, 0)
        self.assertNotIn("a" * 64, json.dumps(self.store.progress(self.job.job_id).to_public_dict()))
        self.store.close()
        response = subprocess.run([sys.executable, "-m", "pipeline.document_job_control",
                                   "--root", str(self.root), "--acknowledge-maintenance",
                                   "status", self.job.job_id], capture_output=True, text=True, timeout=15)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertNotIn("a" * 64, response.stdout)
        self.assertNotIn("runtime_fingerprint", response.stdout)
        self.assertNotIn("fixture.md", response.stdout)
        self.assertEqual(self.provider.calls, [])


if __name__ == "__main__":
    unittest.main()
