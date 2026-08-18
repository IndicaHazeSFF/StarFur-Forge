import tempfile
import unittest
from datetime import UTC, datetime

from pipeline.adventure_events import AdventureEventDraft, AdventureEventLog
from pipeline.adventure_registry import AdventureRegistry
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
            written = log.append_many(transaction.drafts)
            self.assertEqual(["AE-000001", "AE-000002"], [event.event_id for event in written])
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


if __name__ == "__main__":
    unittest.main()
