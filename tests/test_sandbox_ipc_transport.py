from pathlib import Path
import struct
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_ipc import (
    SupervisorIPCAuthenticator,
    SupervisorIPCEnrollment,
    sign_supervisor_ipc_request,
)
from pipeline.sandbox_ipc_transport import (
    AuthenticatedSupervisorIPCReceiver,
    SupervisorIPCFramingError,
    frame_supervisor_ipc_request,
)


SECRET = b"t" * 32


def enrollment():
    return SupervisorIPCEnrollment(
        1, "SE-transport-001", "local.owner", "starfur.sandbox.supervisor",
        "supervisor-v1", "local_authenticated_ipc", "transport-v1",
        "SK-transport-001", ("launch", "query", "cancel"), 900.0, 2000.0,
    )


def request(number=1, *, secret=SECRET):
    return sign_supervisor_ipc_request(
        enrollment(), secret,
        session_instance_id="session-001", operation="query",
        invocation_id=f"TI-transport-{number:03d}",
        worker_generation=f"TW-worker-{number:03d}",
        binding_fingerprint=f"{number:x}".rjust(64, "0"),
        issued_at=1000.0, expires_at=1010.0,
        request_id=f"SI-request-{number:03d}",
        nonce=f"SN-{number:016d}",
    )


def receiver(*, principal="local.owner", maximum_frames=16):
    verifier = SupervisorIPCAuthenticator(enrollment(), SECRET, clock=lambda: 1001.0)
    return AuthenticatedSupervisorIPCReceiver(
        verifier, trusted_peer_principal_id=principal,
        maximum_frames=maximum_frames,
    )


class SandboxIPCTransportTests(unittest.TestCase):
    def test_fragmented_frame_authenticates_only_when_complete(self):
        framed = frame_supervisor_ipc_request(request())
        value = receiver()
        self.assertEqual((), value.feed(framed[:2]))
        self.assertEqual((), value.feed(framed[2:15]))
        accepted = value.feed(framed[15:])
        self.assertEqual(1, len(accepted))
        self.assertEqual("query", accepted[0].request.operation)
        value.close()
        self.assertTrue(value.closed)

    def test_coalesced_frames_remain_separate_and_bounded(self):
        value = receiver(maximum_frames=2)
        accepted = value.feed(
            frame_supervisor_ipc_request(request(1))
            + frame_supervisor_ipc_request(request(2))
        )
        self.assertEqual(("SI-request-001", "SI-request-002"), tuple(
            item.request.request_id for item in accepted
        ))
        with self.assertRaisesRegex(SupervisorIPCFramingError, "limit"):
            value.feed(frame_supervisor_ipc_request(request(3)))
        self.assertTrue(value.failed)

    def test_zero_oversized_malformed_and_partial_frames_fail_closed(self):
        invalid = (
            struct.pack(">I", 0),
            struct.pack(">I", 4097),
            struct.pack(">I", 4) + b"nope",
        )
        for framed in invalid:
            with self.subTest(framed=framed[:8]):
                value = receiver()
                with self.assertRaises(SupervisorIPCFramingError):
                    value.feed(framed)
                self.assertTrue(value.closed)
                self.assertTrue(value.failed)

        value = receiver()
        framed = frame_supervisor_ipc_request(request())
        value.feed(framed[:-1])
        with self.assertRaisesRegex(SupervisorIPCFramingError, "partial"):
            value.close()

    def test_wrong_peer_or_authentication_tag_poison_connection(self):
        cases = (
            (receiver(principal="other.owner"), request()),
            (receiver(), request(secret=b"x" * 32)),
        )
        for value, message in cases:
            with self.subTest(principal=value):
                with self.assertRaisesRegex(SupervisorIPCFramingError, "authentication"):
                    value.feed(frame_supervisor_ipc_request(message))
                with self.assertRaisesRegex(SupervisorIPCFramingError, "closed"):
                    value.feed(frame_supervisor_ipc_request(request(2)))

    def test_replayed_frame_is_rejected_without_dispatch(self):
        value = receiver()
        framed = frame_supervisor_ipc_request(request())
        self.assertEqual(1, len(value.feed(framed)))
        with self.assertRaisesRegex(SupervisorIPCFramingError, "authentication"):
            value.feed(framed)

    def test_abort_discards_partial_data_and_is_not_stop_proof(self):
        value = receiver()
        framed = frame_supervisor_ipc_request(request())
        self.assertEqual((), value.feed(framed[:10]))
        self.assertIsNone(value.abort())
        self.assertTrue(value.closed)
        self.assertFalse(value.failed)
        self.assertNotIn("stopped", repr(value.__dict__).casefold())

    def test_receiver_has_no_transport_or_execution_callback(self):
        value = receiver()
        accepted = value.feed(frame_supervisor_ipc_request(request()))
        self.assertEqual(1, len(accepted))
        self.assertFalse(hasattr(value, "run"))
        self.assertFalse(hasattr(value, "dispatch"))
        self.assertFalse(hasattr(value, "connect"))


if __name__ == "__main__":
    unittest.main()
