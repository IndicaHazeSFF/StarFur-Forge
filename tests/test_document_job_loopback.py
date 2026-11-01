"""Fake-transport private loopback adapter checks; no actual sockets/services."""

import io
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pipeline.document_job_locality import AnnotationLocalityEvidence, LocalAnnotationTarget
from pipeline.document_job_loopback import AnnotationLoopbackError, LoopbackAnnotationProvider


class FakeResponse:
    status = 200
    def __init__(self):
        self.headers = {"Content-Type": "application/json"}
        self.body = json.dumps({"model": "fixture-model", "done": True, "done_reason": "stop", "message": {
            "content": '{"proposals": []}', "thinking": "PRIVATE_REASONING"}}).encode()
        self.read_limit = None
        self.offset = 0
        self.closed = False
    def getheader(self, key, default=None):
        return self.headers.get(key, default)
    def read1(self, limit):
        if self.read_limit is None:
            self.read_limit = limit
        part = self.body[self.offset:self.offset + limit]
        self.offset += len(part)
        return part
    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.response = FakeResponse()
        self.closed = False
        self.sock = mock.Mock()
    def connect(self):
        pass
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
    def getresponse(self):
        self.response.offset = 0
        self.response.read_limit = None
        return self.response
    def close(self):
        self.closed = True


