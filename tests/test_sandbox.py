import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox import (
    SandboxBackendResult,
    SandboxFile,
    SandboxPolicy,
    SandboxRequest,
    SandboxService,
    format_sandbox_report,
)


class RecordingBackend:
    name = "recording"

    def __init__(self, result=None):
        self.result = result or SandboxBackendResult("completed", stdout="tests passed", exit_code=0)
        self.workspace = None
        self.files = None
        self.policy = None

    def run(self, request, workspace, policy):
        self.workspace = workspace
        self.files = {path.relative_to(workspace).as_posix(): path.read_text(encoding="utf-8") for path in workspace.rglob("*") if path.is_file()}
        self.policy = policy
        return self.result


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
            def run(self, request, workspace, policy):
                raise RuntimeError("backend unavailable")

        report = SandboxService(BrokenBackend()).run(
            self._request(), policy=SandboxPolicy(execution_allowed=True),
        )
        self.assertEqual(report.status, "failed")
        self.assertIn("RuntimeError", report.detail)

        noisy = RecordingBackend(SandboxBackendResult("failed", stdout="x" * 200, stderr="y" * 200))
        bounded = SandboxService(noisy).run(
            self._request(), policy=SandboxPolicy(execution_allowed=True, max_output_characters=100),
        )
        self.assertTrue(bounded.stdout.endswith("[output truncated]"))
        self.assertTrue(bounded.stderr.endswith("[output truncated]"))


if __name__ == "__main__":
    unittest.main()
