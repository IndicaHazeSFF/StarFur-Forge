import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.adventure_mutation import (
    AdventureEventEnvelope,
    AdventureMutation,
    AdventureMutationError,
    MUTATION_RELATIONSHIP_SET,
    MUTATION_STATE_SET,
)


class AdventureMutationTests(unittest.TestCase):
    def test_state_mutation_and_v2_envelope_round_trip_without_parsing_prose(self):
        mutation = AdventureMutation(
            MUTATION_STATE_SET,
            state_key="Current_Location",
            state_value="  Chart room  ",
        )
        envelope = AdventureEventEnvelope(
            sequence=2,
            event_id="AE-000002",
            event_type="state_change",
            recorded_at="2026-08-19T12:00:00+00:00",
            summary="The crew reaches the chart room.",
            details="Narrative prose stays separate.",
            request_id="turn-12345678",
            supersedes_event_id="AE-000001",
            mutation=mutation,
        )

        self.assertEqual("current_location", mutation.state_key)
        self.assertEqual("Chart room", mutation.state_value)
        self.assertEqual(envelope, AdventureEventEnvelope.from_dict(envelope.to_dict()))

    def test_unknown_or_mixed_mutation_payloads_fail_closed(self):
        with self.assertRaisesRegex(AdventureMutationError, "unsupported"):
            AdventureMutation.from_dict({"kind": "inventory_add", "item": "key"})
        with self.assertRaisesRegex(AdventureMutationError, "cannot contain another"):
            AdventureMutation(
                MUTATION_RELATIONSHIP_SET,
                relationship_subject="Vespera",
                relationship_dimension="trust",
                relationship_value="cautious",
                state_key="location",
                state_value="deck",
            )

    def test_envelope_rejects_model_authored_authority_and_invalid_supersession(self):
        with self.assertRaisesRegex(AdventureMutationError, "source is not permitted"):
            AdventureEventEnvelope(
                sequence=1,
                event_id="AE-000001",
                event_type="discovery",
                recorded_at="2026-08-19T12:00:00+00:00",
                summary="A model claims a mutation.",
                details=None,
                source="model_inferred",
            )
        with self.assertRaisesRegex(AdventureMutationError, "cannot supersede itself"):
            AdventureEventEnvelope(
                sequence=1,
                event_id="AE-000001",
                event_type="discovery",
                recorded_at="2026-08-19T12:00:00+00:00",
                summary="An invalid correction.",
                details=None,
                supersedes_event_id="AE-000001",
            )


if __name__ == "__main__":
    unittest.main()
