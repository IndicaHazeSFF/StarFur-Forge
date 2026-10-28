"""Ten private-result inspection gates; disposable state, never live providers."""

from contextlib import redirect_stdout
from dataclasses import replace
from datetime import UTC, datetime
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from pipeline.document_intake import (
    DocumentAnnotationFailure, DocumentAnnotationResult, prepare_document_text,
    extract_document_memory_candidates,
)
from pipeline.document_job_control import AnnotationJobControlError, control_annotation_jobs, main
from pipeline.document_job_inspection import (
    AnnotationJobInspectionError, build_annotation_result_page, validate_inspection_range,
)
from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError


def candidate_result(document, count=12):
    proposals = [{"store": True, "subject": f"Fixture person {index}", "memory_type": "preference",
                  "summary": f"Proposal summary {index}", "details": "Private candidate detail.",
                  "importance": 0.5, "confidence": 0.8, "retention": "long_term"}
                 for index in range(count)]
    return DocumentAnnotationResult(extract_document_memory_candidates(document, lambda _chunk: {"proposals": proposals}), ())


class AnnotationJobInspectionContracts(unittest.TestCase):
    def test_range_and_source_binding_are_revalidated(self):
        for values in ((True, 5), (0, False), (-1, 5), (4097, 1), (0, 11), (0, 0)):
            with self.assertRaises(AnnotationJobInspectionError):
                validate_inspection_range(*values)
        document = prepare_document_text("Raw observation fixture.", "fixture.md")
        result = candidate_result(document, 1)
        page = build_annotation_result_page(document, result)
        self.assertEqual(page["candidates"][0]["display_ref"], "JC-0001")
        self.assertNotIn("observation_text", json.dumps(page))
        foreign = replace(result, candidates=(replace(result.candidates[0], source_id="foreign"),))
        with self.assertRaises(AnnotationJobInspectionError):
            build_annotation_result_page(document, foreign)


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows support")
class AnnotationJobInspectionSmokes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime.now(UTC)
        self.text = "RAW_SOURCE_ONLY_MARKER: a synthetic private document."
        self.document = prepare_document_text(self.text, "private-title.md")
        with AnnotationJobStore(self.root, clock=lambda: self.now) as store:
            self.job = store.submit(self.text, "private-title.md")
            store.complete(store.mark_running(self.job.job_id), candidate_result(self.document))
        self.base = ["--root", str(self.root), "--acknowledge-maintenance", "inspect-result",
                     self.job.job_id, "--confirm-inspect", self.job.job_id]
        guard = mock.patch("socket.socket", side_effect=AssertionError("no network"))
        guard.start()
        self.addCleanup(guard.stop)

    def control(self, **kwargs):
        fields = dict(job_id=self.job.job_id, confirm_inspect=self.job.job_id)
        fields.update(kwargs)
        return control_annotation_jobs(self.root, "inspect-result", acknowledge_maintenance=True,
                                       clock=lambda: self.now, **fields)

    def path(self, job=None):
        return self.root / ((self.job if job is None else job).job_id + ".json")

    def run_cli(self, extra=()):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([*self.base, *extra])
        return code, output.getvalue()

    def test_01_exact_disclosure_confirmation_precedes_store_open(self):
        before = self.path().read_bytes()
        with mock.patch("pipeline.document_job_control.AnnotationJobStore") as constructor:
            for confirm in (None, "AJ-" + "0" * 32, True):
                with self.assertRaises(AnnotationJobControlError):
                    self.control(confirm_inspect=confirm)
            with self.assertRaises(AnnotationJobControlError):
                control_annotation_jobs(self.root, "inspect-result", job_id=self.job.job_id,
                                        confirm_inspect=self.job.job_id)
            constructor.assert_not_called()
        self.assertEqual(self.path().read_bytes(), before)
        code, output = self.run_cli(["--confirm-inspect", "wrong"])
        self.assertEqual(code, 2)
        self.assertNotIn("Proposal summary", output)

    def test_02_confirmed_page_exposes_only_selected_untrusted_candidate_fields(self):
        result = self.control()
        page = result["inspection"]
        self.assertEqual((page["candidate_count"], page["returned_count"], page["next_offset"]), (12, 5, 5))
        self.assertEqual(page["trust"], "untrusted_noncanonical")
        self.assertFalse(page["quality_verified"])
        self.assertEqual(page["candidates"][0]["summary"], "Proposal summary 0")
        self.assertEqual(page["candidates"][0]["model_declared_confidence"], 0.8)
        serialized = json.dumps(result)
        for absent in ("RAW_SOURCE_ONLY_MARKER", "private-title.md", "observation_text", "source_reference",
                       "chunk_id", "runtime_fingerprint", "primary_model", "DR-", "P-001"):
            self.assertNotIn(absent, serialized)

    def test_03_pages_have_stable_display_only_refs_and_no_hidden_selection(self):
        first = self.control(offset=0, limit=4)["inspection"]
        second = self.control(offset=4, limit=4)["inspection"]
        self.assertEqual(first["candidates"][-1]["display_ref"], "JC-0004")
        self.assertEqual(second["candidates"][0]["display_ref"], "JC-0005")
        self.assertEqual(second["next_offset"], 8)
        end = self.control(offset=12, limit=4)["inspection"]
        self.assertEqual(end["candidates"], [])
        self.assertIsNone(end["next_offset"])
        with self.assertRaises(AnnotationJobControlError):
            self.control(offset=13)

    def test_04_unfinished_or_missing_job_has_no_candidate_output(self):
        with AnnotationJobStore(self.root, clock=lambda: self.now) as store:
            pending = store.submit("Unfinished private source.", "pending.md")
        with self.assertRaises(AnnotationJobStoreError):
            self.control(job_id=pending.job_id, confirm_inspect=pending.job_id)
        missing = "AJ-" + "0" * 32
        with self.assertRaises(AnnotationJobStoreError):
            self.control(job_id=missing, confirm_inspect=missing)
        with AnnotationJobStore(self.root, clock=lambda: self.now) as store:
            self.assertEqual(store.status(pending.job_id).metadata.state, "interrupted")
            self.assertFalse(store.progress(pending.job_id).result_available)

    def test_05_empty_failed_completion_is_inspectable_but_never_quality_success(self):
        with AnnotationJobStore(self.root, clock=lambda: self.now) as store:
            job = store.submit("A failed extraction fixture.", "failed.md")
            document = store.read_source(job.job_id)
            chunk = document.chunks[0]
            failure = DocumentAnnotationFailure(chunk.chunk_id, chunk.scene_index, chunk.chunk_index, 3)
            store.complete(store.mark_running(job.job_id), DocumentAnnotationResult((), (failure,)))
        page = self.control(job_id=job.job_id, confirm_inspect=job.job_id)["inspection"]
        self.assertEqual(page["candidate_count"], 0)
        self.assertEqual(page["failed_chunk_count"], 1)
        self.assertEqual(page["candidates"], [])
        self.assertFalse(page["quality_verified"])

    def test_06_expiry_during_projection_publishes_no_partial_private_output(self):
        before = self.path().read_bytes()
        original = build_annotation_result_page
        def expire(*args, **kwargs):
            page = original(*args, **kwargs)
            self.now = self.job.metadata.expires_at
            return page
        with mock.patch("pipeline.document_job_control.AnnotationJobStore",
                        side_effect=lambda root, clock=None: AnnotationJobStore(root, clock=lambda: self.now)), \
                mock.patch("pipeline.document_job_control.build_annotation_result_page", side_effect=expire):
            code, output = self.run_cli()
        self.assertEqual(code, 2)
        self.assertNotIn("Proposal summary", output)
        self.assertNotIn("Private candidate", output)
        self.assertEqual(self.path().read_bytes(), before)

    def test_07_malformed_durable_output_fails_closed_without_repair(self):
        record = json.loads(self.path().read_bytes())
        record["result"]["candidates"][0]["proposal"]["execute"] = "private-untrusted-payload"
        self.path().write_text(json.dumps(record), encoding="utf-8")
        before = self.path().read_bytes()
        code, output = self.run_cli()
        self.assertEqual(code, 2)
        self.assertNotIn("private-untrusted", output)
        self.assertNotIn("Proposal summary", output)
        self.assertEqual(self.path().read_bytes(), before)

    def test_08_invalid_ranges_precede_open_and_page_overflow_has_no_partial_output(self):
        before = self.path().read_bytes()
        with mock.patch("pipeline.document_job_control.AnnotationJobStore") as constructor:
            for kwargs in ({"limit": 0}, {"limit": 11}, {"offset": -1}, {"offset": True}):
                with self.assertRaises(AnnotationJobControlError):
                    self.control(**kwargs)
            constructor.assert_not_called()
        with mock.patch("pipeline.document_job_inspection.MAX_INSPECTION_PAGE_BYTES", 64):
            code, output = self.run_cli()
        self.assertEqual(code, 2)
        self.assertNotIn("Private candidate", output)
        self.assertEqual(self.path().read_bytes(), before)

    def test_09_legacy_completed_view_is_passive_and_default_status_stays_private(self):
        before = self.path().read_bytes()
        self.assertEqual(json.loads(before)["storage_version"], 2)
        self.control()
        self.assertEqual(self.path().read_bytes(), before)
        status = control_annotation_jobs(self.root, "status", job_id=self.job.job_id,
                                         acknowledge_maintenance=True, clock=lambda: self.now)
        self.assertNotIn("Proposal summary", json.dumps(status))
        self.assertNotIn("Private candidate", json.dumps(status))
        self.assertEqual(status["job"]["expires_at"], self.job.metadata.expires_at.isoformat())
        self.assertEqual(self.path().read_bytes(), before)

    def test_10_real_cli_entries_never_create_review_proposal_or_processing(self):
        import tests.document_job_fixtures
        import starfur
        before = self.path().read_bytes()
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["starfur.py", "annotation-jobs", *self.base]), \
                mock.patch("pipeline.db.connect", side_effect=AssertionError("no canonical database")), \
                mock.patch("pipeline.document_review.DocumentReviewStore.create", side_effect=AssertionError("no review")), \
                mock.patch("pipeline.document_job_processor.AnnotationJobProcessor.start", side_effect=AssertionError("no processing")), \
                redirect_stdout(output):
            with self.assertRaises(SystemExit) as exited:
                starfur.main()
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(json.loads(output.getvalue())["inspection"]["returned_count"], 5)
        response = subprocess.run([sys.executable, "-m", "pipeline.document_job_control", *self.base,
                                   "--offset", "10", "--limit", "2"], capture_output=True, text=True, timeout=15)
        self.assertEqual(response.returncode, 0, response.stderr)
        page = json.loads(response.stdout)["inspection"]
        self.assertEqual(page["candidates"][0]["display_ref"], "JC-0011")
        self.assertIsNone(page["next_offset"])
        self.assertEqual(self.path().read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