class AnnotationLoopbackContracts(unittest.TestCase):
    def setUp(self):
        self.target = LocalAnnotationTarget("http://127.0.0.1:11434")
        self.evidence = AnnotationLocalityEvidence(self.target.fingerprint, "fixture-model", "a" * 64, True, True, True)
        self.connection = FakeConnection()
        self.factory = mock.Mock(return_value=self.connection)
        self.provider = LoopbackAnnotationProvider(self.target, "fixture-model", self.evidence, _connection_factory=self.factory)
        self.messages = [{"role": "user", "content": "Synthetic private input."}]
        guard = mock.patch("socket.socket", side_effect=AssertionError("no actual network"))
        guard.start()
        self.addCleanup(guard.stop)

    def call(self, **kwargs):
        return self.provider.complete(self.messages, model="fixture-model", **kwargs)

    def test_deadline_crossed_during_json_parsing_discards_completion(self):
        now = 0
        parse = json.loads

        def delayed_parse(*args, **kwargs):
            nonlocal now
            result = parse(*args, **kwargs)
            now = 30
            return result

        with mock.patch("pipeline.document_job_loopback.time.monotonic", side_effect=lambda: now), \
                mock.patch("pipeline.document_job_loopback.json.loads", side_effect=delayed_parse):
            with self.assertRaisesRegex(AnnotationLoopbackError, "request failed safely"):
                self.call()
        self.assertTrue(self.connection.response.closed)
        self.assertTrue(self.connection.closed)

    def test_missing_locality_evidence_denies_before_connection(self):
        with self.assertRaises(AnnotationLoopbackError):
            LoopbackAnnotationProvider(self.target, "fixture-model", _connection_factory=self.factory)
        self.factory.assert_not_called()

    def test_target_and_transport_configuration_cannot_be_reassigned(self):
        for name, value in (("_target", LocalAnnotationTarget("http://127.0.0.1:11435")),
                            ("_model", "different"), ("_evidence", None), ("_connection_factory", self.factory)):
            with self.assertRaises(FrozenInstanceError):
                setattr(self.provider, name, value)
        self.assertNotIn("fixture-model", repr(self.provider))
        self.factory.assert_not_called()

    def test_ambient_host_proxy_and_credentials_never_change_exact_request(self):
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": "https://remote.invalid", "HTTP_PROXY": "http://remote.invalid",
                                         "HTTPS_PROXY": "http://remote.invalid", "OLLAMA_API_KEY": "SECRET_KEY"}):
            self.assertEqual(self.call().content, '{"proposals": []}')
        self.factory.assert_called_once_with("127.0.0.1", 11434, timeout=30)
        args, kwargs = self.connection.calls[0]
        self.assertEqual(args, ("POST", "/api/chat"))
        self.assertNotIn("SECRET_KEY", repr(kwargs))
        self.assertNotIn("Authorization", kwargs["headers"])
        self.assertNotIn("Cookie", kwargs["headers"])
        self.assertTrue(self.connection.closed)

    def test_redirect_and_error_never_follow_or_expose_payload(self):
        for status in (302, 307, 401, 500):
            self.connection.response.status = status
            with self.assertRaises(AnnotationLoopbackError) as error:
                self.call()
            self.assertNotIn("PRIVATE_REASONING", str(error.exception))
            self.assertIsNone(self.connection.response.read_limit)
        self.assertEqual(len(self.connection.calls), 4)

    def test_strict_bounded_json_and_finish_metadata(self):
        self.assertEqual(self.call().finish_reason, "stop")
        self.assertEqual(self.connection.response.read_limit, 16384)
        for body in (b'{"done":true,"done":true}', b'{}', b'{"done":true,"error":"private server error"}',
                     b'not JSON', b'\xff', b'{"done":true,"message":{"content":NaN}}', b'x' * (256 * 1024 + 1)):
            self.connection.response.body = body
            with self.assertRaises(AnnotationLoopbackError):
                self.call()
        self.connection.response.body = b'{"model":"fixture-model","done":true,"done_reason":"length","message":{"content":"partial","thinking":"SECRET"}}'
        result = self.call()
        self.assertEqual(result.finish_reason, "length")
        self.assertNotIn("SECRET", repr(result))

    def test_unsupported_call_controls_deny_before_connection(self):
        for kwargs in ({"stream": True}, {"thinking": 1}, {"options": {"host": "remote"}},
                       {"options": {"temperature": float("inf")}}, {"keep_alive_seconds": -1}):
            with self.assertRaises(AnnotationLoopbackError):
                self.call(**kwargs)
        with self.assertRaises(AnnotationLoopbackError):
            self.provider.complete(self.messages, model="other-model")
        self.factory.assert_not_called()

    def test_unbounded_generation_controls_deny_before_connection(self):
        for options in ({"num_predict": -1}, {"num_predict": 1025}, {"num_predict": True}, {"num_ctx": 32769}):
            with self.assertRaises(AnnotationLoopbackError):
                self.call(options=options)
        self.factory.assert_not_called()

    def test_compression_and_timeout_fail_closed(self):
        self.connection.response.headers["Content-Encoding"] = "gzip"
        with self.assertRaises(AnnotationLoopbackError):
            self.call()
        self.connection.response.headers.pop("Content-Encoding")
        with mock.patch("pipeline.document_job_loopback.time.monotonic", side_effect=[0, 31]):
            with self.assertRaises(AnnotationLoopbackError):
                self.call()
        self.assertTrue(self.connection.closed)

    def test_ctrl_c_closes_without_claiming_remote_stop(self):
        with mock.patch.object(self.connection, "getresponse", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.call()
        self.assertTrue(self.connection.closed)

    def test_trickled_body_cannot_extend_acceptance_deadline(self):
        self.connection.response.body = b"x" * 20000
        with mock.patch("pipeline.document_job_loopback.time.monotonic", side_effect=[0, 1, 2, 3, 31]):
            with self.assertRaises(AnnotationLoopbackError):
                self.call()
        self.assertEqual(self.connection.response.offset, 16384)
        self.assertTrue(self.connection.response.closed)
        self.assertTrue(self.connection.closed)

    def test_cleanup_failure_or_wrong_returned_model_never_returns_success(self):
        with mock.patch.object(self.connection.response, "close", side_effect=OSError("private cleanup detail")):
            with self.assertRaises(AnnotationLoopbackError) as error:
                self.call()
        self.assertNotIn("private cleanup detail", str(error.exception))
        self.assertTrue(self.connection.closed)
        self.connection.response.body = b'{"model":"other","done":true,"message":{"content":"private"}}'
        with self.assertRaises(AnnotationLoopbackError):
            self.call()


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows support")
class AnnotationLoopbackIntegrationSmokes(unittest.TestCase):
    def setUp(self):
        from tests.document_job_fixtures import make_application
        from pipeline.document_job_store import AnnotationJobStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / "jobs"
        root.mkdir(mode=0o700)
        self.store = AnnotationJobStore(root)
        self.addCleanup(self.store.close)
        self.connections = []
        self.hook = None
        def connection(*_args, **_kwargs):
            result = FakeConnection()
            if self.hook:
                self.hook(result)
            self.connections.append(result)
            return result
        self.factory = mock.Mock(side_effect=connection)
        target = LocalAnnotationTarget("http://127.0.0.1:11434")
        evidence = AnnotationLocalityEvidence(target.fingerprint, "fixture-model", "a" * 64, True, True, True)
        provider = LoopbackAnnotationProvider(target, "fixture-model", evidence, _connection_factory=self.factory)
        self.app, self.session, _ = make_application(provider)
        self.job = self.store.submit("Synthetic fixture prefers tea.", "fixture.md")
        for name in ("pipeline.db.connect", "socket.socket"):
            guard = mock.patch(name, side_effect=AssertionError("no canonical data or actual socket"))
            guard.start()
            self.addCleanup(guard.stop)

    def processor(self):
        from pipeline.document_job_processor import AnnotationJobProcessor
        processor = AnnotationJobProcessor(self.store, self.app.bind_annotation_job_runtime())
        return processor, processor.start(self.job.job_id)

    def test_01_application_checkpoint_uses_only_sealed_fake_transport(self):
        processor, run = self.processor()
        self.assertEqual(processor.step(run).status, "checkpointed")
        self.assertEqual(processor.finish(run).status, "completed")
        self.assertEqual(self.store.runtime_evidence(self.job.job_id).bound_chunks, 1)
        self.assertEqual(self.store.progress(self.job.job_id).candidate_count, 0)
        self.assertEqual(self.app._workload_gate.active_count("ollama"), 0)
        self.factory.assert_called_once_with("127.0.0.1", 11434, timeout=30)

    def test_02_focus_and_capacity_defer_before_connect_factory(self):
        processor, run = self.processor()
        self.session.focus_mode_set(True)
        self.assertEqual(processor.step(run).reason, "focus_mode")
        self.session.focus_mode_set(False)
        held = self.app._workload_gate.try_acquire("ollama", 1).lease
        try:
            self.assertEqual(processor.step(run).reason, "provider_capacity_busy")
            self.factory.assert_not_called()
        finally:
            self.app._workload_gate.release(held)
        self.assertEqual(processor.step(run).status, "checkpointed")

    def test_03_core_existing_retry_cannot_redirect_or_publish_invalid_candidates(self):
        def redirect(connection):
            connection.response.status = 302
        self.hook = redirect
        processor, run = self.processor()
        self.assertEqual(processor.step(run).status, "checkpointed")
        self.assertEqual(processor.finish(run).status, "completed")
        result = self.store.read_result(self.job.job_id)
        self.assertEqual((len(result.candidates), len(result.failures)), (0, 1))
        self.assertEqual(self.factory.call_count, 3)  # existing Core bound, no adapter retry
        self.assertTrue(all(connection.closed and connection.response.closed for connection in self.connections))
        self.assertEqual(self.app._workload_gate.active_count("ollama"), 0)

    def test_04_ctrl_c_fences_and_closes_without_saved_output(self):
        def interrupt(connection):
            connection.getresponse = mock.Mock(side_effect=KeyboardInterrupt)
        self.hook = interrupt
        processor, run = self.processor()
        with self.assertRaises(KeyboardInterrupt):
            processor.step(run)
        progress = self.store.progress(self.job.job_id)
        self.assertEqual(progress.metadata.state, "interrupted")
        self.assertEqual(progress.checkpointed_chunks, 0)
        self.assertTrue(self.connections[0].closed)
        self.assertEqual(self.app._workload_gate.active_count("ollama"), 0)


if __name__ == "__main__":
    unittest.main()
