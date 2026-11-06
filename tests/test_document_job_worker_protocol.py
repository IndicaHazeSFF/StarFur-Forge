"""Pure synthetic wire tests: no sockets, files, workers or live models."""
from dataclasses import FrozenInstanceError, replace
import json
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_protocol import (
    WorkerRequest, WorkerResult, WorkerProtocolError, encode_request, decode_request,
    encode_result, decode_result, match_result, MAX_REQUEST_BYTES, MAX_RESULT_BYTES,
)


class WorkerProtocolTests(unittest.TestCase):
    def setUp(self):
        for name in ("socket.socket", "builtins.open", "subprocess.Popen"):
            guard = patch(name, side_effect=AssertionError("no I/O"))
            guard.start(); self.addCleanup(guard.stop)
        self.request = WorkerRequest("a" * 32, "b" * 32, "test:v1", "Fixed instruction", "PRIVATE synthetic chunk", 4096, 256)
        self.result = WorkerResult("a" * 32, "b" * 32, "test:v1", "completed", "UNTRUSTED result", "stop", "")

    def test_deterministic_roundtrip_and_no_authority(self):
        raw = encode_request(self.request)
        self.assertEqual(decode_request(raw), self.request)
        self.assertEqual(encode_request(decode_request(raw)), raw)
        self.assertEqual(decode_result(encode_result(self.result)), self.result)
        self.assertIs(match_result(self.request, self.result), self.result)
        self.assertFalse(hasattr(self.request, "consent"))

    def test_repr_and_errors_do_not_disclose(self):
        self.assertNotIn("PRIVATE", repr(self.request))
        self.assertNotIn("UNTRUSTED", repr(self.result))
        try: decode_request(b'{"PRIVATE":"secret"}')
        except WorkerProtocolError as e: self.assertEqual(str(e), "private worker message is invalid")
        else: self.fail("accepted")
        with self.assertRaises(FrozenInstanceError): self.request.model = "other:v1"

    def test_unknown_authority_network_and_payload_fields_deny(self):
        for key in ("url", "path", "executor", "grant", "consent", "headers", "messages", "schema_version"):
            obj = json.loads(encode_request(self.request)); obj[key] = "untrusted"
            with self.assertRaises(WorkerProtocolError): decode_request(json.dumps(obj).encode())

    def test_missing_wrong_version_and_kind_deny(self):
        for key in json.loads(encode_request(self.request)):
            obj = json.loads(encode_request(self.request)); del obj[key]
            with self.assertRaises(WorkerProtocolError): decode_request(json.dumps(obj).encode())
        for key in ("kind", "policy"):
            obj = json.loads(encode_request(self.request)); obj[key] = "future"
            with self.assertRaises(WorkerProtocolError): decode_request(json.dumps(obj).encode())

    def test_malformed_duplicate_nonfinite_deep_and_unicode(self):
        for raw in (b'{}{}', b'[]', b'null', b'\xff', b'{"x":1,"x":2}', b'{"x":NaN}', b'[' * 2000 + b']' * 2000):
            for decoder in (decode_request, decode_result):
                with self.assertRaises(WorkerProtocolError): decoder(raw)
        with self.assertRaises(WorkerProtocolError): replace(self.request, chunk_text="\ud800")

    def test_exact_identity_model_and_integer_bounds(self):
        for field, values in {
            "epoch": ["a", "A" * 32, 1], "dispatch": ["b", None],
            "model": ["test", "test:cloud", "cloud:v1", "https://host/model:v1", "test:v1@digest"],
            "context_size": [True, 1.0, 0, 32769], "max_output_tokens": [True, 1.0, 0, 1025],
            "system_text": ["", " ", None], "chunk_text": ["", "\n", 12],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(WorkerProtocolError):
                    replace(self.request, **{field: value})

    def test_wire_size_includes_json_escaping_and_utf8(self):
        for text in ("x" * MAX_REQUEST_BYTES, "\0" * 12000, "é" * 33000):
            with self.assertRaises(WorkerProtocolError): replace(self.request, chunk_text=text)
        with self.assertRaises(WorkerProtocolError): replace(self.result, content="x" * MAX_RESULT_BYTES)
        for decoder, limit in ((decode_request, MAX_REQUEST_BYTES), (decode_result, MAX_RESULT_BYTES)):
            with self.assertRaises(WorkerProtocolError): decoder(b' ' * (limit + 1))

    def test_closed_result_outcomes_not_quality(self):
        for reason in ("stop", "length"):
            self.assertEqual(replace(self.result, content="", finish_reason=reason).content, "")
        for reason in ("provider_failed", "response_invalid", "interrupted", "unavailable"):
            value = replace(self.result, status="failed", content="", finish_reason="", failure=reason)
            self.assertEqual(decode_result(encode_result(value)), value)
        for changes in ({"failure":"private traceback"}, {"status":"verified"}, {"finish_reason":"other"},
                        {"status":"failed", "failure":"provider_failed"}, {"status":[]}, {"failure":None}):
            with self.assertRaises(WorkerProtocolError): replace(self.result, **changes)

    def test_mismatch_never_correlates_other_attempt_or_model(self):
        for changes in ({"epoch":"c"*32}, {"dispatch":"c"*32}, {"model":"other:v1"}):
            with self.assertRaises(WorkerProtocolError): match_result(self.request, replace(self.result, **changes))
        # Identical bytes still match twice: lifecycle replay prevention is NOT this codec's job.
        match_result(self.request, self.result); match_result(self.request, self.result)

    def test_result_fields_strict_and_wrong_contract_types_deny(self):
        obj = json.loads(encode_result(self.result)); obj["thinking"] = "PRIVATE"
        with self.assertRaises(WorkerProtocolError): decode_result(json.dumps(obj).encode())
        for function, value in ((encode_request, {}), (encode_result, self.request), (decode_request, "{}")):
            with self.assertRaises(WorkerProtocolError): function(value)
        object.__setattr__(self.request, "max_output_tokens", True)
        with self.assertRaises(WorkerProtocolError): encode_request(self.request)
