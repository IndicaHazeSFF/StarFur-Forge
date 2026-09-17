from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_web_search import (
    SessionWebSearchArtifactStore,
    WebSearchArtifact,
    WebSearchCandidate,
)


QUERY_DIGEST = "a" * 64


class WebSearchArtifactTests(unittest.TestCase):
    @staticmethod
    def artifact(title="First"):
        return WebSearchArtifact.create(
            QUERY_DIGEST,
            "fixture.search",
            (WebSearchCandidate(1, "https://example.com/a", title),),
        )

    def test_artifact_is_deterministic_bounded_and_explicitly_untrusted(self):
        results = (
            WebSearchCandidate(1, "https://example.com/a", "  First   result  "),
            WebSearchCandidate(2, "https://docs.example.org/b", "Second result"),
        )
        first = WebSearchArtifact.create(QUERY_DIGEST, "fixture.search", results)
        second = WebSearchArtifact.create(QUERY_DIGEST, "fixture.search", results)
        self.assertEqual(first, second)
        self.assertEqual("First result", first.results[0].title)
        self.assertEqual("untrusted_discovery", first.trust_label)
        rendered = first.public_dict()
        self.assertNotIn("query", rendered)
        self.assertNotIn("snippet", repr(rendered).casefold())
        self.assertNotIn("evidence", repr(rendered).casefold())

    def test_candidate_requires_canonical_public_https_destination(self):
        for url in (
            "http://example.com/a",
            "https://127.0.0.1/private",
            "https://user:pass@example.com/private",
            "https://example.com/a#fragment",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                WebSearchCandidate(1, url, "Result")

    def test_result_ranks_and_urls_must_be_exact_and_unique(self):
        first = WebSearchCandidate(1, "https://example.com/a", "First")
        with self.assertRaisesRegex(ValueError, "contiguous"):
            WebSearchArtifact.create(
                QUERY_DIGEST,
                "fixture.search",
                (first, WebSearchCandidate(3, "https://example.com/b", "Third")),
            )
        with self.assertRaisesRegex(ValueError, "unique"):
            WebSearchArtifact.create(
                QUERY_DIGEST,
                "fixture.search",
                (first, WebSearchCandidate(2, "https://example.com/a", "Duplicate")),
            )

    def test_hidden_title_formatting_and_oversized_sets_fail_closed(self):
        with self.assertRaises(ValueError):
            WebSearchCandidate(1, "https://example.com/a", "hidden\u200btitle")
        with self.assertRaises(ValueError):
            WebSearchArtifact.create(QUERY_DIGEST, "fixture.search", ())
        with self.assertRaises(ValueError):
            WebSearchArtifact.create(
                QUERY_DIGEST,
                "fixture.search",
                tuple(
                    WebSearchCandidate(index, f"https://example.com/{index}", f"Result {index}")
                    for index in range(1, 10)
                ),
            )

    def test_artifact_digest_detects_changes(self):
        artifact = WebSearchArtifact.create(
            QUERY_DIGEST,
            "fixture.search",
            (WebSearchCandidate(1, "https://example.com/a", "First"),),
        )
        with self.assertRaisesRegex(ValueError, "digest"):
            replace(artifact, artifact_sha256="0" * 64)

    def test_session_store_uses_exact_refs_and_retains_only_valid_artifacts(self):
        refs = iter(("TF-search_one", "TF-search_two"))
        store = SessionWebSearchArtifactStore(ref_factory=lambda: next(refs))
        artifact = self.artifact()
        reference = store.store(artifact)
        self.assertEqual("TF-search_one", reference)
        self.assertIs(artifact, store.get(reference))
        self.assertIsNone(store.get("TF-search_missing"))
        self.assertIsNone(store.get("bad ref"))
        with self.assertRaises(TypeError):
            store.store(object())

    def test_session_store_capacity_and_reference_collisions_fail_closed(self):
        artifact = self.artifact()
        store = SessionWebSearchArtifactStore(
            ref_factory=lambda: "TF-search_same",
            maximum_artifacts=2,
        )
        store.store(artifact)
        with self.assertRaisesRegex(ValueError, "capacity"):
            store.store(artifact)

        tiny = SessionWebSearchArtifactStore(
            ref_factory=lambda: "TF-search_tiny",
            maximum_total_bytes=1,
        )
        with self.assertRaisesRegex(ValueError, "capacity"):
            tiny.store(artifact)


if __name__ == "__main__":
    unittest.main()
