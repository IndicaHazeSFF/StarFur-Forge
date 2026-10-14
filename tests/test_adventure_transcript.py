from datetime import UTC, datetime
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_transcript import (
    AdventureTranscriptError,
    AdventureTranscriptLog,
    AdventureTranscriptRecord,
    MAX_TRANSCRIPT_TEXT_LENGTH,
)
from pipeline.adventure_registry import AdventureRegistry


class AdventureTranscriptTests(unittest.TestCase):
    def _log(self, root):
        registry = AdventureRegistry(root, now=lambda: datetime(2026, 8, 23, 12, 0, tzinfo=UTC))
        record = registry.create("Quiet Ember")
        return registry, record, AdventureTranscriptLog(
            registry, record, now=lambda: datetime(2026, 8, 23, 12, 1, tzinfo=UTC),
        )

    def test_record_round_trip_keeps_presentation_separate_and_bounded(self):
        record = AdventureTranscriptRecord(
            sequence=1,
            record_id="AT-000001",
            role="narrator",
            text="The brass hatch groans open.\nA cold draft fills the chart room.",
            recorded_at="2026-08-22T12:00:00+00:00",
        )

        self.assertEqual(record, AdventureTranscriptRecord.from_dict(record.to_dict()))
        self.assertEqual("narrator", record.role)
        self.assertNotIn("event_type", record.to_dict())
        self.assertNotIn("mutation", record.to_dict())

    def test_records_reject_invalid_ids_roles_text_and_schema(self):
        base = {
            "sequence": 1,
            "record_id": "AT-000001",
            "role": "user",
            "text": "I inspect the hatch.",
            "recorded_at": "2026-08-22T12:00:00+00:00",
        }
        with self.assertRaisesRegex(AdventureTranscriptError, "identifier does not match"):
            AdventureTranscriptRecord(**(base | {"record_id": "AT-000002"}))
        with self.assertRaisesRegex(AdventureTranscriptError, "role is unsupported"):
            AdventureTranscriptRecord(**(base | {"role": "assistant"}))
        with self.assertRaisesRegex(AdventureTranscriptError, "at most"):
            AdventureTranscriptRecord(**(base | {"text": "x" * (MAX_TRANSCRIPT_TEXT_LENGTH + 1)}))
        with self.assertRaisesRegex(AdventureTranscriptError, "schema is unsupported"):
            AdventureTranscriptRecord(**(base | {"schema_version": 2}))

    def test_from_dict_is_closed_and_does_not_accept_event_fields(self):
        raw = {
            "schema_version": 1,
            "sequence": 1,
            "record_id": "AT-000001",
            "role": "user",
            "text": "I inspect the hatch.",
            "recorded_at": "2026-08-22T12:00:00+00:00",
            "source": "core_explicit",
            "event_type": "discovery",
        }
        with self.assertRaisesRegex(AdventureTranscriptError, "fields are invalid"):
            AdventureTranscriptRecord.from_dict(raw)

    def test_log_is_lazy_append_only_and_does_not_create_an_event_log(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record, log = self._log(directory)
            workspace = registry.workspace_path(record.adventure_id)

            self.assertEqual([], log.records())
            self.assertFalse(log.path.exists())
            first = log.append("user", "I inspect the brass hatch.")
            second = log.append("narrator", "The hatch shudders but stays sealed.")

            self.assertEqual("AT-000001", first.record_id)
            self.assertEqual([first, second], log.records())
            self.assertFalse((workspace / "events.jsonl").exists())
            self.assertFalse((workspace / "manifest.json").read_text(encoding="utf-8").find("transcript") >= 0)

    def test_append_many_writes_one_validated_presentation_pair_or_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            _registry, _record, log = self._log(directory)

            pair = log.append_many((
                ("user", "I offer Murr the brass key."),
                ("narrator", "Murr suggests checking its teeth first."),
            ))
            self.assertEqual(("AT-000001", "AT-000002"), tuple(item.record_id for item in pair))
            self.assertEqual(["user", "narrator"], [item.role for item in log.records()])

            with self.assertRaisesRegex(AdventureTranscriptError, "role is unsupported"):
                log.append_many((("user", "This must not persist."), ("assistant", "Bad role.")))
            self.assertEqual(2, len(log.records()))

    def test_invalid_transcript_fails_closed_and_live_lock_blocks_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record, first = self._log(directory)
            second = AdventureTranscriptLog(registry, record)
            first.path.write_text('{"sequence":2}\n', encoding="utf-8")

            with self.assertRaisesRegex(AdventureTranscriptError, "invalid"):
                first.append("user", "This must not replace the malformed log.")
            self.assertEqual('{"sequence":2}\n', first.path.read_text(encoding="utf-8"))

            first.path.unlink()
            with first._write_guard():
                with self.assertRaisesRegex(AdventureTranscriptError, "busy"):
                    second.append("user", "This must wait.")
            self.assertEqual("AT-000001", second.append("user", "The lock is free.").record_id)


if __name__ == "__main__":
    unittest.main()
