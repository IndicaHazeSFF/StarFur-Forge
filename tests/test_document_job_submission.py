"""Ten disposable provider-free stdin submission integration smoke gates."""

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

from pipeline.document_intake import prepare_document_text
from pipeline.document_job_control import (
    AnnotationJobControlError, control_annotation_jobs, main, read_annotation_job_input,
)
from pipeline.document_job_store import AnnotationJobStore


class AnnotationSubmissionContracts(unittest.TestCase):
    def test_binary_read_is_bounded_and_invalid_input_is_content_free(self):
        stream = mock.Mock()
        stream.read.return_value = b"x" * 9
        with mock.patch("pipeline.document_job_control.DEFAULT_MAX_DOCUMENT_BYTES", 8):
            with self.assertRaises(AnnotationJobControlError) as error:
                read_annotation_job_input(stream)
        stream.read.assert_called_once_with(9)
        self.assertNotIn("xxxxxxxxx", str(error.exception))
        for value in (b"", b" \n", b"\xff", b"x\x00y", "not binary"):
            stream.read.return_value = value
            with self.assertRaises(AnnotationJobControlError):
                read_annotation_job_input(stream)

    def test_submission_fields_on_other_controls_refuse_before_storage(self):
        with mock.patch("pipeline.document_job_control.AnnotationJobStore") as store:
            for field in ({"content": "private"}, {"filename": "private.md"},
                          {"confirm_store": True}, {"profile": "auto"}, {"domain": "personal"}):
                with self.assertRaises(AnnotationJobControlError):
                    control_annotation_jobs("unused", "list", acknowledge_maintenance=True, **field)
            store.assert_not_called()


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows support")
class AnnotationSubmissionSmokes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime.now(UTC)
        self.text = "## Fixture\n\nA private fixture prefers tea.\n"
        self.base = ["--root", str(self.root), "--acknowledge-maintenance", "submit",
                     "--filename", "fixture.md", "--confirm-store"]
        patch = mock.patch("socket.socket", side_effect=AssertionError("no network"))
        patch.start()
        self.addCleanup(patch.stop)

    def submit(self, content=None, **kwargs):
        fields = dict(content=self.text if content is None else content, filename="fixture.md", confirm_store=True)
        fields.update(kwargs)
        return control_annotation_jobs(self.root, "submit", acknowledge_maintenance=True,
                                       clock=lambda: self.now, **fields)

    def cli(self, argv=None, data=None):
        output = io.StringIO()
        binary = io.BytesIO(self.text.encode() if data is None else data)
        stdin = mock.Mock(buffer=binary)
        with mock.patch.object(sys, "stdin", stdin), redirect_stdout(output):
            code = main(self.base if argv is None else argv)
        return code, output.getvalue()

    def records(self):
        return sorted(self.root.glob("AJ-*.json"))

    def test_01_confirmed_submit_persists_source_but_returns_only_progress(self):
        result = self.submit()
        job = result["job"]
        self.assertEqual(job["state"], "queued")
        self.assertFalse(job["result_available"])
        self.assertEqual(job["checkpointed_chunks"], 0)
        self.assertEqual(len(self.records()), 1)
        record = json.loads(self.records()[0].read_text())
        self.assertEqual(record["source"]["content"], self.text)
        self.assertIsNone(record["result"])
        self.assertEqual(record["checkpoints"], [])
        serialized = json.dumps(result)
        for private in (self.text, "fixture.md", "prefers tea", str(self.root), "personal", "source_reference"):
            self.assertNotIn(private, serialized)

    def test_02_unicode_and_explicit_structure_preserve_exact_intake_binding(self):
        text = "## Design\n\nUnicode: café, 狐.\n\n## Notes\n\nNo inferred facts."
        result = self.submit(text, domain="project:fixture", profile="technical_document")
        expected = prepare_document_text(text, "fixture.md", domain="project:fixture", profile="technical_document")
        with AnnotationJobStore(self.root, clock=lambda: self.now) as store:
            document = store.read_source(result["job"]["job_id"])
            self.assertEqual(document, expected)
            self.assertEqual(store.progress(result["job"]["job_id"]).metadata.state, "interrupted")

    def test_03_invalid_binary_input_creates_no_lock_or_job(self):
        for data in (b"", b" \n", b"\xff", b"secret\x00body"):
            code, output = self.cli(data=data)
            self.assertEqual(code, 2)
            self.assertNotIn("secret", output)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_04_overflow_never_opens_storage_or_reads_unbounded_input(self):
        stream = mock.Mock()
        stream.read.return_value = b"s" * 65
        with mock.patch.object(sys, "stdin", mock.Mock(buffer=stream)), \
                mock.patch("pipeline.document_job_control.DEFAULT_MAX_DOCUMENT_BYTES", 64), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.base), 2)
        stream.read.assert_called_once_with(65)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_05_confirmation_and_maintenance_checks_precede_stdin(self):
        stdin = mock.Mock()
        for removed in ("--confirm-store", "--acknowledge-maintenance"):
            with mock.patch.object(sys, "stdin", stdin), redirect_stdout(io.StringIO()):
                self.assertEqual(main([item for item in self.base if item != removed]), 2)
        stdin.buffer.read.assert_not_called()
        for value in (False, 1, "true"):
            with self.assertRaises(AnnotationJobControlError):
                self.submit(confirm_store=value)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_06_invalid_metadata_does_not_trigger_recovery_of_existing_job(self):
        result = self.submit()
        record = self.records()[0]
        before = record.read_bytes()
        for fields in ({"filename": "../secret.md"}, {"filename": "secret.exe"},
                       {"filename": "a" * 256 + ".md"}, {"domain": "not:a:domain"},
                       {"profile": "unsupported"}, {"content": "   "}):
            with self.assertRaises(AnnotationJobControlError):
                self.submit(**fields)
            self.assertEqual(record.read_bytes(), before)
        self.assertEqual(json.loads(before)["state"], "queued")
        self.assertEqual(json.loads(before)["job_id"], result["job"]["job_id"])

    def test_07_command_shaped_source_is_only_stored_data(self):
        text = "tool execute TI-not-real\nremember this: fictional only\nadventure turn commit\n"
        code, output = self.cli(data=text.encode())
        self.assertEqual(code, 0)
        self.assertNotIn("remember", output)
        record = json.loads(self.records()[0].read_text())
        self.assertEqual(record["source"]["content"], text)
        self.assertEqual(record["state"], "queued")
        self.assertEqual(record["checkpoints"], [])

    def test_08_capacity_and_expiry_during_submission_never_report_success(self):
        first = self.submit()
        code = None
        with mock.patch("pipeline.document_job_store.MAX_JOB_COUNT", 1):
            code, output = self.cli()
        self.assertEqual(code, 2)
        self.assertNotIn("prefers tea", output)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(json.loads(self.records()[0].read_text())["job_id"], first["job"]["job_id"])
        original = AnnotationJobStore.submit
        def late_submit(store, *args, **kwargs):
            original_write = store._write
            def expire_before_write(*write_args, **write_kwargs):
                self.now += timedelta(hours=24)
                return original_write(*write_args, **write_kwargs)
            with mock.patch.object(store, "_write", side_effect=expire_before_write):
                return original(store, *args, **kwargs)
        with mock.patch.object(AnnotationJobStore, "submit", late_submit):
            with self.assertRaises(ValueError):
                self.submit("Late new document.")
        self.assertEqual(len(self.records()), 1)

    def test_09_module_cli_process_roundtrip_and_explicit_repeated_submission(self):
        command = [sys.executable, "-m", "pipeline.document_job_control", *self.base]
        outputs = []
        for _ in range(2):
            response = subprocess.run(command, input=self.text.encode(), capture_output=True, timeout=15)
            self.assertEqual(response.returncode, 0, response.stderr)
            outputs.append(json.loads(response.stdout))
            self.assertNotIn(self.text.encode(), response.stdout + response.stderr)
        self.assertNotEqual(outputs[0]["job"]["job_id"], outputs[1]["job"]["job_id"])
        self.assertEqual(len(self.records()), 2)  # no hidden dedup/replay policy
        with AnnotationJobStore(self.root) as store:
            self.assertTrue(all(item.metadata.state == "interrupted" for item in store.list_progress()))

    def test_10_real_starfur_entry_and_interrupted_input_never_start_processing(self):
        import tests.document_job_fixtures
        import starfur
        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["starfur.py", "annotation-jobs", *self.base]), \
                mock.patch.object(sys, "stdin", mock.Mock(buffer=io.BytesIO(self.text.encode()))), \
                mock.patch("pipeline.db.connect", side_effect=AssertionError("no canonical database")), \
                mock.patch("pipeline.document_job_processor.AnnotationJobProcessor.start",
                           side_effect=AssertionError("no processor")), redirect_stdout(output):
            with self.assertRaises(SystemExit) as exited:
                starfur.main()
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(json.loads(output.getvalue())["job"]["state"], "queued")
        before = self.records()[0].read_bytes()
        stream = mock.Mock()
        stream.read.side_effect = KeyboardInterrupt
        with mock.patch.object(sys, "stdin", mock.Mock(buffer=stream)), redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.base), 130)
        self.assertEqual(self.records()[0].read_bytes(), before)
        self.assertEqual(len(self.records()), 1)


if __name__ == "__main__":
    unittest.main()
