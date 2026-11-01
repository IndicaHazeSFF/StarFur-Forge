"""Provider-free fake transport coverage; no real sockets/services."""
from dataclasses import FrozenInstanceError
import json
import unittest
from unittest.mock import Mock, patch

from pipeline.document_job_locality import LocalAnnotationTarget
from pipeline.document_job_model import MAX_LOCAL_MODEL_LISTING_BYTES
from pipeline.document_job_model_request import ModelListingRequest
from pipeline.document_job_model_acquisition import ModelListingAcquirer, ModelListingAcquisitionError


def listing(**changes):
    item = dict(name="fixture", model="fixture", digest="a" * 64, size=1, details={"format": "gguf"})
    item.update(changes)
    return json.dumps({"models": [item]}).encode()


class Response:
    def __init__(self, data=None):
        self.status = 200
        self.headers = {"Content-Type": "application/json"}
        self.data = listing() if data is None else data
        self.offset = 0
        self.closed = False
        self.hook = lambda: None
        self.close_hook = lambda: None
    def getheader(self, key, default=None):
        return self.headers.get(key, default)
    def read1(self, size):
        self.hook()
        result = self.data[self.offset:self.offset + size]
        self.offset += len(result)
        return result
    def close(self):
        self.closed = True
        self.close_hook()


class Connection:
    def __init__(self):
        self.response = Response()
        self.sock = Mock()
        self.request = Mock()
        self.connect = Mock()
        self.close = Mock()
    def getresponse(self):
        return self.response


class ModelListingAcquisitionTests(unittest.TestCase):
    def setUp(self):
        guard = patch("socket.socket", side_effect=AssertionError("no actual sockets"))
        guard.start()
        self.addCleanup(guard.stop)
        self.request = ModelListingRequest(LocalAnnotationTarget("http://127.0.0.1:11434"), "fixture")
        self.conn = Connection()
        self.factory = Mock(return_value=self.conn)
        self.now = 0.0
        self.adapter = ModelListingAcquirer(self.request, _connection_factory=self.factory, _clock=lambda: self.now)

    def test_construction_is_inert_immutable_and_redacted(self):
        self.factory.assert_not_called()
        self.assertNotIn("fixture", repr(self.adapter))
        with self.assertRaises(FrozenInstanceError):
            self.adapter._request = None
        with self.assertRaises(ModelListingAcquisitionError):
            ModelListingAcquirer(None)

    def test_exact_transport_ignores_environment(self):
        with patch.dict("os.environ", {"HTTP_PROXY": "http://remote.invalid", "OLLAMA_HOST": "https://remote.invalid", "OLLAMA_API_KEY": "secret"}):
            self.assertEqual(self.adapter.inspect().digest, "a" * 64)
        self.factory.assert_called_once_with("127.0.0.1", 11434, timeout=10.0)
        self.conn.request.assert_called_once_with("GET", "/api/tags", headers={
            "Accept": "application/json", "Accept-Encoding": "identity", "Connection": "close"})
        self.assertTrue(self.conn.response.closed)
        self.conn.close.assert_called_once()

    def test_ipv6_target_and_no_untrusted_constructor_controls(self):
        request = ModelListingRequest(LocalAnnotationTarget("http://[::1]:11435"), "fixture")
        ModelListingAcquirer(request, _connection_factory=self.factory).inspect()
        self.assertEqual(self.factory.call_args.args, ("::1", 11435))
        for option in ({"_clock": False}, {"_connection_factory": False}):
            with self.assertRaises(ModelListingAcquisitionError):
                ModelListingAcquirer(self.request, **option)

    def test_invalid_status_headers_and_schema_are_content_free(self):
        for status, headers, data in ((302, {}, listing()), (200, {"Content-Type": "text/html"}, listing()),
                                      (200, {"Content-Encoding": "gzip"}, listing()),
                                      (200, {}, b"private"), (200, {}, listing(model="other")),
                                      (200, {}, listing(remote_host="remote.invalid"))):
            self.conn.response = Response(data)
            self.conn.response.status = status
            self.conn.response.headers.update(headers)
            with self.assertRaises(ModelListingAcquisitionError) as error:
                self.adapter.inspect()
            self.assertEqual(str(error.exception), "model listing acquisition failed safely")
            self.assertTrue(self.conn.response.closed)

    def test_exact_byte_limit_and_oversize(self):
        data = listing()
        self.conn.response = Response(data + b" " * (MAX_LOCAL_MODEL_LISTING_BYTES - len(data)))
        self.assertEqual(self.adapter.inspect().model, "fixture")
        self.conn.response = Response(b" " * (MAX_LOCAL_MODEL_LISTING_BYTES + 1))
        with self.assertRaises(ModelListingAcquisitionError):
            self.adapter.inspect()

    def test_total_deadline_trickle_and_decreasing_timeouts(self):
        self.conn.response.hook = lambda: setattr(self, "now", self.now + 1)
        self.adapter.inspect()
        values = [call.args[0] for call in self.conn.sock.settimeout.call_args_list]
        self.assertEqual(values, sorted(values, reverse=True))
        self.now = 0
        self.conn.response = Response()
        self.conn.response.hook = lambda: setattr(self, "now", self.now + 5)
        with self.assertRaises(ModelListingAcquisitionError):
            self.adapter.inspect()

    def test_factory_delay_updates_connect_deadline(self):
        def factory(*args, **kwargs):
            self.now = 4
            return self.conn
        ModelListingAcquirer(self.request, _connection_factory=factory, _clock=lambda: self.now).inspect()
        self.assertEqual(self.conn.timeout, 6)

    def test_invalid_clock_and_connection_failure(self):
        for values in ((float("nan"),), (True,), (1, 0), (1, 11)):
            with self.assertRaises(ModelListingAcquisitionError):
                ModelListingAcquirer(self.request, _connection_factory=self.factory, _clock=Mock(side_effect=values)).inspect()
        self.conn.connect.side_effect = OSError("private")
        with self.assertRaises(ModelListingAcquisitionError):
            self.adapter.inspect()
        self.conn.close.assert_called()

    def test_interruption_preserved_and_both_resources_closed(self):
        self.conn.response.hook = Mock(side_effect=KeyboardInterrupt)
        self.conn.response.close_hook = Mock(side_effect=OSError("private"))
        with self.assertRaises(KeyboardInterrupt):
            self.adapter.inspect()
        self.assertTrue(self.conn.response.closed)
        self.conn.close.assert_called_once()

    def test_cleanup_error_discards_success(self):
        self.conn.close.side_effect = OSError("private")
        with self.assertRaisesRegex(ModelListingAcquisitionError, "cleanup failed safely"):
            self.adapter.inspect()
