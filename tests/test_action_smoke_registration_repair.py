import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_initiative import AdventureParticipantRoster
from pipeline.adventure_transcript import AdventureTranscriptRecord, TRANSCRIPT_WRITE_LOCK_FILENAME
from scripts.restore_action_smoke import WORKSPACE_ID, restore


class ActionSmokeRepairTests(unittest.TestCase):
    def _orphan(self, root):
        registry = AdventureRegistry(root)
        record = registry.create("Action Smoke")
        self.assertEqual(WORKSPACE_ID, record.adventure_id)
        registry.configure_participant_roster(record, AdventureParticipantRoster(record.adventure_id, ()))
        registry.create("Other Carrier")
        raw = json.loads(registry.registry_path.read_text())
        raw["adventures"] = [item for item in raw["adventures"] if item["adventure_id"] != WORKSPACE_ID]
        registry.registry_path.write_text(json.dumps(raw), encoding="utf-8")
        return registry, root / WORKSPACE_ID

    def test_preview_is_read_only_and_apply_backs_up_without_rewriting_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, workspace = self._orphan(root)
            original = registry.registry_path.read_bytes()
            manifest = (workspace / "manifest.json").read_bytes()
            transcript = (json.dumps(AdventureTranscriptRecord(
                1, "AT-000001", "user", "A synthetic repair fixture.", "2026-10-09T00:00:00+00:00",
            ).to_dict()) + "\n").encode("utf-8")
            (workspace / "transcript.jsonl").write_bytes(transcript)
            before = set(root.iterdir())
            self.assertIn("Preview passed", restore(root))
            self.assertEqual(before, set(root.iterdir()))
            self.assertEqual(original, registry.registry_path.read_bytes())
            self.assertIn("Restored", restore(root, apply=True))
            self.assertEqual(["Action Smoke", "Other Carrier"], [item.title for item in registry.list()])
            self.assertEqual(manifest, (workspace / "manifest.json").read_bytes())
            self.assertEqual(transcript, (workspace / "transcript.jsonl").read_bytes())
            backups = list((root / "_registration_backups").iterdir())
            self.assertEqual(1, len(backups))
            self.assertEqual(original, (backups[0] / "registry.json").read_bytes())
            self.assertEqual(manifest, (backups[0] / "manifest.json").read_bytes())
            self.assertEqual(transcript, (backups[0] / "transcript.jsonl").read_bytes())
            repaired = registry.registry_path.read_bytes()
            self.assertIn("already registered", restore(root, apply=True))
            self.assertEqual(repaired, registry.registry_path.read_bytes())
            self.assertEqual(backups, list((root / "_registration_backups").iterdir()))

    def test_persisted_transcript_lock_is_preserved_and_backed_up(self):
        for lock_bytes in (b"", b"\0"):
            with self.subTest(lock_bytes=lock_bytes), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry, workspace = self._orphan(root)
                lock_path = workspace / TRANSCRIPT_WRITE_LOCK_FILENAME
                lock_path.write_bytes(lock_bytes)
                manifest = (workspace / "manifest.json").read_bytes()
                original = registry.registry_path.read_bytes()
                self.assertIn("Preview passed", restore(root))
                self.assertEqual(original, registry.registry_path.read_bytes())
                self.assertFalse((root / "_registration_backups").exists())
                self.assertEqual(lock_bytes, lock_path.read_bytes())
                self.assertIn("Restored", restore(root, apply=True))
                self.assertEqual(lock_bytes, lock_path.read_bytes())
                self.assertEqual(manifest, (workspace / "manifest.json").read_bytes())
                backup = next((root / "_registration_backups").iterdir())
                self.assertEqual(lock_bytes, (backup / TRANSCRIPT_WRITE_LOCK_FILENAME).read_bytes())
                self.assertIn("already registered", restore(root, apply=True))

    def test_bad_manifest_roster_transcript_and_unexpected_files_fail_without_write(self):
        for failure in ("identity", "roster", "transcript", "events", "hidden", "lock_directory"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry, workspace = self._orphan(root)
                manifest_path = workspace / "manifest.json"
                raw = json.loads(manifest_path.read_text())
                if failure == "identity":
                    raw["title"] = "Different World"
                elif failure == "roster":
                    raw["participant_roster"] = {"schema_version": 999}
                elif failure == "transcript":
                    (workspace / "transcript.jsonl").write_text('{"bad":true}\n')
                elif failure == "events":
                    (workspace / "events.jsonl").write_text("")
                elif failure == "hidden":
                    (workspace / ".unexpected.lock").write_text("")
                else:
                    (workspace / TRANSCRIPT_WRITE_LOCK_FILENAME).mkdir()
                manifest_path.write_text(json.dumps(raw))
                original = registry.registry_path.read_bytes()
                with self.assertRaises(ValueError):
                    restore(root, apply=True)
                self.assertEqual(original, registry.registry_path.read_bytes())
                self.assertFalse((root / "_registration_backups").exists())

    def test_changed_transcript_lock_aborts_replace_and_keeps_backup(self):
        import scripts.restore_action_smoke as helper

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, workspace = self._orphan(root)
            lock_path = workspace / TRANSCRIPT_WRITE_LOCK_FILENAME
            lock_path.write_bytes(b"")
            original = registry.registry_path.read_bytes()
            original_reader = helper._read
            reads = []

            def changed_read(path):
                if path == lock_path:
                    reads.append(path)
                    if len(reads) == 2:
                        path.write_bytes(b"\0")
                return original_reader(path)

            with patch.object(helper, "_read", side_effect=changed_read), patch.object(helper.os, "replace") as replacement:
                with self.assertRaisesRegex(ValueError, "inputs changed"):
                    restore(root, apply=True)
                replacement.assert_not_called()
            self.assertEqual(original, registry.registry_path.read_bytes())
            self.assertEqual(b"\0", lock_path.read_bytes())
            backup = next((root / "_registration_backups").iterdir())
            self.assertEqual(b"", (backup / TRANSCRIPT_WRITE_LOCK_FILENAME).read_bytes())
            self.assertEqual([], list(root.glob(".registration-*")))

    def test_changed_registry_aborts_replace_and_keeps_backup(self):
        import scripts.restore_action_smoke as helper

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry, _ = self._orphan(root)
            original = registry.registry_path.read_bytes()
            original_reader = helper._read
            reads = []
            changed = original + b"\n"

            def changed_read(path):
                if path == registry.registry_path:
                    reads.append(path)
                    if len(reads) == 2:
                        path.write_bytes(changed)
                return original_reader(path)

            with patch.object(helper, "_read", side_effect=changed_read), patch.object(helper.os, "replace") as replacement:
                with self.assertRaisesRegex(ValueError, "inputs changed"):
                    restore(root, apply=True)
                replacement.assert_not_called()
            self.assertEqual(changed, registry.registry_path.read_bytes())
            backup = next((root / "_registration_backups").iterdir())
            self.assertEqual(original, (backup / "registry.json").read_bytes())
            self.assertEqual([], list(root.glob(".registration-*")))

    def test_duplicate_json_and_conflicting_registered_identity_fail_closed(self):
        for failure in ("duplicates", "conflict"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry, _ = self._orphan(root)
                if failure == "duplicates":
                    registry.registry_path.write_text('{"schema_version":1,"schema_version":1,"adventures":[]}')
                else:
                    raw = json.loads(registry.registry_path.read_text())
                    raw["adventures"].append({"adventure_id": WORKSPACE_ID, "title": "Wrong Title", "created_at": "different"})
                    registry.registry_path.write_text(json.dumps(raw))
                original = registry.registry_path.read_bytes()
                with self.assertRaises(ValueError):
                    restore(root, apply=True)
                self.assertEqual(original, registry.registry_path.read_bytes())
                self.assertFalse((root / "_registration_backups").exists())


if __name__ == "__main__":
    unittest.main()
