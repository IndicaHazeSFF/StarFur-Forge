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
from pipeline.adventure_turn_candidates import (
    AdventureTurnCandidateSelection,
    parse_untrusted_adventure_turn_candidates,
)
from pipeline.adventure_turn_mutation_candidate_inbox import AdventureTurnMutationCandidateSelection
from pipeline.adventure_turn_mutation_candidates import parse_untrusted_adventure_turn_mutation_candidates
from pipeline.adventure_turn_provenance import AdventureTurnGenerationProvenance


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

    def test_explicitly_selected_ordinary_candidate_can_stage_but_cannot_write_itself(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 18, tzinfo=UTC))
            record = registry.create("Quiet Ember")
            candidate = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery",
                    "summary": "The crew finds a brass key.",
                    "confidence": 0.8,
                }],
            }).candidates[0]
            selection = AdventureTurnCandidateSelection("TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", candidate)
            transaction = AdventureTurnTransaction.inactive().begin(record).stage_candidate(selection)
            log = AdventureEventLog(registry, record)

            self.assertEqual("The crew finds a brass key.", transaction.drafts[0].summary)
            self.assertEqual([], log.events())
            with self.assertRaisesRegex(TypeError, "AdventureTurnCandidate"):
                transaction.stage_candidate(object())

    def test_candidate_staging_is_idempotent_and_removal_allows_an_explicit_restage(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 25, tzinfo=UTC))
            record = registry.create("Quiet Ember")
            candidate = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery",
                    "summary": "The crew finds a brass key.",
                    "confidence": 0.8,
                }],
            }).candidates[0]
            selection = AdventureTurnCandidateSelection("TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", candidate)
            transaction = AdventureTurnTransaction.inactive().begin(record).stage_candidate(selection)
            duplicate = transaction.stage_candidate(selection)

            self.assertEqual(transaction, duplicate)
            self.assertEqual(((0, "TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "TC-001"),), duplicate.candidate_draft_ids)
            removed = duplicate.remove(1)
            self.assertEqual((), removed.candidate_draft_ids)
            self.assertEqual(1, len(removed.stage_candidate(selection).drafts))

    def test_distinct_generation_batches_can_stage_their_own_tc_001_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 25, tzinfo=UTC)).create("Quiet Ember")
            first = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "discovery", "summary": "A brass key is found.", "confidence": 0.8}],
            }).candidates[0]
            second = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{"event_type": "discovery", "summary": "A silver key is found.", "confidence": 0.8}],
            }).candidates[0]
            first_selection = AdventureTurnCandidateSelection("TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", first)
            second_selection = AdventureTurnCandidateSelection("TG-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", second)

            transaction = AdventureTurnTransaction.inactive().begin(record).stage_candidate(first_selection)
            transaction = transaction.stage_candidate(second_selection)

            self.assertEqual(["A brass key is found.", "A silver key is found."], [draft.summary for draft in transaction.drafts])
            self.assertEqual(
                ((0, first_selection.generation_id, "TC-001"), (1, second_selection.generation_id, "TC-001")),
                transaction.candidate_draft_ids,
            )

    def test_reviewed_typed_candidate_stages_only_through_core_summary_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 26, tzinfo=UTC))
            record = registry.create("Quiet Ember")
            candidate = parse_untrusted_adventure_turn_mutation_candidates({
                "schema_version": 1,
                "candidates": [{
                    "mutation": {"kind": "state_set", "key": "current_location", "value": "engine room"},
                    "confidence": 0.8,
                }],
            }).candidates[0]
            provenance = AdventureTurnGenerationProvenance(
                "TG-cccccccccccccccccccccccccccccccc", "adventure_turn_mutation_generation",
                "Ollama", "qwen3:8b", 0, (), "TM-001",
            )
            selection = AdventureTurnMutationCandidateSelection(provenance.generation_id, candidate, provenance)

            transaction = AdventureTurnTransaction.inactive().begin(record).stage_mutation_candidate(selection)

            self.assertEqual("state_change", transaction.drafts[0].event_type)
            self.assertEqual("Generated state: current_location = engine room.", transaction.drafts[0].summary)
            self.assertEqual(provenance, transaction.drafts[0].generation_provenance)
            self.assertEqual(((0, provenance.generation_id, "TM-001"),), transaction.candidate_draft_ids)
            self.assertEqual(transaction, transaction.stage_mutation_candidate(selection))

    def test_generated_resource_candidate_requires_matching_catalog_validated_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            record = AdventureRegistry(directory).create("Quiet Ember")
            candidate = parse_untrusted_adventure_turn_mutation_candidates({
                "schema_version": 1,
                "candidates": [{
                    "mutation": {"kind": "resource_change", "id": "fuel", "operation": "increment", "value": 10},
                    "confidence": 0.8,
                }],
            }).candidates[0]
            provenance = AdventureTurnGenerationProvenance(
                "TG-dddddddddddddddddddddddddddddddd", "adventure_turn_mutation_generation",
                "Ollama", "qwen3:8b", 0, (), "TM-001",
            )
            selection = AdventureTurnMutationCandidateSelection(provenance.generation_id, candidate, provenance)
            transaction = AdventureTurnTransaction.inactive().begin(record)

            with self.assertRaisesRegex(ValueError, "catalog-validated"):
                transaction.stage_mutation_candidate(selection)
            with self.assertRaisesRegex(ValueError, "does not match"):
                transaction.stage_mutation_candidate(selection, resource_operation=AdventureResourceOperation("fuel", "set", 10))
            staged = transaction.stage_mutation_candidate(
                selection, resource_operation=AdventureResourceOperation("fuel", "increment", 10),
            )
            self.assertEqual("resource_change", staged.drafts[0].event_type)
            self.assertEqual(provenance, staged.drafts[0].generation_provenance)


if __name__ == "__main__":
    unittest.main()
