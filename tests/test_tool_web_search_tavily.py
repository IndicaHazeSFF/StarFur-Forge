import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_supervisor import SupervisorCancellation
from pipeline.tool_web_search_connector import WebSearchAdapterPolicyError, WebSearchRequest
from pipeline.tool_web_search_tavily import (
    MAX_TAVILY_SEARCH_RESPONSE_BYTES,
    TAVILY_SEARCH_SERVICE_ID,
    TavilySearchHTTPResponse,
    TavilyWebSearchAdapter,
    parse_tavily_search_response,
)


def request(*, service_id=TAVILY_SEARCH_SERVICE_ID, maximum_results=2):
    return WebSearchRequest.from_launch(
        type("Launch", (), {
            "invocation_id": "TI-tavily-search",
            "binding_fingerprint": "a" * 64,
            "worker_generation": "TW-tavily-search",
            "authorization_deadline": 200.0,
        })(),
        service_id=service_id,
        query="current public test query",
        maximum_results=maximum_results,
    )


def response_body():
    return json.dumps({
        "query": "current public test query",
        "answer": "provider prose must not cross the adapter",
        "results": [
            {
                "title": "First result",
                "url": "https://example.com/one",
                "content": "untrusted snippet must not cross the adapter",
                "score": 0.99,
                "raw_content": "raw provider content must not cross the adapter",
            },
            {"title": "Second result", "url": "https://example.org/two"},
            {"title": "Third result", "url": "https://example.net/three"},
        ],
        "usage": {"credits": 1},
        "request_id": "provider-request-id",
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
        self.result = result or TavilySearchHTTPResponse(200, "application/json", response_body())
        self.calls = []
        self.cancelled = []

    def search(self, search_request, api_key, cancellation):
        self.calls.append((search_request, api_key, cancellation))
        return self.result

    def request_cancel(self, search_request):
        self.cancelled.append(search_request)


class TavilySearchAdapterTests(unittest.TestCase):
    def test_adapter_reads_secret_only_at_execution_and_returns_bounded_candidates(self):
        credentials = FakeCredentials()
        transport = FakeTransport()
        adapter = TavilyWebSearchAdapter(credentials, transport)

        self.assertTrue(adapter.available)
        self.assertEqual(0, credentials.reads)
        result = adapter.search(request(), SupervisorCancellation())

        self.assertEqual(1, credentials.reads)
        self.assertEqual("secret-test-key", transport.calls[0][1])
        self.assertEqual(2, len(result.results))
        self.assertEqual("https://example.com/one", result.results[0].url)
        self.assertFalse(hasattr(result.results[0], "content"))
        self.assertNotIn("provider-request-id", repr(result))
        self.assertNotIn("secret-test-key", repr(result))

    def test_wrong_service_or_missing_credential_denies_before_transport(self):
        transport = FakeTransport()
        adapter = TavilyWebSearchAdapter(FakeCredentials(), transport)
        with self.assertRaisesRegex(WebSearchAdapterPolicyError, "service binding"):
            adapter.search(request(service_id="other.search"), SupervisorCancellation())
        self.assertEqual([], transport.calls)

        adapter = TavilyWebSearchAdapter(FakeCredentials("bad key with spaces"), transport)
        with self.assertRaisesRegex(WebSearchAdapterPolicyError, "credential"):
            adapter.search(request(), SupervisorCancellation())
        self.assertEqual([], transport.calls)

    def test_cancelled_request_never_reads_secret_or_calls_transport(self):
        credentials = FakeCredentials()
        transport = FakeTransport()
        adapter = TavilyWebSearchAdapter(credentials, transport)
        cancellation = SupervisorCancellation()
        cancellation.request()
        with self.assertRaisesRegex(Exception, "cancelled"):
            adapter.search(request(), cancellation)
        self.assertEqual((0, []), (credentials.reads, transport.calls))

    def test_parser_rejects_non_success_invalid_and_oversized_payloads(self):
        with self.assertRaises(WebSearchAdapterPolicyError):
            parse_tavily_search_response(
                TavilySearchHTTPResponse(401, "application/json", b"{}"),
                maximum_results=2,
            )
        for body in (
            b"not json",
            b'{"results":[]}',
            b'{"results":[{"title":"x","url":"http://example.com"}]}',
            b'{"results":[{"title":"x","title":"y","url":"https://example.com"}]}',
        ):
            with self.subTest(body=body):
                with self.assertRaises((TypeError, ValueError)):
                    parse_tavily_search_response(
                        TavilySearchHTTPResponse(200, "application/json", body),
                        maximum_results=2,
                    )
        with self.assertRaises(ValueError):
            TavilySearchHTTPResponse(
                200, "application/json", b"x" * (MAX_TAVILY_SEARCH_RESPONSE_BYTES + 1),
            )

    def test_duplicate_canonical_urls_fail_closed(self):
        body = json.dumps({"results": [
            {"title": "One", "url": "https://example.com/path"},
            {"title": "Two", "url": "https://example.com/path"},
        ]}).encode()
        with self.assertRaisesRegex(ValueError, "unique"):
            parse_tavily_search_response(
                TavilySearchHTTPResponse(200, "application/json", body),
                maximum_results=2,
            )


if __name__ == "__main__":
    unittest.main()
