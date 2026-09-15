import hashlib
import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_supervisor import SupervisorCancellation
from pipeline.tool_web_connector import (
    WebFetchedArtifact,
    WebTransportPolicyError,
    WebTransportRequest,
)
from pipeline.tool_web_native import (
    NativeHTTPSWebTransport,
    NativeWebResolver,
    SessionWebPrerequisiteStore,
    SessionWebQuarantineStore,
)
from pipeline.tool_web_parser import prepare_quarantined_web_text
from pipeline.tool_web_policy import WebDestination
from pipeline.tool_web_response import WebResponseCollector, WebResponseMetadata


class FakeSocket:
    def __init__(self, address="93.184.216.34"):
        self.address = address
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)

    def getpeername(self):
        return self.address, 443


class FakeResponse:
    status = 200

    def __init__(self, body=b"bounded public text", headers=None):
        self.body = body
        self.offset = 0
        self.headers = headers or [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ]

    def getheaders(self):
        return list(self.headers)

    def read(self, size):
        value = self.body[self.offset:self.offset + size]
        self.offset += len(value)
        return value


class FakeConnection:
    def __init__(self, response=None):
        self.response = response or FakeResponse()
        self.sock = FakeSocket()
        self.calls = []
        self.closed = False

    def putrequest(self, *args, **kwargs):
        self.calls.append(("request", args, kwargs))

    def putheader(self, *args):
        self.calls.append(("header", args))

    def endheaders(self):
        self.calls.append(("end",))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class ClosingResponseConnection(FakeConnection):
    """Mimic http.client clearing its socket for Connection: close."""

    def getresponse(self):
        response = self.response
        self.sock = None
        return response


def transport_request():
    return WebTransportRequest(
        1,
        "TI-native_web",
        "a" * 64,
        "TW-native-web",
        WebDestination(1, "https://example.com/reference?q=public"),
        "93.184.216.34",
        "example.com",
        "example.com",
        150.0,
    )


def quarantined_artifact():
    body = b"public source"
    collector = WebResponseCollector(
        WebResponseMetadata(1, 200, "text/plain", "identity", len(body)),
    )
    collector.append(body, encoded_bytes_consumed=len(body))
    payload = prepare_quarantined_web_text(collector.finalize())
    return WebFetchedArtifact(
        1, "a" * 64, WebDestination(1, "https://example.com/reference"),
        "93.184.216.34", 120.0, "b" * 64, "c" * 64, payload,
    )


