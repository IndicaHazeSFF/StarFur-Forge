import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_selection import select_research_sources
from pipeline.tool_web_connector import WebFetchedArtifact
from pipeline.tool_web_parser import QuarantinedWebText
from pipeline.tool_web_policy import WebDestination


def artifact(url, text="Public fact."):
    digest = hashlib.sha256(text.encode()).hexdigest()
    return WebFetchedArtifact(
        1, "a" * 64, WebDestination(1, url), "93.184.216.34", 100.0,
        "b" * 64, "c" * 64,
        QuarantinedWebText(1, "text/plain", "untrusted_external", text, len(text), digest, digest),
    )


class ResearchSelectionTests(unittest.TestCase):
    def test_selection_is_explicit_unique_and_deterministically_ordered(self):
        sources = select_research_sources([
            ("TF-z", artifact("https://example.com/z")),
            ("TF-a", artifact("https://example.com/a")),
        ])
        self.assertEqual(("https://example.com/a", "https://example.com/z"), tuple(item.url for item in sources))

    def test_duplicate_missing_or_invalid_items_fail_closed(self):
        item = ("TF-a", artifact("https://example.com/a"))
        with self.assertRaisesRegex(ValueError, "unique"):
            select_research_sources([item, item])
        with self.assertRaisesRegex(ValueError, "source count"):
            select_research_sources([])
        with self.assertRaisesRegex(TypeError, "artifact"):
            select_research_sources([("TF-a", object())])

    def test_sources_that_collapse_to_same_identity_are_rejected(self):
        source = artifact("https://example.com/same")
        with self.assertRaisesRegex(ValueError, "remain distinct"):
            select_research_sources([("TF-a", source), ("TF-b", source)])


if __name__ == "__main__":
    unittest.main()
