import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.adventure_registry import AdventureNotFoundError, AdventureRegistry, AdventureRegistryError
from pipeline.adventure_initiative import AdventureParticipant, AdventureParticipantRoster
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition


class AdventureRegistryTests(unittest.TestCase):
    def _registry(self, root):
        return AdventureRegistry(root, now=lambda: datetime(2026, 8, 15, 12, 0, tzinfo=UTC))

    def test_create_writes_only_registry_and_workspace_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            record = registry.create("  Quiet   Ember ")
            workspace = registry.workspace_path(record.adventure_id)

            self.assertEqual("Quiet Ember", record.title)
            self.assertTrue(registry.registry_path.exists())
            self.assertTrue((workspace / "manifest.json").exists())
            self.assertFalse((workspace / "events.jsonl").exists())
            self.assertFalse((workspace / "adventure.sqlite").exists())
            self.assertFalse((workspace / "semantic_index").exists())
            self.assertEqual([record], registry.list())

    def test_title_resolution_is_exact_and_never_creates_a_world(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            created = registry.create("Quiet Ember")
            self.assertEqual(created, registry.resolve_title(" quiet ember "))
            with self.assertRaises(AdventureNotFoundError):
                registry.resolve_title("Quiet")
            self.assertEqual([created], registry.list())

    def test_duplicate_title_requires_explicit_resume_later(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            registry.create("Quiet Ember")
            with self.assertRaisesRegex(AdventureRegistryError, "resume it explicitly"):
                registry.create("quiet ember")

    def test_invalid_titles_do_not_create_a_root_or_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "adventures"
            registry = self._registry(root)
            with self.assertRaises(AdventureRegistryError):
                registry.create("   ")
            with self.assertRaises(AdventureRegistryError):
                registry.create("x" * 121)
            self.assertFalse(root.exists())

    def test_resource_catalog_is_immutable_manifest_metadata_before_event_log_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            record = registry.create("Quiet Ember")
            catalog = AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
            ))
            self.assertEqual((), registry.resource_catalog(record).definitions)
            self.assertEqual(catalog, registry.configure_resource_catalog(record, catalog))
            self.assertEqual(catalog, registry.resource_catalog(record))
            self.assertEqual(catalog, registry.configure_resource_catalog(record, catalog))
            different = AdventureResourceCatalog((
                AdventureResourceDefinition("oxygen", "Oxygen", "integer", minimum=0, maximum=100),
            ))
            with self.assertRaisesRegex(AdventureRegistryError, "already configured"):
                registry.configure_resource_catalog(record, different)

    def test_resource_catalog_cannot_be_configured_after_event_log_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            record = registry.create("Quiet Ember")
            (registry.workspace_path(record.adventure_id) / "events.jsonl").write_text("", encoding="utf-8")
            catalog = AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
            ))
            with self.assertRaisesRegex(AdventureRegistryError, "event log exists"):
                registry.configure_resource_catalog(record, catalog)

    def test_participant_roster_is_immutable_manifest_metadata_before_event_log_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            record = registry.create("Quiet Ember")
            roster = AdventureParticipantRoster(record.adventure_id, (
                AdventureParticipant(
                    "murr", "Murr", "persona",
                    f"adventure:{record.adventure_id}:participant:murr",
                ),
            ))
            self.assertEqual((), registry.participant_roster(record).participants)
            self.assertEqual(roster, registry.configure_participant_roster(record, roster))
            self.assertEqual(roster, registry.participant_roster(record))
            self.assertEqual(roster, registry.configure_participant_roster(record, roster))
            different = AdventureParticipantRoster(record.adventure_id, (
                AdventureParticipant(
                    "rook", "Rook", "npc",
                    f"adventure:{record.adventure_id}:participant:rook",
                ),
            ))
            with self.assertRaisesRegex(AdventureRegistryError, "already configured"):
                registry.configure_participant_roster(record, different)

    def test_participant_roster_cannot_be_configured_after_event_log_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(directory)
            record = registry.create("Quiet Ember")
            (registry.workspace_path(record.adventure_id) / "events.jsonl").write_text("", encoding="utf-8")
            roster = AdventureParticipantRoster(record.adventure_id, ())
            with self.assertRaisesRegex(AdventureRegistryError, "event log exists"):
                registry.configure_participant_roster(record, roster)


if __name__ == "__main__":
    unittest.main()
