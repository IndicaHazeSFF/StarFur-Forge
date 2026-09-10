import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox import (
    SandboxBackendResult,
    SandboxFile,
    SandboxOutputCollector,
    SandboxPolicy,
    SandboxRequest,
    SandboxService,
    format_sandbox_report,
)


class RecordingBackend:
    name = "recording"
    available = True

    def __init__(self, result=None):
        self.result = result or SandboxBackendResult("completed", stdout="tests passed", exit_code=0)
        self.workspace = None
        self.files = None
        self.policy = None

    def run(self, request, workspace, policy, *, stdout, stderr):
        self.workspace = workspace
        self.files = {path.relative_to(workspace).as_posix(): path.read_text(encoding="utf-8") for path in workspace.rglob("*") if path.is_file()}
        self.policy = policy
        return self.result

    def supports_policy(self, policy):
        return not policy.network_allowed


class SandboxTests(unittest.TestCase):
    def _request(self):
        return SandboxRequest(
            "SB-rust-001", "murr", "rust_tests", "Compile a bounded Rust exercise.",
            (SandboxFile("src/main.rs", "fn main() {}"), SandboxFile("tests/check.txt", "expected")),
        )

    def test_default_policy_denies_without_materializing_or_calling_backend(self):
        backend = RecordingBackend()
        report = SandboxService(backend).run(self._request())

        self.assertEqual(report.status, "denied")
        self.assertIsNone(backend.workspace)
        self.assertIn("execution is disabled", report.detail)
        self.assertNotIn("workspace", format_sandbox_report(report).casefold())

    def test_injected_backend_receives_only_bounded_temporary_workspace(self):
        backend = RecordingBackend()
        report = SandboxService(backend).run(self._request(), policy=SandboxPolicy(execution_allowed=True, timeout_seconds=5))

        self.assertEqual(report.status, "completed")
        self.assertEqual(report.exit_code, 0)
        self.assertEqual(backend.files, {"src/main.rs": "fn main() {}", "tests/check.txt": "expected"})
        self.assertFalse(backend.policy.network_allowed)
        self.assertFalse(backend.workspace.exists())
        self.assertNotIn(str(backend.workspace), format_sandbox_report(report))

    def test_unavailable_backend_denies_before_materialization_even_when_requested(self):
        class UnavailableBackend(RecordingBackend):
            available = False

            def run(self, request, workspace, policy, *, stdout, stderr):
                raise AssertionError("unavailable backend must not receive a workspace")

        report = SandboxService(UnavailableBackend()).run(
            self._request(), policy=SandboxPolicy(execution_allowed=True),
        )

        self.assertEqual(report.status, "denied")
        self.assertIn("No isolated sandbox backend", report.detail)

    def test_utf8_bytes_and_windows_unsafe_paths_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "UTF-8 bytes"):
            SandboxFile("emoji.txt", "🙂" * 20_000)
        for path in ("CON.txt", "folder/NUL", "folder/name:stream", "folder/name. ", "folder//name"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    SandboxFile(path, "safe")

    def test_portable_case_unicode_and_file_directory_collisions_are_rejected(self):
        for paths in (
            ("Readme.txt", "README.TXT"),
            ("src", "src/main.py"),
            ("SRC/main.py", "src"),
        ):
            with self.subTest(paths=paths), self.assertRaisesRegex(ValueError, "unique|collision"):
                SandboxRequest(
                    "SB-collision", "murr", "python_tests", "Reject ambiguous trees.",
                    tuple(SandboxFile(path, "safe") for path in paths),
                )
        with self.assertRaisesRegex(ValueError, "canonical Unicode"):
            SandboxFile("cafe\u0301.txt", "safe")

    def test_invalid_paths_policy_and_input_limits_are_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError, "traversal"):
            SandboxFile("../outside.txt", "bad")
        with self.assertRaisesRegex(ValueError, "POSIX separators"):
            SandboxFile("src\\main.rs", "bad")
        with self.assertRaisesRegex(ValueError, "network access"):
            SandboxPolicy(network_allowed=True)

        backend = RecordingBackend()
        with self.assertRaisesRegex(ValueError, "file limit"):
            SandboxService(backend).run(self._request(), policy=SandboxPolicy(execution_allowed=True, max_files=1))
        self.assertIsNone(backend.workspace)

    def test_backend_errors_and_output_are_bounded_in_a_report(self):
        class BrokenBackend:
            name = "broken"
            available = True

            def supports_policy(self, policy):
                return True

            def run(self, request, workspace, policy, *, stdout, stderr):
                raise RuntimeError("secret=must-not-leak")

        report = SandboxService(BrokenBackend()).run(
            self._request(), policy=SandboxPolicy(execution_allowed=True),
        )
        self.assertEqual(report.status, "failed")
        self.assertIn("RuntimeError", report.detail)
        self.assertNotIn("secret=", report.detail)

        noisy = RecordingBackend(SandboxBackendResult("failed", stdout="x" * 200, stderr="y" * 200))
        bounded = SandboxService(noisy).run(
            self._request(), policy=SandboxPolicy(execution_allowed=True, max_output_characters=100),
        )
        self.assertTrue(bounded.stdout.endswith("[output truncated]"))
        self.assertTrue(bounded.stderr.endswith("[output truncated]"))
        self.assertLessEqual(len(bounded.stdout.encode("utf-8")), 100)
        self.assertLessEqual(len(bounded.stderr.encode("utf-8")), 100)

    def test_backend_must_explicitly_claim_availability_and_policy_support(self):
        class AmbiguousBackend:
            name = "ambiguous"

            def run(self, request, workspace, policy):
                raise AssertionError("ambiguous backend must not receive files")

        report = SandboxService(AmbiguousBackend()).run(
            self._request(), policy=SandboxPolicy(execution_allowed=True),
        )
        self.assertEqual(report.status, "denied")
        self.assertIn("No isolated sandbox backend", report.detail)

        class NoPolicyBackend(RecordingBackend):
            supports_policy = None

        backend = NoPolicyBackend()
        report = SandboxService(backend).run(
            self._request(), policy=SandboxPolicy(execution_allowed=True),
        )
        self.assertEqual(report.status, "denied")
        self.assertIsNone(backend.workspace)

        class BrokenPolicyBackend(RecordingBackend):
            def supports_policy(self, policy):
                raise RuntimeError("secret policy detail")

        backend = BrokenPolicyBackend()
        report = SandboxService(backend).run(
            self._request(), policy=SandboxPolicy(execution_allowed=True),
        )
        self.assertEqual(report.status, "denied")
        self.assertIsNone(backend.workspace)
        self.assertNotIn("secret", format_sandbox_report(report))

    def test_materialization_and_cleanup_faults_are_safe_bounded_failures(self):
        backend = RecordingBackend()
        with patch("pipeline.sandbox.Path.write_text", side_effect=OSError("secret host path")):
            report = SandboxService(backend).run(
                self._request(), policy=SandboxPolicy(execution_allowed=True),
            )
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.detail, "Sandbox materialization error: OSError")
        self.assertIsNone(backend.workspace)
        self.assertNotIn("secret", format_sandbox_report(report))

    def test_output_collector_caps_chunked_utf8_flood_and_marker_within_limit(self):
        collector = SandboxOutputCollector(64)
        for _ in range(100):
            collector.write("🦊" * 20)
        rendered = collector.text()
        self.assertTrue(collector.truncated)
        self.assertTrue(rendered.endswith("[output truncated]"))
        self.assertLessEqual(len(rendered.encode("utf-8")), 64)
        with self.assertRaisesRegex(ValueError, "valid UTF-8"):
            SandboxOutputCollector(64).write("\ud800")

        real_temporary_directory = tempfile.TemporaryDirectory

        class CleanupFault:
            def __init__(self, *args, **kwargs):
                self._inner = real_temporary_directory(*args, **kwargs)
                self.name = self._inner.name

            def cleanup(self):
                self._inner.cleanup()
                raise OSError("secret cleanup path")

        with patch("pipeline.sandbox.tempfile.TemporaryDirectory", CleanupFault):
            report = SandboxService(RecordingBackend()).run(
                self._request(), policy=SandboxPolicy(execution_allowed=True),
            )
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.detail, "Sandbox cleanup error: OSError")
        self.assertNotIn("secret", format_sandbox_report(report))


if __name__ == "__main__":
    unittest.main()
