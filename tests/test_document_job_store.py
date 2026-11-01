"""Ten disposable storage lifecycle smoke gates; no live providers or data."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows ACL/handle support")
class AnnotationJobStoreSmokes(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime(2026, 10, 23, 12, tzinfo=UTC)
        self.owners = []
        self.addCleanup(self._close)
        self.database = mock.patch("pipeline.db.connect", side_effect=AssertionError("no database"))
        self.network = mock.patch("socket.socket", side_effect=AssertionError("no network"))
        self.database.start()
        self.network.start()
        self.addCleanup(self.database.stop)
        self.addCleanup(self.network.stop)

    def _close(self):
        for store in reversed(self.owners):
            store.close()

    def store(self, root=None):
        store = AnnotationJobStore(self.root if root is None else root, clock=lambda: self.now)
        self.owners.append(store)
        return store

    def submit(self, store):
        return store.submit("A test-owned person prefers tea.", "source.md")

    def path(self, job):
        return self.root / (job.job_id + ".json")

    def test_01_source_roundtrip_and_passive_status(self):
        with self.store() as store:
            job = self.submit(store)
            source = store.read_source(job.job_id)
            status = asdict(store.status(job.job_id))
            self.assertEqual(set(status), {"job_id", "metadata"})
            self.assertNotIn("tea", repr(status))
            self.assertEqual(source.source_name, "source.md")
            self.assertIn("prefers tea", source.chunks[0].text)
            self.assertEqual(self.path(job).stat().st_mode & 0o777, 0o600)
        with self.store() as reopened:
            self.assertEqual(reopened.read_source(job.job_id), source)

    def test_source_expiring_during_reconstruction_is_not_returned(self):
        with self.store() as store:
            job = self.submit(store)
            from pipeline.document_job_store import prepare_document_text
            calls = 0

            def prepare(*args, **kwargs):
                nonlocal calls
                result = prepare_document_text(*args, **kwargs)
                calls += 1
                # First preparation validates the saved record; the second
                # reconstructs the value after the initial retention check.
                if calls == 2:
                    self.now = job.metadata.expires_at
                return result

            before = self.path(job).read_bytes()
            with mock.patch("pipeline.document_job_store.prepare_document_text", side_effect=prepare):
                with self.assertRaisesRegex(AnnotationJobStoreError, "expired"):
                    store.read_source(job.job_id)
            self.assertEqual(calls, 2)
            self.assertEqual(self.path(job).read_bytes(), before)

    def test_02_second_process_owner_denied_until_release(self):
        store = self.store()
        self.submit(store)
        code = """
import sys
from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError
try:
    with AnnotationJobStore(sys.argv[1]):
        pass
except AnnotationJobStoreError:
    print('denied')
else:
    print('opened')
