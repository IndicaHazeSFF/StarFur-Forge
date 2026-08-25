import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.adventure_events import AdventureEventDraft, AdventureEventLog
from pipeline.adventure_mutation import AdventureMutation, MUTATION_KNOWLEDGE_SET, MUTATION_RELATIONSHIP_SET, MUTATION_STATE_SET
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition
from pipeline.adventure_resource_state import AdventureResourceOperation
from pipeline.adventure_turn import AdventureTurnTransaction


class AdventureTurnTests(unittest.TestCase):
    def test_staged_drafts_are_in_memory_until_one_atomic_batch_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 18, tzinfo=UTC))
            record = registry.create("Quiet Ember")
            transaction = AdventureTurnTransaction.inactive().begin(record)
            transaction = transaction.stage(AdventureEventDraft("discovery", "The crew finds a hatch."))
            transaction = transaction.stage(AdventureEventDraft("choice", "The crew opens it."))
            log = AdventureEventLog(registry, record)
            self.assertEqual([], log.events())
            written = log.append_many(transaction.drafts, request_id=transaction.request_id)
            self.assertEqual(["AE-000001", "AE-000002"], [event.event_id for event in written])
            self.assertTrue(all(event.request_id == transaction.request_id for event in written))
            self.assertEqual(written, log.append_many(transaction.drafts, request_id=transaction.request_id))
            self.assertEqual(2, len(log.events()))

    def test_abort_never_persists_and_inactive_cannot_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 18, tzinfo=UTC))
            record = registry.create("Quiet Ember")
            transaction = AdventureTurnTransaction.inactive().begin(record)
            transaction = transaction.stage(AdventureEventDraft("discovery", "The crew finds a hatch."))
            self.assertFalse(transaction.abort().active)
            self.assertEqual([], AdventureEventLog(registry, record).events())
            with self.assertRaisesRegex(ValueError, "no adventure turn"):
                AdventureTurnTransaction.inactive().stage(AdventureEventDraft("choice", "Open it."))

    def test_typed_structured_mutations_stage_with_ordinary_events_and_commit_together(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 18, tzinfo=UTC))
            record = registry.create("Quiet Ember")
            transaction = AdventureTurnTransaction.inactive().begin(record)
            transaction = transaction.stage(AdventureEventDraft("discovery", "The crew finds a compass."))
            transaction = transaction.stage_mutation(
                AdventureMutation(MUTATION_STATE_SET, state_key="location", state_value="chart room"),
                summary="The crew reaches the chart room.",
            )
            transaction = transaction.stage_mutation(
                AdventureMutation(
                    MUTATION_RELATIONSHIP_SET,
                    relationship_subject="Vespera",
                    relationship_dimension="trust",
                    relationship_value="cautious",
                ),
                summary="Vespera remains cautiously trusting.",
            )
            transaction = transaction.stage_mutation(
                AdventureMutation(
                    MUTATION_KNOWLEDGE_SET,
                    knowledge_subject="Rook",
                    knowledge_status="believes",
                    knowledge_fact="the hatch is trapped",
                ),
                summary="Rook believes the hatch is trapped.",
            )

            self.assertEqual(4, len(transaction.drafts))
            self.assertEqual(3, len(transaction.mutations))
            log = AdventureEventLog(registry, record)
            written = log.append_many(transaction.drafts, request_id=transaction.request_id)

            self.assertEqual(["discovery", "state_change", "relationship_change", "character_knowledge"], [event.event_type for event in written])
            self.assertEqual("chart room", written[1].state_value)
            self.assertEqual("cautious", written[2].relationship_value)
            self.assertEqual("the hatch is trapped", written[3].knowledge_fact)
            self.assertEqual(4, len(log.events()))

    def test_resource_operation_stages_as_one_validated_v1_resource_event(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 18, tzinfo=UTC))
            record = registry.create("Quiet Ember")
            registry.configure_resource_catalog(record, AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
            )))
            transaction = AdventureTurnTransaction.inactive().begin(record).stage_resource(
                AdventureResourceOperation("fuel", "increment", 20),
                summary="Fuel changed.",
            )
            self.assertEqual(1, len(transaction.drafts))
            self.assertEqual(0, len(transaction.mutations))
            written = AdventureEventLog(registry, record).append_many(
                transaction.drafts, request_id=transaction.request_id,
            )
            self.assertEqual("resource_change", written[0].event_type)
            self.assertEqual("fuel", written[0].resource_id)
            self.assertEqual("increment", written[0].resource_operation)
            self.assertEqual(20, written[0].resource_value)

    def test_remove_discards_one_draft_and_keeps_remaining_mutation_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 18, tzinfo=UTC))
            record = registry.create("Quiet Ember")
            transaction = AdventureTurnTransaction.inactive().begin(record)
            transaction = transaction.stage(AdventureEventDraft("discovery", "The crew finds a hatch."))
            transaction = transaction.stage_mutation(
                AdventureMutation(MUTATION_STATE_SET, state_key="location", state_value="chart room"),
                summary="The crew reaches the chart room.",
            )
            transaction = transaction.stage(AdventureEventDraft("choice", "The crew opens it."))
            trimmed = transaction.remove(2)

            self.assertEqual(["discovery", "choice"], [draft.event_type for draft in trimmed.drafts])
            self.assertEqual((), trimmed.mutations)
            self.assertEqual((), trimmed.mutation_draft_indices)
            self.assertEqual("The crew opens it.", trimmed.drafts[1].summary)
            with self.assertRaisesRegex(ValueError, "event number is invalid"):
                trimmed.remove(3)


if __name__ == "__main__":
    unittest.main()
