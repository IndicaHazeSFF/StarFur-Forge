import json
from pathlib import Path
import socket
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_supervisor import SupervisorCancellation
from pipeline.tool_web_search_brave import (
    BraveSearchTransportRequest,
    WebSearchAdapterPolicyError,
)
from pipeline.tool_web_search_brave_native import (
    BRAVE_SEARCH_API_KEY_ENV,
    BRAVE_SEARCH_HOST,
    EnvironmentBraveCredentialSource,
    NativeBraveSearchTransport,
    create_brave_web_search_runtime,
)


class FakeSocket:
    def __init__(self, address="93.184.216.34"):
        self.address = address
        self.timeouts = []

    def getpeername(self):
        return (self.address, 443)

    def settimeout(self, value):
        self.timeouts.append(value)


class FakeResponse:
    status = 200

    def __init__(self, body=None, headers=None):
        self.body = body or json.dumps({"web": {"results": [
            {"title": "Result", "url": "https://example.com/result"},
        ]}}).encode()
        self.headers = headers or [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(self.body))),
        ]
        self.offset = 0

    def getheaders(self):
        return self.headers

    def read(self, size):
        result = self.body[self.offset:self.offset + size]
        self.offset += len(result)
        return result


class FakeConnection:
    def __init__(self, *, address="93.184.216.34", response=None):
        self.sock = FakeSocket(address)
        self.response = response or FakeResponse()
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


def search_request():
    return BraveSearchTransportRequest(
        "TI-brave-native",
        "a" * 64,
        "TW-brave-native",
        "current public price test",
        3,
        150.0,
    )


def public_dns(*args):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (
        "93.184.216.34", 443,
    ))]


class BraveNativeSearchTests(unittest.TestCase):
    def test_environment_secret_source_is_fixed_and_never_public(self):
        reads = []
        source = EnvironmentBraveCredentialSource(
            getenv=lambda name: reads.append(name) or "private-test-key",
        )
        self.assertTrue(source.available)
        self.assertEqual("private-test-key", source.read_api_key())
        self.assertEqual([BRAVE_SEARCH_API_KEY_ENV, BRAVE_SEARCH_API_KEY_ENV], reads)
        self.assertNotIn("private-test-key", repr(source))

    def test_transport_uses_fixed_pinned_destination_and_bounded_query(self):
        connection = FakeConnection()
        transport = NativeBraveSearchTransport(
            clock=lambda: 120.0,
            getaddrinfo=public_dns,
            connection_factory=lambda address, timeout: connection,
        )
        response = transport.search(
            search_request(), "private-test-key", SupervisorCancellation(),
        )
        self.assertEqual(200, response.status_code)
        self.assertTrue(connection.closed)
        rendered = repr(connection.calls)
        self.assertIn("current+public+price+test", rendered)
        self.assertIn("&count=3", rendered)
        self.assertIn(BRAVE_SEARCH_HOST, rendered)
        self.assertIn("X-Subscription-Token", rendered)
        self.assertIn("private-test-key", rendered)

    def test_non_global_dns_denies_before_connection_or_secret_disclosure(self):
        connections = []
        transport = NativeBraveSearchTransport(
            clock=lambda: 120.0,
            getaddrinfo=lambda *args: [(
                socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443),
            )],
            connection_factory=lambda address, timeout: connections.append(address),
        )
        with self.assertRaisesRegex(WebSearchAdapterPolicyError, "forbidden"):
            transport.search(
                search_request(), "private-test-key", SupervisorCancellation(),
            )
        self.assertEqual([], connections)

    def test_peer_change_duplicate_headers_and_timeout_fail_closed(self):
        connection = FakeConnection(address="93.184.216.35")
        transport = NativeBraveSearchTransport(
            clock=lambda: 120.0,
            getaddrinfo=public_dns,
            connection_factory=lambda address, timeout: connection,
        )
        with self.assertRaisesRegex(WebSearchAdapterPolicyError, "binding changed"):
            transport.search(search_request(), "private-test-key", SupervisorCancellation())

        response = FakeResponse(headers=[
            ("Content-Type", "application/json"),
            ("Content-Type", "application/json"),
        ])
        connection = FakeConnection(response=response)
        transport = NativeBraveSearchTransport(
            clock=lambda: 120.0,
            getaddrinfo=public_dns,
            connection_factory=lambda address, timeout: connection,
        )
        with self.assertRaisesRegex(WebSearchAdapterPolicyError, "ambiguous"):
            transport.search(search_request(), "private-test-key", SupervisorCancellation())

        transport = NativeBraveSearchTransport(clock=lambda: 151.0, getaddrinfo=public_dns)
        with self.assertRaisesRegex(Exception, "expired"):
            transport.search(search_request(), "private-test-key", SupervisorCancellation())

    def test_runtime_composition_is_inert_and_unavailable_without_key(self):
        dns_calls = []
        runtime = create_brave_web_search_runtime(
            getenv=lambda name: None,
            clock=lambda: 100.0,
            getaddrinfo=lambda *args: dns_calls.append(args),
        )
        observation = runtime.service_observation("TR-brave-service")
        self.assertFalse(runtime.supervisor.available)
        self.assertFalse(observation.available)
        self.assertEqual("hosted", observation.deployment)
        self.assertEqual([], dns_calls)


if __name__ == "__main__":
    unittest.main()
