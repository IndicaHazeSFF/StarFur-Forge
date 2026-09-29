import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition
from pipeline.adventure_session import AdventureSessionState
from pipeline.adventure_mutation import AdventureMutation, MUTATION_RESOURCE_CHANGE
from pipeline.adventure_turn_resource_policy import (
    AdventureTurnResourcePolicyError,
    AdventureTurnResourcePolicyView,
    MAX_RESOURCE_CANDIDATE_POLICY_ENTRIES,
)


class AdventureTurnResourcePolicyTests(unittest.TestCase):
    def _record(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return AdventureRegistry(
            directory.name, now=lambda: datetime(2026, 9, 27, tzinfo=UTC),
        ).create("Quiet Ember")

    def test_public_catalog_metadata_is_bounded_and_hidden_definitions_never_render(self):
        catalog = AdventureResourceCatalog((
            AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
            AdventureResourceDefinition("mode", "Mode", "enum", allowed_values=("silent", "normal")),
            AdventureResourceDefinition("primary_slot", "Primary slot", "equipment", visibility="hidden"),
        ))

        view = AdventureTurnResourcePolicyView.from_catalog(catalog)
        rendered = view.render()

        self.assertEqual(("fuel", "mode"), tuple(entry.resource_id for entry in view.entries))
        self.assertIn("fuel [integer]; operations: decrement, increment, set", rendered)
        self.assertIn("mode [enum]; operations: set; allowed values: silent, normal", rendered)
        self.assertNotIn("primary_slot", rendered)
        self.assertNotIn("Primary slot", rendered)
        self.assertNotIn("100", rendered)

    def test_session_projection_requires_a_mount_and_never_reads_resource_values(self):
        with self.assertRaisesRegex(ValueError, "mounted"):
            AdventureTurnResourcePolicyView.from_session(AdventureSessionState.unmounted())

        record = self._record()
        session = AdventureSessionState(
            record=record,
            resource_catalog=AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
            )),
        )
        rendered = AdventureTurnResourcePolicyView.from_session(session).render()

        self.assertIn("fuel", rendered)
        self.assertNotIn("current", rendered.casefold())

    def test_policy_limit_is_deterministic_by_resource_identifier(self):
        catalog = AdventureResourceCatalog(tuple(
            AdventureResourceDefinition(
                f"resource_{index:02d}", f"Resource {index}", "flag",
            )
            for index in reversed(range(MAX_RESOURCE_CANDIDATE_POLICY_ENTRIES + 2))
        ))

        view = AdventureTurnResourcePolicyView.from_catalog(catalog)

        self.assertEqual(MAX_RESOURCE_CANDIDATE_POLICY_ENTRIES, len(view.entries))
        self.assertEqual(
            tuple(f"resource_{index:02d}" for index in range(MAX_RESOURCE_CANDIDATE_POLICY_ENTRIES)),
            tuple(entry.resource_id for entry in view.entries),
        )

    def test_candidate_eligibility_accepts_only_public_declared_operations(self):
        catalog = AdventureResourceCatalog((
            AdventureResourceDefinition(
                "alarm", "Alarm", "enum", allowed_values=("inactive", "active"),
            ),
            AdventureResourceDefinition(
                "hidden_code", "Hidden code", "flag", visibility="hidden",
            ),
        ))
        view = AdventureTurnResourcePolicyView.from_catalog(catalog)
        allowed = AdventureMutation(
            kind=MUTATION_RESOURCE_CHANGE, resource_id="alarm", resource_operation="set", resource_value="active",
        )
        self.assertIs(allowed, view.validate_candidate(allowed))

        with self.assertRaisesRegex(AdventureTurnResourcePolicyError, "not a declared public"):
            view.validate_candidate(AdventureMutation(
                kind=MUTATION_RESOURCE_CHANGE, resource_id="hidden_code", resource_operation="activate", resource_value=True,
            ))
        with self.assertRaisesRegex(AdventureTurnResourcePolicyError, "enum value"):
            view.validate_candidate(AdventureMutation(
                kind=MUTATION_RESOURCE_CHANGE, resource_id="alarm", resource_operation="set", resource_value="unknown",
            ))

    def test_portable_enum_schema_is_public_bounded_and_its_validator_is_narrow(self):
        catalog = AdventureResourceCatalog((
            AdventureResourceDefinition("airlock", "Airlock", "enum", allowed_values=("sealed", "open")),
            AdventureResourceDefinition("alarm", "Alarm", "flag"),
            AdventureResourceDefinition("secret_mode", "Secret mode", "enum", visibility="hidden", allowed_values=("a", "b")),
        ))
        view = AdventureTurnResourcePolicyView.from_catalog(catalog)
        schema = view.portable_enum_candidate_schema()
        mutation_properties = schema["properties"]["candidates"]["items"]["properties"]["mutation"]["properties"]
        self.assertEqual(["airlock"], mutation_properties["id"]["enum"])
        self.assertEqual(["open", "sealed"], mutation_properties["value"]["enum"])
        self.assertNotIn("secret_mode", repr(schema))
        self.assertIsNotNone(view.validate_portable_enum_candidate(AdventureMutation(
            kind=MUTATION_RESOURCE_CHANGE, resource_id="airlock", resource_operation="set", resource_value="open",
        )))
        with self.assertRaisesRegex(AdventureTurnResourcePolicyError, "portable enum"):
            view.validate_portable_enum_candidate(AdventureMutation(
                kind=MUTATION_RESOURCE_CHANGE, resource_id="alarm", resource_operation="set", resource_value=True,
            ))
        with self.assertRaisesRegex(AdventureTurnResourcePolicyError, "portable public enum"):
            AdventureTurnResourcePolicyView.from_catalog(AdventureResourceCatalog((
                AdventureResourceDefinition("alarm", "Alarm", "flag"),
            ))).portable_enum_candidate_schema()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
