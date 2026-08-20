import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_resources import (
    AdventureResourceCatalog,
    AdventureResourceDefinition,
    AdventureResourceError,
)


class AdventureResourceDefinitionTests(unittest.TestCase):
    def test_generic_scenario_resources_are_validated_without_game_specific_core_names(self):
        fuel = AdventureResourceDefinition(
            "fuel", "Fuel", "integer", minimum=0, maximum=100,
            permitted_operations=frozenset({"set", "decrement"}),
        )
        credits = AdventureResourceDefinition("credits", "Credits", "decimal", minimum="0", maximum="9999.50")
        door = AdventureResourceDefinition("airlock", "Airlock", "enum", allowed_values=("sealed", "open"))
        medkit = AdventureResourceDefinition("medkit", "Medkit", "inventory")
        slot = AdventureResourceDefinition("primary_slot", "Primary slot", "equipment", visibility="hidden")
        objective = AdventureResourceDefinition("repair_engine", "Repair engine", "objective")
        location = AdventureResourceDefinition("current_location", "Current location", "location")
        clock = AdventureResourceDefinition("shift_clock", "Shift clock", "clock")
        flag = AdventureResourceDefinition("alarm", "Alarm", "flag")
        catalog = AdventureResourceCatalog.from_definitions(
            (fuel, credits, door, medkit, slot, objective, location, clock, flag)
        )

        self.assertEqual("fuel", catalog.resolve("FUEL").resource_id)
        self.assertEqual(Decimal("9999.50"), catalog.resolve("credits").maximum)
        self.assertEqual(("sealed", "open"), catalog.resolve("airlock").allowed_values)
        self.assertEqual(("add", "remove"), catalog.resolve("medkit").public_definition()["permitted_operations"])
        self.assertEqual("hidden", catalog.resolve("primary_slot").visibility)

    def test_invalid_bounds_operations_and_duplicate_ids_fail_closed(self):
        with self.assertRaisesRegex(AdventureResourceError, "require minimum and maximum"):
            AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0)
        with self.assertRaisesRegex(AdventureResourceError, "cannot exceed"):
            AdventureResourceDefinition("fuel", "Fuel", "decimal", minimum="9", maximum="2")
        with self.assertRaisesRegex(AdventureResourceError, "only for integer or decimal"):
            AdventureResourceDefinition("alarm", "Alarm", "flag", minimum=0, maximum=1)
        with self.assertRaisesRegex(AdventureResourceError, "not permitted"):
            AdventureResourceDefinition("medkit", "Medkit", "inventory", permitted_operations=frozenset({"equip"}))
        fuel = AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=1)
        with self.assertRaisesRegex(AdventureResourceError, "unique"):
            AdventureResourceCatalog((fuel, AdventureResourceDefinition("FUEL", "Duplicate", "integer", minimum=0, maximum=1)))

    def test_catalog_is_metadata_only_and_unknown_resources_fail(self):
        catalog = AdventureResourceCatalog((
            AdventureResourceDefinition("power", "Power", "integer", minimum=0, maximum=5),
        ))
        self.assertEqual((), tuple(catalog.resolve("power").public_definition()["allowed_values"] or ()))
        with self.assertRaisesRegex(AdventureResourceError, "not declared"):
            catalog.resolve("ammo")

    def test_json_compatible_catalog_round_trip_preserves_decimal_bounds_and_operations(self):
        catalog = AdventureResourceCatalog((
            AdventureResourceDefinition("credits", "Credits", "decimal", minimum="0", maximum="99.5"),
            AdventureResourceDefinition("door", "Door", "enum", allowed_values=("sealed", "open")),
        ))
        restored = AdventureResourceCatalog.from_dict(catalog.to_dict())
        self.assertEqual(catalog, restored)
        with self.assertRaisesRegex(AdventureResourceError, "schema"):
            AdventureResourceCatalog.from_dict({"schema_version": 2, "definitions": []})


if __name__ == "__main__":
    unittest.main()
