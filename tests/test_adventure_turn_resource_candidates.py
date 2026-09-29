import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition
from pipeline.adventure_turn_resource_candidates import (
    AdventureTurnResourceCandidateError,
    parse_untrusted_adventure_turn_resource_candidates,
    render_adventure_turn_resource_candidate_batch,
)
from pipeline.adventure_turn_resource_policy import AdventureTurnResourcePolicyView


class AdventureTurnResourceCandidateTests(unittest.TestCase):
    def setUp(self):
        self.policy = AdventureTurnResourcePolicyView.from_catalog(AdventureResourceCatalog((
            AdventureResourceDefinition("hatch", "Hatch", "enum", allowed_values=("sealed", "open")),
            AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
            AdventureResourceDefinition("secret", "Secret", "enum", visibility="hidden", allowed_values=("a", "b")),
        )))

    def test_public_enum_candidate_receives_a_distinct_resource_handle(self):
        batch = parse_untrusted_adventure_turn_resource_candidates({
            "schema_version": 1,
            "candidates": [{
                "mutation": {"kind": "resource_change", "id": "hatch", "operation": "set", "value": "open"},
                "confidence": 0.8,
            }],
        }, self.policy)
        self.assertEqual("TR-001", batch.candidates[0].candidate_id)
        rendered = render_adventure_turn_resource_candidate_batch(batch, generation_id="TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertIn("TR-001 [resource_change]", rendered)
        self.assertIn("untrusted; not staged", rendered)

    def test_wrong_or_hidden_resource_data_cannot_enter_the_resource_channel(self):
        for mutation in (
            {"kind": "resource_change", "id": "fuel", "operation": "set", "value": 10},
            {"kind": "resource_change", "id": "secret", "operation": "set", "value": "a"},
            {"kind": "state_set", "key": "current_location", "value": "engine room"},
        ):
            with self.assertRaisesRegex(AdventureTurnResourceCandidateError, "payload is invalid"):
                parse_untrusted_adventure_turn_resource_candidates({
                    "schema_version": 1, "candidates": [{"mutation": mutation, "confidence": 0.8}],
                }, self.policy)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