"""
        # Same process and a separate process must both fail, without recovery.
        with self.assertRaises(AnnotationJobStoreError):
            self.store()
        result = subprocess.run([sys.executable, "-c", code, str(self.root)],
                                capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(result.stdout.strip(), "denied")
        store.close()
        with self.store():
            pass

    def test_03_queued_restart_is_interrupted_and_idempotent(self):
        with self.store() as store:
            job = self.submit(store)
        with self.store() as recovered:
            self.assertEqual(recovered.status(job.job_id).metadata.state, "interrupted")
            first = self.path(job).read_bytes()
        with self.store() as recovered:
            self.assertEqual(recovered.status(job.job_id).metadata.state, "interrupted")
            self.assertEqual(self.path(job).read_bytes(), first)

    def test_04_running_restart_fences_old_attempt(self):
        with self.store() as store:
            job = self.submit(store)
            stale = store.mark_running(job.job_id)
        with self.store() as recovered:
            self.assertEqual(recovered.status(job.job_id).metadata.state, "interrupted")
            with self.assertRaises(AnnotationJobStoreError):
                recovered.interrupt(stale)
            recovered.resume(job.job_id)
            fresh = recovered.mark_running(job.job_id)
            with self.assertRaises(AnnotationJobStoreError):
                recovered.interrupt(stale)
            recovered.interrupt(fresh)

    def test_05_explicit_resume_preserves_deadline_and_attempt_generation(self):
        with self.store() as store:
            job = self.submit(store)
            old = store.mark_running(job.job_id)
            store.interrupt(old)
            self.now += timedelta(hours=23)
            resumed = store.resume(job.job_id)
            self.assertEqual(resumed.metadata.expires_at, job.metadata.expires_at)
            self.assertEqual(resumed.metadata.state, "queued")
            fresh = store.mark_running(job.job_id)
            with self.assertRaises(AnnotationJobStoreError):
                store.interrupt(old)
            self.assertEqual(store.status(job.job_id).metadata.state, "running")
            store.interrupt(fresh)
            self.now = job.metadata.expires_at
            with self.assertRaises(AnnotationJobStoreError):
                store.resume(job.job_id)

    def test_06_expiry_denies_source_before_cleanup(self):
        with self.store() as store:
            job = self.submit(store)
            self.now = job.metadata.expires_at - timedelta(microseconds=1)
            self.assertTrue(store.read_source(job.job_id).chunks)
            self.now = job.metadata.expires_at
            self.assertEqual(store.status(job.job_id).metadata.state, "expired")
            with self.assertRaises(AnnotationJobStoreError):
                store.read_source(job.job_id)
            self.assertTrue(self.path(job).exists())
            self.assertEqual(store.cleanup_expired(), 1)
            self.assertFalse(self.path(job).exists())

    def test_07_cleanup_and_startup_preserve_unrelated_files(self):
        unrelated = self.root / "operator-note.txt"
        unrelated.write_text("retain", encoding="utf-8")
        with self.store() as store:
            expired = self.submit(store)
            self.now += timedelta(hours=12)
            current = self.submit(store)
            self.now += timedelta(hours=12)
            self.assertEqual(store.cleanup_expired(), 1)
            self.assertFalse(self.path(expired).exists())
            self.assertTrue(self.path(current).exists())
            self.assertEqual(unrelated.read_text(), "retain")
        self.now += timedelta(hours=12)
        with self.store():
            self.assertFalse(self.path(current).exists())
            self.assertEqual(unrelated.read_text(), "retain")

    def test_08_explicit_delete_cannot_cancel_running_intent(self):
        with self.store() as store:
            job = self.submit(store)
            other = self.submit(store)
            attempt = store.mark_running(job.job_id)
            original = self.path(job).read_bytes()
            with self.assertRaises(AnnotationJobStoreError):
                store.delete(job.job_id)
            self.assertEqual(self.path(job).read_bytes(), original)
            store.interrupt(attempt)
            store.delete(job.job_id)
            self.assertFalse(self.path(job).exists())
            self.assertTrue(store.read_source(other.job_id).chunks)
        with self.store() as reopened:
            with self.assertRaises(AnnotationJobStoreError):
                reopened.status(job.job_id)

    def test_09_corruption_fails_without_repair_or_private_errors(self):
        with self.store() as store:
            job = self.submit(store)
            original = self.path(job).read_bytes()
        original_record = json.loads(original)
        altered_source = {**original_record["source"], "content": "Changed private source."}
        for payload in (b'{"schema_version":1,"schema_version":2}', b'[]',
                        b'{"private-marker":NaN}',
                        json.dumps({**original_record, "source": altered_source}).encode(),
                        json.dumps({**original_record, "schema_version": 2}).encode(),
                        json.dumps({**original_record, "state": "unsupported"}).encode()):
            with self.subTest(payload=payload[:20]):
                self.path(job).write_bytes(payload)
                with self.assertRaises(AnnotationJobStoreError) as caught:
                    self.store()
                self.assertNotIn("private-marker", str(caught.exception))
                self.assertEqual(self.path(job).read_bytes(), payload)
        self.path(job).write_bytes(original)
        with self.store() as recovered:
            tampered = json.loads(self.path(job).read_bytes())
            tampered["source"]["content"] = "Changed private source."
            self.path(job).write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(AnnotationJobStoreError):
                recovered.read_source(job.job_id)

    def test_10_exact_paths_links_capacity_and_pending_crash_fail_closed(self):
        outside = Path(self.temporary.name) / "unrelated.txt"
        outside.write_text("retain", encoding="utf-8")
        with self.store() as store:
            job = self.submit(store)
            for identifier in ("../unrelated.txt", "AJ-../outside", "AJ-" + "a" * 5000):
                with self.assertRaises(AnnotationJobStoreError):
                    store.read_source(identifier)
            with mock.patch("pipeline.document_job_store.MAX_JOB_COUNT", 1):
                with self.assertRaises(AnnotationJobStoreError):
                    self.submit(store)
            self.assertEqual(len(list(self.root.glob("AJ-*.json"))), 1)
        original = self.path(job).read_bytes()
        self.path(job).unlink()
        self.path(job).symlink_to(outside)
        with self.assertRaises(AnnotationJobStoreError):
            self.store()
        self.path(job).unlink()
        os.link(outside, self.path(job))
        with self.assertRaises(AnnotationJobStoreError):
            self.store()
        self.path(job).unlink()
        self.path(job).write_bytes(original)
        self.path(job).chmod(0o600)
        pending = self.root / ".annotation-job-crash.pending"
        pending.write_bytes(original)
        pending.chmod(0o600)
        with self.assertRaises(AnnotationJobStoreError):
            self.store()
        self.assertEqual(pending.read_bytes(), original)
        self.assertEqual(outside.read_text(), "retain")


class AnnotationJobUnsupportedHostTests(unittest.TestCase):
    @unittest.skipIf(os.name == "posix", "POSIX storage covered by ten lifecycle gates")
    def test_unsupported_host_does_not_create_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-created"
            with self.assertRaisesRegex(AnnotationJobStoreError, "unsupported"):
                AnnotationJobStore(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