class ToolWebNativeTests(unittest.TestCase):
    def test_resolver_uses_fixed_stream_request_and_returns_bounded_evidence(self):
        calls = []

        def fake_getaddrinfo(*args):
            calls.append(args)
            return [
                (2, 1, 6, "", ("93.184.216.34", 443)),
                (2, 1, 6, "", ("93.184.216.34", 443)),
                (10, 1, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0)),
            ]

        resolver = NativeWebResolver(getaddrinfo=fake_getaddrinfo, clock=lambda: 100.0)
        evidence = resolver.resolve(WebDestination(1, "https://example.com/reference"))
        self.assertEqual(("example.com", 443), calls[0][0:2])
        self.assertEqual(2, len(evidence.addresses))
        self.assertEqual((100.0, 130.0), (
            evidence.observed_at_epoch, evidence.expires_at_epoch,
        ))

    def test_prerequisite_store_classifies_exact_url_and_is_revocable(self):
        refs = iter(("TR-destination", "TR-disclosure"))
        resolver = NativeWebResolver(
            getaddrinfo=lambda *args: [(2, 1, 6, "", ("93.184.216.34", 443))],
            clock=lambda: 100.0,
        )
        store = SessionWebPrerequisiteStore(resolver, ref_factory=lambda: next(refs))
        destination = WebDestination(1, "https://example.com/reference")
        destination_record, disclosure_record = store.prepare_public(destination)
        self.assertEqual(destination_record, store.destination_for("TR-destination"))
        self.assertEqual(disclosure_record, store.disclosure_for("TR-disclosure"))
        self.assertEqual(
            hashlib.sha256(destination.url.encode("utf-8")).hexdigest(),
            disclosure_record.intent.content_sha256,
        )
        self.assertTrue(store.revoke("TR-destination"))
        with self.assertRaises(KeyError):
            store.destination_for("TR-destination")

    def test_prerequisite_reservation_is_inert_until_explicit_prepare(self):
        calls = []
        refs = iter(("TR-reserved_destination", "TR-reserved_disclosure"))
        resolver = NativeWebResolver(
            getaddrinfo=lambda *args: calls.append(args) or [
                (2, 1, 6, "", ("93.184.216.34", 443)),
            ],
            clock=lambda: 100.0,
        )
        store = SessionWebPrerequisiteStore(resolver, ref_factory=lambda: next(refs))
        destination = WebDestination(1, "https://example.com/reference")

        reserved = store.reserve_public(destination)
        self.assertEqual(("TR-reserved_destination", "TR-reserved_disclosure"), reserved)
        self.assertEqual([], calls)
        with self.assertRaises(KeyError):
            store.destination_for(reserved[0])

        prepared = store.prepare_reserved(*reserved)
        self.assertEqual(1, len(calls))
        self.assertEqual(destination, prepared[0].destination)

    def test_transport_sends_fixed_no_credential_request_and_pins_peer(self):
        connection = FakeConnection()
        transport = NativeHTTPSWebTransport(
            clock=lambda: 120.0,
            connection_factory=lambda request, timeout: connection,
        )
        response = transport.fetch(transport_request(), SupervisorCancellation())
        self.assertEqual("93.184.216.34", response.connected_address)
        self.assertEqual(b"bounded public text", response.chunks[0].data)
        self.assertTrue(connection.closed)
        rendered = repr(connection.calls)
        self.assertIn("'GET', '/reference?q=public'", rendered)
        self.assertIn("'Host', 'example.com'", rendered)
        self.assertIn("'Accept-Encoding', 'identity'", rendered)
        self.assertNotIn("Cookie", rendered)
        self.assertNotIn("Authorization", rendered)

    def test_transport_captures_tls_peer_before_http_client_clears_socket(self):
        connection = ClosingResponseConnection()
        transport = NativeHTTPSWebTransport(
            clock=lambda: 120.0,
            connection_factory=lambda request, timeout: connection,
        )

        response = transport.fetch(transport_request(), SupervisorCancellation())

        self.assertEqual("93.184.216.34", response.connected_address)
        self.assertTrue(connection.closed)

    def test_transport_rejects_redirects_unsupported_media_and_duplicate_headers(self):
        for response in (
            type("Redirect", (), {"status": 302})(),
            FakeResponse(headers=[("Content-Type", "text/html")]),
            FakeResponse(headers=[
                ("Content-Type", "text/plain"),
                ("Transfer-Encoding", "chunked"),
            ]),
            FakeResponse(headers=[
                ("Content-Type", "text/plain"),
                ("Content-Type", "text/markdown"),
            ]),
        ):
            with self.subTest(response=response):
                connection = FakeConnection(response=response)
                transport = NativeHTTPSWebTransport(
                    clock=lambda: 120.0,
                    connection_factory=lambda request, timeout, value=connection: value,
                )
                with self.assertRaises(WebTransportPolicyError):
                    transport.fetch(transport_request(), SupervisorCancellation())
                self.assertTrue(connection.closed)

    def test_quarantine_store_is_bounded_and_reference_only(self):
        refs = iter(("TF-first", "TF-second"))
        store = SessionWebQuarantineStore(
            ref_factory=lambda: next(refs), maximum_artifacts=1,
        )
        artifact = quarantined_artifact()
        reference = store.store(artifact)
        self.assertEqual("TF-first", reference)
        self.assertEqual(artifact, store.get(reference))
        with self.assertRaisesRegex(ValueError, "capacity"):
            store.store(artifact)


if __name__ == "__main__":
    unittest.main()
