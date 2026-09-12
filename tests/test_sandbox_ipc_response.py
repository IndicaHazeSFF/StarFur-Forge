import json
from pathlib import Path
import struct
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_ipc import SupervisorIPCEnrollment, sign_supervisor_ipc_request
from pipeline.sandbox_ipc_response import (
    AuthenticatedSupervisorIPCResponseReceiver,
    SupervisorIPCResponse,
    SupervisorIPCResponseAuthenticator,
    SupervisorIPCResponseError,
    SupervisorIPCServiceIdentity,
    frame_supervisor_ipc_response,
    sign_supervisor_ipc_response,
)
from pipeline.sandbox_supervisor import (
    SupervisorCancelReceipt,
    SupervisorCompletion,
    SupervisorRunStatus,
)
from pipeline.tool_contracts import ToolResult


CLIENT_SECRET = b"c" * 32
SERVICE_SECRET = b"r" * 32


def enrollment():
    return SupervisorIPCEnrollment(
        1, "SE-response-001", "local.owner", "starfur.sandbox.supervisor",
        "supervisor-v1", "local_authenticated_ipc", "transport-v1",
        "SK-client-001", ("launch", "query", "cancel"), 900.0, 2000.0,
    )


def identity(**overrides):
    values = {
        "schema_version": 1,
        "enrollment_id": "SE-response-001",
        "service_id": "starfur.sandbox.supervisor",
        "service_revision": "supervisor-v1",
        "transport_revision": "transport-v1",
        "response_key_id": "SK-service-001",
        "created_at": 900.0,
        "expires_at": 2000.0,
    }
    values.update(overrides)
    return SupervisorIPCServiceIdentity(**values)


def request(*, operation="query", number=1):
    return sign_supervisor_ipc_request(
        enrollment(), CLIENT_SECRET,
        session_instance_id="session-001", operation=operation,
        invocation_id=f"TI-response-{number:03d}",
        worker_generation=f"TW-worker-{number:03d}",
        binding_fingerprint=f"{number:x}".rjust(64, "0"),
        issued_at=1000.0, expires_at=1010.0,
        request_id=f"SI-request-{number:03d}", nonce=f"SN-{number:016d}",
    )


def status(req):
    return SupervisorRunStatus(
        1, req.invocation_id, req.binding_fingerprint, req.worker_generation,
        "running",
    )


def response(req=None, payload=None, *, secret=SERVICE_SECRET, **overrides):
    req = req or request()
    values = {
        "issued_at": 1001.0,
        "expires_at": 1009.0,
        "response_id": "SO-response-001",
        "nonce": "SR-1234567890abcdef",
    }
    values.update(overrides)
    return sign_supervisor_ipc_response(
        identity(), secret, req, payload or status(req), **values,
    )


def verifier(**kwargs):
    return SupervisorIPCResponseAuthenticator(
        identity(), SERVICE_SECRET, clock=lambda: 1002.0, **kwargs,
    )


