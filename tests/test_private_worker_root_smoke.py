"""Only fake startup diagnostics; never run namespaces/syscalls at discovery."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location("root_smoke_fixture", Path(__file__).resolve().parents[1] / "scripts/private_worker_root_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class RootSmokeDiagnosticTests(unittest.TestCase):
    def test_capability_abi_needs_no_import_or_library_file_after_setup(self):
        class FakeLibrary:
            def prctl(self, *_args): return 0
            def syscall(self, *_args): return 0
        status = "\n".join(f"{key}:0" for key in ("CapEff", "CapPrm", "CapInh", "CapBnd", "CapAmb"))
        status += "\nNoNewPrivs:1"
        with patch.object(smoke.Path, "read_text", return_value=status), \
             patch("builtins.__import__", side_effect=AssertionError("unexpected lazy import")), \
             patch("builtins.open", side_effect=AssertionError("unexpected library open")):
            smoke.drop_privileges(FakeLibrary())

    def test_unexpected_exception_reports_only_phase_and_class(self):
        control = Mock()
        with patch.object(smoke.socket, "socket", return_value=control), \
             patch.object(smoke, "need", side_effect=FileNotFoundError("PRIVATE")):
            with self.assertRaises(FileNotFoundError):
                smoke.stage({}, 9)
        self.assertEqual([call.args[0] for call in control.sendall.call_args_list],
                         [b"boot", b"STOP:initial:FileNotFoundError"])
        control.close.assert_called_once()

    def test_unsafe_refusal_prose_is_not_disclosed(self):
        control = Mock()
        with patch.object(smoke.socket, "socket", return_value=control), \
             patch.object(smoke, "need", side_effect=smoke.Refusal("PRIVATE CONTENT")):
            with self.assertRaises(smoke.Refusal):
                smoke.stage({}, 9)
        self.assertEqual([call.args[0] for call in control.sendall.call_args_list],
                         [b"boot", b"STOP:initial:native_error"])


class RootSmokeSupervisionTests(unittest.TestCase):
    def run_supervisor(self, replies):
        parent, child, process = Mock(), Mock(), Mock()
        parent.__enter__ = Mock(return_value=parent)
        parent.__exit__ = Mock(return_value=False)
        child.__enter__ = Mock(return_value=child)
        child.__exit__ = Mock(return_value=False)
        child.fileno.return_value = 8
        process.pid = 100
        process.poll.return_value = None
        parent.recv.side_effect = replies
        events = []
        parent.sendall.side_effect = lambda data: events.append(("send", data))
        captures = iter(((101, 21), (102, 22)))
        def capture(pid):
            events.append(("capture", pid))
            return next(captures)
        with patch.object(smoke.socket, "socketpair", return_value=(parent, child)), \
             patch.object(smoke.subprocess, "Popen", return_value=process), \
             patch.object(smoke, "capture_child", side_effect=capture), \
             patch.object(smoke.select, "select", side_effect=lambda *_a: ([], [], [])
                          if not process.wait.called else ([21, 22], [], [])), \
             patch.object(smoke.os, "close") as close:
            failure = None
            try:
                smoke.supervise({})
            except BaseException as error:
                failure = error
        process.kill.assert_called_once()
        process.wait.assert_called_once_with(timeout=2)
        return events, close, failure

    def test_pins_worker_and_descendant_before_each_release(self):
        events, close, error = self.run_supervisor([b"boot", b"child", b"ready"])
        self.assertIsNone(error)
        self.assertEqual(events, [("capture", 100), ("send", b"go"),
                                  ("capture", 101), ("send", b"child-go")])
        self.assertEqual([c.args[0] for c in close.call_args_list], [21, 22])

    def test_startup_failure_still_waits_for_captured_worker(self):
        events, close, error = self.run_supervisor([b"boot", b"STOP:private_root:Refusal"])
        self.assertIsInstance(error, smoke.Refusal)
        self.assertEqual(events, [("capture", 100), ("send", b"go")])
        close.assert_called_once_with(21)

    def test_interrupt_during_child_phase_preserves_both_cleanup_handles(self):
        _, close, error = self.run_supervisor([b"boot", b"child", KeyboardInterrupt()])
        self.assertIsInstance(error, KeyboardInterrupt)
        self.assertEqual([c.args[0] for c in close.call_args_list], [21, 22])

    def test_reused_child_identity_closes_unaccepted_handle(self):
        with patch.object(smoke, "only_child", side_effect=[101, 103]), \
             patch.object(smoke.Path, "read_text", return_value="101 (fixture) " + "0 " * 20), \
             patch.object(smoke.os, "pidfd_open", return_value=21), \
             patch.object(smoke.os, "close") as close:
            with self.assertRaises(smoke.Refusal):
                smoke.capture_child(100)
        close.assert_called_once_with(21)

    def test_malformed_startup_diagnostic_is_not_reflected(self):
        parent = Mock()
        parent.recv.return_value = b"STOP:private_root:PRIVATE CONTENT"
        with self.assertRaisesRegex(smoke.Refusal, "^startup_diagnostic_invalid$"):
            smoke.receive_phase(parent, b"ready")
