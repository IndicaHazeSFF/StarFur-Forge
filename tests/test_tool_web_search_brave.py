import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_supervisor import SupervisorCancellation
from pipeline.tool_web_search_brave import (
    BRAVE_SEARCH_SERVICE_ID,
    BraveSearchHTTPResponse,
    BraveWebSearchAdapter,
    MAX_BRAVE_SEARCH_RESPONSE_BYTES,
    parse_brave_search_response,
)
from pipeline.tool_web_search_connector import WebSearchAdapterPolicyError, WebSearchRequest


def request(*, service_id=BRAVE_SEARCH_SERVICE_ID, maximum_results=2):
    return WebSearchRequest.from_launch(
        type("Launch", (), {
            "invocation_id": "TI-brave-search",
            "binding_fingerprint": "a" * 64,
            "worker_generation": "TW-brave-search",
            "authorization_deadline": 200.0,
        })(),
        service_id=service_id,
        query="current public test query",
        maximum_results=maximum_results,
    )


def response_body():
    return json.dumps({
        "type": "search",
        "web": {
            "results": [
                {
                    "title": "First result",
                    "url": "https://example.com/one",
                    "description": "untrusted snippet must not cross the adapter",
                },
                {
                    "title": "Second result",
                    "url": "https://example.org/two",
                },
                {
                    "title": "Third result",
                    "url": "https://example.net/three",
                },
            ],
        },
        "query": {"original": "current public test query"},
    }).encode("utf-8")


class FakeCredentials:
    def __init__(self, value="secret-test-key", *, available=True):
        self.value = value
        self.available = available
        self.reads = 0

    def read_api_key(self):
        self.reads += 1
        return self.value


class FakeTransport:
    def __init__(self, *, available=True, result=None):
        self.available = available
        self.result = result or BraveSearchHTTPResponse(200, "application/json", response_body())
        self.calls = []
        self.cancelled = []

    def search(self, search_request, api_key, cancellation):
        self.calls.append((search_request, api_key, cancellation))
        return self.result

    def request_cancel(self, search_request):
        self.cancelled.append(search_request)


class BraveSearchAdapterTests(unittest.TestCase):
    def test_adapter_reads_secret_only_at_execution_and_returns_bounded_candidates(self):
        credentials = FakeCredentials()
        transport = FakeTransport()
        adapter = BraveWebSearchAdapter(credentials, transport)

        self.assertTrue(adapter.available)
        self.assertEqual(0, credentials.reads)
        result = adapter.search(request(), SupervisorCancellation())

        self.assertEqual(1, credentials.reads)
        self.assertEqual("secret-test-key", transport.calls[0][1])
        self.assertEqual(2, len(result.results))
        self.assertEqual("https://example.com/one", result.results[0].url)
        self.assertFalse(hasattr(result.results[0], "description"))
        self.assertNotIn("secret-test-key", repr(result))

    def test_wrong_service_or_missing_credential_denies_before_transport(self):
        transport = FakeTransport()
        adapter = BraveWebSearchAdapter(FakeCredentials(), transport)
        with self.assertRaisesRegex(WebSearchAdapterPolicyError, "service binding"):
            adapter.search(request(service_id="other.search"), SupervisorCancellation())
        self.assertEqual([], transport.calls)

        credentials = FakeCredentials("bad key with spaces")
        adapter = BraveWebSearchAdapter(credentials, transport)
        with self.assertRaisesRegex(WebSearchAdapterPolicyError, "credential"):
            adapter.search(request(), SupervisorCancellation())
        self.assertEqual([], transport.calls)

    def test_cancelled_request_never_reads_secret_or_calls_transport(self):
        credentials = FakeCredentials()
        transport = FakeTransport()
        adapter = BraveWebSearchAdapter(credentials, transport)
        cancellation = SupervisorCancellation()
        cancellation.request()
        with self.assertRaisesRegex(Exception, "cancelled"):
            adapter.search(request(), cancellation)
        self.assertEqual((0, []), (credentials.reads, transport.calls))

    def test_parser_rejects_non_success_invalid_and_oversized_payloads(self):
        with self.assertRaises(WebSearchAdapterPolicyError):
            parse_brave_search_response(
                BraveSearchHTTPResponse(401, "application/json", b"{}"),
                maximum_results=2,
            )
        for body in (
            b"not json",
            b'{"web":{"results":[]}}',
            b'{"web":{"results":[{"title":"x","url":"http://example.com"}]}}',
            b'{"web":{"results":[{"title":"x","title":"y","url":"https://example.com"}]}}',
        ):
            with self.subTest(body=body):
                with self.assertRaises((TypeError, ValueError)):
                    parse_brave_search_response(
                        BraveSearchHTTPResponse(200, "application/json", body),
                        maximum_results=2,
                    )
        with self.assertRaises(ValueError):
            BraveSearchHTTPResponse(
                200, "application/json", b"x" * (MAX_BRAVE_SEARCH_RESPONSE_BYTES + 1),
            )

    def test_duplicate_canonical_urls_fail_closed(self):
        body = json.dumps({"web": {"results": [
            {"title": "One", "url": "https://example.com/path"},
            {"title": "Two", "url": "https://example.com/path"},
        ]}}).encode()
        with self.assertRaisesRegex(ValueError, "unique"):
            parse_brave_search_response(
                BraveSearchHTTPResponse(200, "application/json", body),
                maximum_results=2,
            )


if __name__ == "__main__":
    unittest.main()