class SandboxIPCResponseTests(unittest.TestCase):
    def test_status_response_round_trips_and_authenticates_exact_request(self):
        req = request()
        value = response(req)
        decoded = SupervisorIPCResponse.from_json_bytes(value.to_json_bytes())
        self.assertEqual(value, decoded)
        accepted = verifier().authenticate(decoded, request=req)
        self.assertEqual("running", accepted.response.payload.state)
        public = repr(accepted.public_dict())
        self.assertNotIn("authentication_tag", public)
        self.assertNotIn("local.owner", public)

    def test_completion_carries_strict_bounded_result_and_keeps_it_private_publicly(self):
        req = request(operation="launch")
        result = ToolResult(
            1, req.invocation_id, "sandbox.run", 1, "completed", 0,
            "private output", "", None,
        )
        completion = SupervisorCompletion(
            1, req.invocation_id, "sandbox.run", 1, req.binding_fingerprint,
            "policy-v1", req.worker_generation, "completed",
            "verified_stopped", result,
        )
        value = response(req, completion)
        decoded = SupervisorIPCResponse.from_json_bytes(value.to_json_bytes())
        self.assertEqual("private output", decoded.payload.result.stdout)
        self.assertNotIn("private output", repr(decoded.public_dict()))
        self.assertEqual(
            "completed", verifier().authenticate(decoded, request=req).response.payload.outcome,
        )

    def test_cancel_receipt_is_allowed_only_for_cancel_request(self):
        req = request(operation="cancel")
        receipt = SupervisorCancelReceipt(
            1, req.invocation_id, req.worker_generation, "requested",
        )
        self.assertEqual("cancel_receipt", response(req, receipt).response_kind)
        with self.assertRaisesRegex(ValueError, "not valid for operation"):
            response(request(operation="query"), receipt)

    def test_wrong_key_modified_response_and_wrong_request_fail_closed(self):
        req = request()
        bad_key = response(req, secret=b"x" * 32)
        with self.assertRaisesRegex(SupervisorIPCResponseError, "authentication"):
            verifier().authenticate(bad_key, request=req)

        value = response(req)
        altered = SupervisorIPCResponse(**{**value.__dict__, "service_revision": "supervisor-v2"})
        with self.assertRaises(SupervisorIPCResponseError):
            verifier().authenticate(altered, request=req)
        with self.assertRaisesRegex(SupervisorIPCResponseError, "request binding"):
            verifier().authenticate(value, request=request(number=2))
        with self.assertRaisesRegex(ValueError, "enrollment"):
            sign_supervisor_ipc_response(
                identity(enrollment_id="SE-other-001"), SERVICE_SECRET, req,
                status(req), issued_at=1001.0, expires_at=1009.0,
            )
        with self.assertRaisesRegex(ValueError, "key identities"):
            sign_supervisor_ipc_response(
                identity(response_key_id=req.key_id), SERVICE_SECRET, req,
                status(req), issued_at=1001.0, expires_at=1009.0,
            )

    def test_response_id_and_nonce_are_single_use_and_capacity_fails_closed(self):
        req = request()
        check = verifier(maximum_seen_responses=2)
        check.authenticate(response(req), request=req)
        for overrides in (
            {"nonce": "SR-abcdef1234567890"},
            {"response_id": "SO-response-002"},
        ):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(
                SupervisorIPCResponseError, "already used",
            ):
                check.authenticate(response(req, **overrides), request=req)
        second = response(
            req, response_id="SO-response-002", nonce="SR-abcdef1234567890",
        )
        check.authenticate(second, request=req)
        third = response(
            req, response_id="SO-response-003", nonce="SR-fedcba0987654321",
        )
        with self.assertRaisesRegex(SupervisorIPCResponseError, "capacity"):
            check.authenticate(third, request=req)

    def test_strict_json_rejects_unknown_duplicate_and_malformed_payload(self):
        encoded = response().to_json_bytes()
        value = json.loads(encoded)
        value["extra"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            SupervisorIPCResponse.from_json_bytes(json.dumps(value).encode())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            SupervisorIPCResponse.from_json_bytes(
                b'{"schema_version":1,"schema_version":1}',
            )
        value = json.loads(encoded)
        value["payload"]["extra"] = True
        with self.assertRaisesRegex(ValueError, "payload"):
            SupervisorIPCResponse.from_json_bytes(json.dumps(value).encode())

    def test_response_framing_handles_fragmentation_and_partial_disconnect(self):
        req = request()
        framed = frame_supervisor_ipc_response(response(req))
        receiver = AuthenticatedSupervisorIPCResponseReceiver(
            verifier(), request=req,
        )
        self.assertEqual((), receiver.feed(framed[:7]))
        accepted = receiver.feed(framed[7:])
        self.assertEqual(1, len(accepted))
        receiver.close()

        partial = AuthenticatedSupervisorIPCResponseReceiver(verifier(), request=req)
        partial.feed(framed[:-1])
        with self.assertRaisesRegex(SupervisorIPCResponseError, "partial"):
            partial.close()

    def test_invalid_length_and_authentication_poison_response_connection(self):
        req = request()
        for framed in (
            struct.pack(">I", 0),
            struct.pack(">I", 24 * 1024 + 1),
            frame_supervisor_ipc_response(response(req, secret=b"x" * 32)),
        ):
            with self.subTest(prefix=framed[:4]):
                receiver = AuthenticatedSupervisorIPCResponseReceiver(
                    verifier(), request=req,
                )
                with self.assertRaises(SupervisorIPCResponseError):
                    receiver.feed(framed)
                self.assertTrue(receiver.failed)


if __name__ == "__main__":
    unittest.main()
