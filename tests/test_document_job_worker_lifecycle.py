"""Provider-free descriptive policy tests; not production replay enforcement."""
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_lifecycle import (
    WorkerLifecycle, WorkerLifecycleError, advance_worker_lifecycle as step, EVENTS,
)


class WorkerLifecycleTests(unittest.TestCase):
    def setUp(self):
        for name in ("socket.socket", "builtins.open", "subprocess.Popen"):
            guard = patch(name, side_effect=AssertionError("no I/O"))
            guard.start(); self.addCleanup(guard.stop)

    def test_success_is_monotone_and_does_not_modify_input(self):
        prepared = WorkerLifecycle()
        active = step(prepared, "dispatch_burned")
        done = step(active, "response_valid")
        self.assertEqual(prepared, WorkerLifecycle("prepared", False))
        self.assertEqual(active, WorkerLifecycle("inflight", True))
        self.assertEqual(done, WorkerLifecycle("completed", True))
        with self.assertRaises(FrozenInstanceError): done.state = "prepared"

    def test_failure_before_disclosure_never_claims_send(self):
        for event in ("cancel", "timeout", "disconnect", "binding_changed", "restart"):
            self.assertEqual(step(WorkerLifecycle(), event), WorkerLifecycle("fenced", False))

    def test_failure_after_burn_keeps_possible_disclosure(self):
        active = step(WorkerLifecycle(), "dispatch_burned")
        for event in ("cancel", "timeout", "disconnect", "binding_changed", "restart", "response_invalid"):
            self.assertEqual(step(active, event), WorkerLifecycle("fenced", True))

    def test_every_terminal_event_refuses_late_response_and_replay(self):
        for current in (WorkerLifecycle("completed", True), WorkerLifecycle("fenced", True), WorkerLifecycle("fenced", False)):
            for event in EVENTS:
                with self.assertRaises(WorkerLifecycleError): step(current, event)

    def test_no_response_before_burn_or_double_burn(self):
        for event in ("response_valid", "response_invalid"):
            with self.assertRaises(WorkerLifecycleError): step(WorkerLifecycle(), event)
        with self.assertRaises(WorkerLifecycleError): step(WorkerLifecycle("inflight", True), "dispatch_burned")

    def test_strict_state_event_contracts_and_no_authority(self):
        for args in (("prepared", True), ("inflight", False), ("completed", False), ([], False), ("fenced", 1)):
            with self.assertRaises(WorkerLifecycleError): WorkerLifecycle(*args)
        for event in (None, [], True, "retry", "resume", "approve", "PRIVATE"):
            with self.assertRaises(WorkerLifecycleError) as caught: step(WorkerLifecycle(), event)
            self.assertNotIn("PRIVATE", str(caught.exception))
        with self.assertRaises(WorkerLifecycleError): step({}, "cancel")
        # Reconstructing descriptions is possible; no saved state is an admission token.
        self.assertEqual(WorkerLifecycle(), WorkerLifecycle())
        self.assertFalse(hasattr(WorkerLifecycle(), "send"))
