import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, __import__("pathlib").Path(__file__).resolve().parents[1])
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import proposal_pipeline


class ProposalNormalizationTests(unittest.TestCase):
    def test_trivial_variants_normalize_to_same_name(self):
        self.assertEqual(
            proposal_pipeline.normalize_proposal_name("  Meridian-Compact! "),
            "meridian compact",
        )

    @patch.object(proposal_pipeline, "get_entity_names_and_aliases", return_value=[])
    @patch.object(
        proposal_pipeline,
        "get_pending_proposals",
        return_value=[{"proposed_name": "Meridian Compact"}],
    )
    def test_pending_trivial_duplicate_is_suppressed(self, _pending, _confirmed):
        match = proposal_pipeline.proposal_match(" meridian   compact ")
        self.assertEqual(match, {"kind": "pending_duplicate", "match": "Meridian Compact"})

    @patch.object(
        proposal_pipeline,
        "get_entity_names_and_aliases",
        return_value=["Meridian Compact", "MC"],
    )
    @patch.object(proposal_pipeline, "get_pending_proposals", return_value=[])
    def test_confirmed_canonical_or_alias_is_duplicate(self, _pending, _confirmed):
        self.assertEqual(
            proposal_pipeline.proposal_match("mc"),
            {"kind": "confirmed_duplicate", "match": "MC"},
        )

    @patch.object(
        proposal_pipeline,
        "get_entity_names_and_aliases",
        return_value=["Meridian Compact"],
    )
    @patch.object(proposal_pipeline, "get_pending_proposals", return_value=[])
    def test_ambiguous_short_name_is_surfaced_for_review(self, _pending, _confirmed):
        match = proposal_pipeline.proposal_match("Meridian")
        self.assertEqual(match["kind"], "possible_match")
        self.assertEqual(match["matches"], ["Meridian Compact"])


if __name__ == "__main__":
    unittest.main()
