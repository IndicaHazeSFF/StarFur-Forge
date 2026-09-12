import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_ipc import (
    SupervisorIPCAuthenticationError,
    SupervisorIPCAuthenticator,
    SupervisorIPCEnrollment,
    SupervisorIPCRequest,
    sign_supervisor_ipc_request,
)


SECRET = b"s" * 32


def enrollment(**overrides):
    values = {
        "schema_version": 1,
        "enrollment_id": "SE-local-001",
        "client_principal_id": "local.owner",
        "service_id": "starfur.sandbox.supervisor",
        "service_revision": "supervisor-v1",
        "transport_kind": "local_authenticated_ipc",
        "transport_revision": "transport-v1",
        "key_id": "SK-local-001",
        "allowed_operations": ("launch", "query", "cancel"),
        "created_at": 900.0,
        "expires_at": 2000.0,
    }
    values.update(overrides)
    return SupervisorIPCEnrollment(**values)


def request(enrolled=None, secret=SECRET, **overrides):
    values = {
        "session_instance_id": "session-001",
        "operation": "launch",
        "invocation_id": "TI-ipc-001",
        "worker_generation": "TW-worker-001",
        "binding_fingerprint": "a" * 64,
        "issued_at": 1000.0,
        "expires_at": 1010.0,
        "request_id": "SI-request-001",
        "nonce": "SN-1234567890abcdef",
    }
    values.update(overrides)
    return sign_supervisor_ipc_request(enrolled or enrollment(), secret, **values)


class SandboxIPCContractTests(unittest.TestCase):
    def test_enrollment_is_bounded_public_and_contains_no_secret(self):
        value = enrollment()
        public = repr(value.public_dict())
        self.assertNotIn("local.owner", public)
        self.assertNotIn(SECRET.decode("ascii"), public)
        with self.assertRaisesRegex(ValueError, "allowed operations"):
            enrollment(allowed_operations=("launch", "manage_vm"))

    def test_request_json_is_strict_bounded_and_round_trips(self):
        value = request()
        decoded = SupervisorIPCRequest.from_json_bytes(value.to_json_bytes())
        self.assertEqual(value, decoded)
        payload = json.loads(value.to_json_bytes())
        payload["extra"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            SupervisorIPCRequest.from_json_bytes(json.dumps(payload).encode())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            SupervisorIPCRequest.from_json_bytes(
                b'{"schema_version":1,"schema_version":1}',
            )
        with self.assertRaisesRegex(ValueError, "bytes"):
            SupervisorIPCRequest.from_json_bytes(b"x" * 4097)

    def test_valid_request_authenticates_once_but_does_not_claim_authority(self):
        verifier = SupervisorIPCAuthenticator(enrollment(), SECRET, clock=lambda: 1001.0)
        proof = verifier.authenticate(
            request(), trusted_peer_principal_id="local.owner",
        )
        self.assertEqual(proof.authenticated_principal_id, "local.owner")
        self.assertNotIn("authorized", repr(proof.public_dict()).casefold())
        with self.assertRaisesRegex(SupervisorIPCAuthenticationError, "already used"):
            verifier.authenticate(request(), trusted_peer_principal_id="local.owner")

    def test_wrong_peer_modified_message_or_wrong_key_is_denied(self):
        cases = (
            (request(), "other.owner"),
            (request(secret=b"x" * 32), "local.owner"),
            (request(operation="cancel"), "local.owner"),
        )
        # The final request is valid; modify its authenticated operation afterward.
        modified = cases[-1][0]
        modified = SupervisorIPCRequest(**{**modified.__dict__, "operation": "query"})
        cases = cases[:2] + ((modified, "local.owner"),)
        for value, peer in cases:
            with self.subTest(peer=peer, operation=value.operation):
                verifier = SupervisorIPCAuthenticator(enrollment(), SECRET, clock=lambda: 1001.0)
                with self.assertRaises(SupervisorIPCAuthenticationError):
                    verifier.authenticate(value, trusted_peer_principal_id=peer)

    def test_stale_expired_revoked_and_unenrolled_operations_are_denied(self):
        stale = SupervisorIPCAuthenticator(enrollment(), SECRET, clock=lambda: 1010.0)
        with self.assertRaisesRegex(SupervisorIPCAuthenticationError, "stale"):
            stale.authenticate(request(), trusted_peer_principal_id="local.owner")

        inactive = SupervisorIPCAuthenticator(enrollment(expires_at=1000.0), SECRET, clock=lambda: 1001.0)
        with self.assertRaisesRegex(SupervisorIPCAuthenticationError, "inactive"):
            inactive.authenticate(request(), trusted_peer_principal_id="local.owner")

        revoked = SupervisorIPCAuthenticator(enrollment(), SECRET, clock=lambda: 1001.0)
        revoked.revoke()
        with self.assertRaisesRegex(SupervisorIPCAuthenticationError, "revoked"):
            revoked.authenticate(request(), trusted_peer_principal_id="local.owner")

        query_only = enrollment(allowed_operations=("query",))
        verifier = SupervisorIPCAuthenticator(query_only, SECRET, clock=lambda: 1001.0)
        with self.assertRaisesRegex(SupervisorIPCAuthenticationError, "not enrolled"):
            verifier.authenticate(request(query_only), trusted_peer_principal_id="local.owner")

    def test_replay_cache_fails_closed_at_capacity(self):
        verifier = SupervisorIPCAuthenticator(
            enrollment(), SECRET, clock=lambda: 1001.0, maximum_seen_requests=1,
        )
        verifier.authenticate(request(), trusted_peer_principal_id="local.owner")
        with self.assertRaisesRegex(SupervisorIPCAuthenticationError, "capacity"):
            verifier.authenticate(
                request(request_id="SI-request-002", nonce="SN-abcdef1234567890"),
                trusted_peer_principal_id="local.owner",
            )

    def test_request_id_and_nonce_are_each_single_use(self):
        for overrides in (
            {"nonce": "SN-abcdef1234567890"},
            {"request_id": "SI-request-002"},
        ):
            with self.subTest(overrides=overrides):
                verifier = SupervisorIPCAuthenticator(
                    enrollment(), SECRET, clock=lambda: 1001.0,
                )
                verifier.authenticate(request(), trusted_peer_principal_id="local.owner")
                with self.assertRaisesRegex(SupervisorIPCAuthenticationError, "already used"):
                    verifier.authenticate(
                        request(**overrides), trusted_peer_principal_id="local.owner",
                    )

    def test_module_import_and_contracts_perform_no_io_or_execution(self):
        value = enrollment()
        signed = request(value)
        self.assertEqual("launch", signed.operation)
        self.assertNotIn("powershell", repr(value).casefold())
        self.assertNotIn("hyper-v", repr(value).casefold())


if __name__ == "__main__":
    unittest.main()
