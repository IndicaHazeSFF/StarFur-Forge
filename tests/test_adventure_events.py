import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.adventure_events import AdventureEvent, AdventureEventDraft, AdventureEventLog, AdventureEventLogError
from pipeline.adventure_mutation import AdventureEventEnvelope, AdventureMutation, MUTATION_STATE_SET
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition
from pipeline.adventure_resource_state import derive_adventure_resource_state


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

    def test_request_identifier_makes_a_batch_retry_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            drafts = (AdventureEventDraft("discovery", "The crew finds a brass compass."),)

            first = log.append_many(drafts, request_id="turn-12345678")
            repeated = log.append_many(drafts, request_id="turn-12345678")

            self.assertEqual(first, repeated)
            self.assertEqual(1, len(log.events()))
            self.assertEqual("turn-12345678", log.events()[0].request_id)
            with self.assertRaisesRegex(AdventureEventLogError, "already used"):
                log.append_many(
                    (AdventureEventDraft("choice", "The crew ignores the compass."),),
                    request_id="turn-12345678",
                )
            self.assertEqual(1, len(log.events()))

    def test_workspace_write_guard_blocks_an_independent_log_handle(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record, first = self._log(directory)
            second = AdventureEventLog(registry, record)

            with first._write_guard():
                with self.assertRaisesRegex(AdventureEventLogError, "workspace is busy"):
                    second.append("discovery", "This must wait for the other writer.")
                self.assertEqual([], first.events())

            event = second.append("discovery", "The lock has been released.")
            self.assertEqual("AE-000001", event.event_id)

    def test_existing_legacy_lock_file_contents_do_not_block_a_recovered_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            log.lock_path.write_text('{"pid":999999}\n', encoding="utf-8")

            event = log.append("discovery", "The old lock owner is gone.")

            self.assertEqual("AE-000001", event.event_id)
            self.assertTrue(log.lock_path.exists())

    def test_valid_pending_log_extension_is_recovered_before_the_next_append(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            first = log.append("discovery", "The crew finds an old signal.")
            recovered = AdventureEvent(
                sequence=2,
                event_id="AE-000002",
                event_type="choice",
                summary="The crew follows the signal.",
                details=None,
                recorded_at="2026-08-17T12:02:00+00:00",
            )
            log.pending_path.write_text(
                log.path.read_text(encoding="utf-8")
                + json.dumps(recovered.__dict__, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )

            appended = log.append("discovery", "The signal leads below deck.")

            self.assertEqual("AE-000003", appended.event_id)
            self.assertEqual([first, recovered, appended], log.events())
            self.assertFalse(log.pending_path.exists())

    def test_invalid_pending_log_fails_closed_without_changing_authoritative_log(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            first = log.append("discovery", "The crew finds an old signal.")
            original_text = log.path.read_text(encoding="utf-8")
            log.pending_path.write_text('{"sequence":2}\n', encoding="utf-8")

            with self.assertRaisesRegex(AdventureEventLogError, "pending event log is invalid"):
                log.append("choice", "This must not be appended.")

            self.assertEqual(original_text, log.path.read_text(encoding="utf-8"))
            self.assertEqual([first], log.events())
            self.assertTrue(log.pending_path.exists())

    def test_conflicting_pending_log_fails_closed_without_overwriting_authoritative_log(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            first = log.append("discovery", "The crew finds an old signal.")
            original_text = log.path.read_text(encoding="utf-8")
            conflicting = AdventureEvent(
                sequence=1,
                event_id="AE-000001",
                event_type="choice",
                summary="The crew abandons the signal.",
                details=None,
                recorded_at=first.recorded_at,
            )
            log.pending_path.write_text(
                json.dumps(conflicting.__dict__, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(AdventureEventLogError, "conflicts with the authoritative"):
                log.recover()

            self.assertEqual(original_text, log.path.read_text(encoding="utf-8"))
            self.assertEqual([first], log.events())
            self.assertTrue(log.pending_path.exists())

    def test_append_repairs_a_manifest_left_at_not_created_after_log_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record, log = self._log(directory)
            first = log.append("discovery", "The crew finds an old signal.")
            manifest_path = registry.workspace_path(record.adventure_id) / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["storage"]["event_log"] = "not_created"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            second = log.append("choice", "The crew follows the signal.")

            repaired = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual([first, second], log.events())
            self.assertEqual("events.jsonl:v1", repaired["storage"]["event_log"])

    def test_manifest_claiming_an_absent_log_fails_closed_before_append(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record, log = self._log(directory)
            manifest_path = registry.workspace_path(record.adventure_id) / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["storage"]["event_log"] = "events.jsonl:v1"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(AdventureEventLogError, "claims an event log that is absent"):
                log.append("discovery", "This must not be appended.")

            self.assertFalse(log.path.exists())

    def test_schema_v1_log_entries_remain_unchanged_on_read_and_append(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            first = log.append("discovery", "The crew finds an old signal.")
            raw_before = json.loads(log.path.read_text(encoding="utf-8").splitlines()[0])

            second = log.append("choice", "The crew follows the signal.")
            raw_after = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(1, raw_before["schema_version"])
            self.assertEqual(raw_before, raw_after[0])
            self.assertEqual([first, second], log.events())

    def test_schema_v2_mutation_entry_projects_through_existing_readers_and_survives_append(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            first = log.append("discovery", "The crew finds an old signal.")
            v2 = AdventureEventEnvelope(
                sequence=2,
                event_id="AE-000002",
                event_type="state_change",
                recorded_at="2026-08-19T12:00:00+00:00",
                summary="The crew reaches the chart room.",
                details="The compass points here.",
                request_id="turn-12345678",
                mutation=AdventureMutation(
                    MUTATION_STATE_SET,
                    state_key="current_location",
                    state_value="chart room",
                ),
            )
            log.path.write_text(
                json.dumps(first.to_dict(), sort_keys=True, separators=(",", ":"))
                + "\n"
                + json.dumps(v2.to_dict(), sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )

            loaded = log.events()
            appended = log.append("choice", "The crew studies the compass.")
            raw = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual("current_location", loaded[1].state_key)
            self.assertEqual("chart room", loaded[1].state_value)
            self.assertEqual(v2.mutation, loaded[1].mutation)
            self.assertEqual([1, 2, 1], [entry["schema_version"] for entry in raw])
            self.assertEqual([first, loaded[1], appended], log.events())

    def test_resource_events_require_the_declared_catalog_and_replay_through_it(self):
        with tempfile.TemporaryDirectory() as directory:
            registry, record, log = self._log(directory)
            catalog = AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
                AdventureResourceDefinition("medkit", "Medkit", "inventory"),
            ))
            registry.configure_resource_catalog(record, catalog)

            fuel = log.append(
                "resource_change", "Fuel reserve increases.",
                resource_id="fuel", resource_operation="increment", resource_value=20,
            )
            kits = log.append(
                "resource_change", "A repair kit is stored.",
                resource_id="medkit", resource_operation="add", resource_value=("repair_kit", 2),
            )
            state = derive_adventure_resource_state(catalog, log.events())

            self.assertEqual("fuel", fuel.resource_id)
            self.assertEqual(20, fuel.resource_value)
            self.assertEqual(["repair_kit", 2], kits.resource_value)
            self.assertEqual(20, state.value_for("fuel"))
            self.assertEqual((("repair_kit", 2),), state.value_for("medkit"))
            with self.assertRaisesRegex(AdventureEventLogError, "resource event is invalid"):
                log.append(
                    "resource_change", "Fuel reserve drops too far.",
                    resource_id="fuel", resource_operation="decrement", resource_value=21,
                )
            self.assertEqual(2, len(log.events()))

    def test_resource_event_is_rejected_when_the_workspace_declares_no_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, log = self._log(directory)
            with self.assertRaisesRegex(AdventureEventLogError, "resource event is invalid"):
                log.append(
                    "resource_change", "This must not persist.",
                    resource_id="fuel", resource_operation="set", resource_value=10,
                )
            self.assertFalse(log.path.exists())


if __name__ == "__main__":
    unittest.main()
