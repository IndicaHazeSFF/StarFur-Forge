"""Five local-control integration smoke gates, only disposable private state."""

from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from pipeline.document_intake import DocumentAnnotationResult
from pipeline.document_job_control import (
    AnnotationJobControlError, control_annotation_jobs, main,
)
from pipeline.document_job_store import AnnotationJobStore


class AnnotationJobControlContracts(unittest.TestCase):
    def test_invalid_controls_never_construct_storage(self):
        job = "AJ-" + "a" * 32
        with mock.patch("pipeline.document_job_control.AnnotationJobStore") as store:
            for kwargs in (
                {}, {"acknowledge_maintenance": 1},
                {"acknowledge_maintenance": True, "confirm_delete": "other"},
            ):
                with self.assertRaises(AnnotationJobControlError):
                    control_annotation_jobs("unused", "delete", job_id=job, **kwargs)
            for action, identity in (("submit", job), ("status", "../escape"), ("list", job)):
                with self.assertRaises(AnnotationJobControlError):
                    control_annotation_jobs("unused", action, job_id=identity,
                                            acknowledge_maintenance=True)
            store.assert_not_called()


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows support")
class AnnotationJobControlSmokes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime.now(UTC)
        self.owner = None
        self.addCleanup(self.close)
        for name in ("socket.socket",):
            patch = mock.patch(name, side_effect=AssertionError("no network"))
            patch.start()
            self.addCleanup(patch.stop)

    def close(self):
        if self.owner is not None:
            self.owner.close()
            self.owner = None

    def seed(self, state="queued", *, expired=False):
        self.owner = AnnotationJobStore(self.root, clock=lambda: self.now - timedelta(hours=25) if expired else self.now)
        job = self.owner.submit("Private fixture prefers tea.", "private-title.md")
        if state in {"running", "completed"}:
            attempt = self.owner.mark_running(job.job_id)
            if state == "completed":
                self.owner.complete(attempt, DocumentAnnotationResult((), ()))
        self.close()
        return job

    def control(self, action, **kwargs):
        return control_annotation_jobs(self.root, action, acknowledge_maintenance=True,
                                       clock=lambda: self.now, **kwargs)

    def test_01_progress_is_content_free_and_open_maintenance_is_explicit(self):
        job = self.seed("completed")
        path = self.root / (job.job_id + ".json")
        before = path.read_bytes()
        listing = self.control("list")
        status = self.control("status", job_id=job.job_id)
        self.assertEqual(listing["jobs"], [status["job"]])
        self.assertEqual(status["job"]["state"], "completed")
        self.assertTrue(status["job"]["result_available"])
        self.assertEqual(path.read_bytes(), before)
        encoded = json.dumps(listing)
        for private in ("Private fixture", "private-title", str(self.root), "personal", "source_reference", "proposals"):
            self.assertNotIn(private, encoded)
        self.assertTrue(listing["maintenance_on_open"])

    def test_02_restart_fences_and_explicit_resume_preserves_deadline(self):
        job = self.seed("running")
        before = self.control("status", job_id=job.job_id)["job"]
        self.assertEqual(before["state"], "interrupted")
        resumed = self.control("resume", job_id=job.job_id)["job"]
        self.assertEqual(resumed["state"], "queued")
        self.assertEqual(resumed["expires_at"], before["expires_at"])
        self.assertEqual(resumed["submitted_at"], before["submitted_at"])
        self.assertEqual(resumed["checkpointed_chunks"], 0)
        # No worker owns resumed intent; the next process must fence it again.
        self.assertEqual(self.control("status", job_id=job.job_id)["job"]["state"], "interrupted")

    def test_03_expiry_sweeps_only_job_records_after_acknowledgement(self):
        job = self.seed(expired=True)
        record = self.root / (job.job_id + ".json")
        unrelated = self.root / "keep.txt"
        unrelated.write_text("keep", encoding="utf-8")
        with self.assertRaises(AnnotationJobControlError):
            control_annotation_jobs(self.root, "list")
        self.assertTrue(record.exists())
        self.assertEqual(self.control("list")["jobs"], [])
        self.assertFalse(record.exists())
        self.assertEqual(unrelated.read_text(), "keep")

    def test_04_exact_delete_confirmation_precedes_any_store_effect(self):
        job = self.seed("running")
        record = self.root / (job.job_id + ".json")
        before = record.read_bytes()
        for confirmation in (None, "AJ-" + "0" * 32):
            with self.assertRaises(AnnotationJobControlError):
                self.control("delete", job_id=job.job_id, confirm_delete=confirmation)
            self.assertEqual(record.read_bytes(), before)  # no startup recovery either
        result = self.control("delete", job_id=job.job_id, confirm_delete=job.job_id)
        self.assertTrue(result["deleted"])
        self.assertFalse(record.exists())
        self.assertEqual(self.control("list")["jobs"], [])

    def test_05_cli_refusals_and_real_entrypoint_release_owner(self):
        job = self.seed("completed")
        base = ["--root", str(self.root), "--acknowledge-maintenance"]
        # Exercise the real operator entrypoint, not a mocked store facade.
        import tests.document_job_fixtures  # provider module stub for starfur import only
        import starfur
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["starfur.py", "annotation-jobs", *base, "status", job.job_id]), redirect_stdout(output):
            with self.assertRaises(SystemExit) as finished:
                starfur.main()
        self.assertEqual(finished.exception.code, 0)
        self.assertEqual(json.loads(output.getvalue())["job"]["job_id"], job.job_id)
        # Independent process confirms owner release and the module entrypoint.
        completed = subprocess.run([sys.executable, "-m", "pipeline.document_job_control", *base, "list"],
                                   capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(json.loads(completed.stdout)["jobs"]), 1)
        self.owner = AnnotationJobStore(self.root)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([*base, "list"]), 2)  # live owner cannot be stolen
        self.assertNotIn(str(self.root), output.getvalue())
        self.close()
        missing = self.root / "not-created"
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--root", str(missing), "--acknowledge-maintenance", "list"]), 2)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
