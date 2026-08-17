import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.adventure_events import AdventureEventLog, AdventureEventLogError
from pipeline.adventure_registry import AdventureRegistry


class AdventureEventLogTests(unittest.TestCase):
    def _registry(self, root):
        return AdventureRegistry(root, now=lambda: datetime(2026, 8, 17, 12, 0, tzinfo=UTC))

    def _log(self, root):
        registry = self._registry(root)
        record = registry.create("Quiet Ember")
        log = AdventureEventLog(registry, record, now=lambda: datetime(2026, 8, 17, 12, 1, tzinfo=UTC))
        return registry, record, log

    def test_log_is_lazy_and_appends_validated_replayable_events(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record, log = self._log(directory)
            self.assertEqual([], log.events())
            self.assertFalse(log.path.exists())
            first = log.append("discovery", "  The crew finds an old signal.  ", details="It comes from below deck.")
            second = log.append("promise", "The player promises to investigate the signal.")
            self.assertEqual("AE-000001", first.event_id)
            self.assertEqual("The crew finds an old signal.", first.summary)
            self.assertEqual([first, second], log.events())
            manifest = json.loads((registry.workspace_path(record.adventure_id) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("events.jsonl:v1", manifest["storage"]["event_log"])
            self.assertEqual(2, len(log.path.read_text(encoding="utf-8").splitlines()))

    def test_invalid_event_does_not_create_or_mutate_log(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            with self.assertRaisesRegex(AdventureEventLogError, "unsupported"):
                log.append("ordinary_dialogue", "This must not persist.")
            with self.assertRaisesRegex(AdventureEventLogError, "summary"):
                log.append("choice", " ")
            self.assertFalse(log.path.exists())

    def test_corrupt_or_non_contiguous_log_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            log.path.write_text('{"sequence":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(AdventureEventLogError, "invalid"):
                log.events()

    def test_log_requires_a_current_registry_record(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            record = registry.create("Quiet Ember")
            other_registry = self._registry(Path(directory) / "other")
            with self.assertRaisesRegex(AdventureEventLogError, "not registered"):
                AdventureEventLog(other_registry, record)


if __name__ == "__main__":
    unittest.main()
