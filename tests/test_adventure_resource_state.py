import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition
from pipeline.adventure_resource_state import (
    AdventureResourceOperation,
    AdventureResourceState,
    AdventureResourceStateError,
)


def catalog():
    return AdventureResourceCatalog((
        AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
        AdventureResourceDefinition("credits", "Credits", "decimal", minimum=0, maximum="99.5"),
        AdventureResourceDefinition("airlock", "Airlock", "enum", allowed_values=("sealed", "open")),
        AdventureResourceDefinition("alarm", "Alarm", "flag"),
        AdventureResourceDefinition("medkit", "Medkit", "inventory"),
        AdventureResourceDefinition("primary_slot", "Primary", "equipment", visibility="hidden"),
        AdventureResourceDefinition("repair_engine", "Repair Engine", "objective"),
        AdventureResourceDefinition("location", "Location", "location"),
        AdventureResourceDefinition("clock", "Clock", "clock"),
    ))


class AdventureResourceStateTests(unittest.TestCase):
    def test_defaults_and_catalog_validated_operations_are_deterministic(self):
        state = AdventureResourceState.initial(catalog())
        self.assertEqual(0, state.value_for("fuel"))
        self.assertEqual(Decimal("0"), state.value_for("credits"))
        self.assertEqual("sealed", state.value_for("airlock"))
        self.assertFalse(state.value_for("alarm"))
        self.assertEqual((), state.value_for("medkit"))
        self.assertIsNone(state.value_for("primary_slot"))
        self.assertEqual("inactive", state.value_for("repair_engine"))

        state = state.apply(AdventureResourceOperation("alarm", "set", True))
        self.assertTrue(state.value_for("alarm"))
        state = state.apply(AdventureResourceOperation("alarm", "set", False))
        self.assertFalse(state.value_for("alarm"))

        for operation in (
            AdventureResourceOperation("fuel", "increment", 40),
            AdventureResourceOperation("credits", "increment", "2.5"),
            AdventureResourceOperation("airlock", "set", "OPEN"),
            AdventureResourceOperation("alarm", "activate"),
            AdventureResourceOperation("medkit", "add", ("repair_kit", 2)),
            AdventureResourceOperation("primary_slot", "equip", "brass key"),
            AdventureResourceOperation("repair_engine", "activate"),
            AdventureResourceOperation("location", "set", "engine room"),
            AdventureResourceOperation("clock", "increment", 15),
        ):
            state = state.apply(operation)
        self.assertEqual(40, state.value_for("fuel"))
        self.assertEqual(Decimal("2.5"), state.value_for("credits"))
        self.assertEqual("open", state.value_for("airlock"))
        self.assertTrue(state.value_for("alarm"))
        self.assertEqual((("repair_kit", 2),), state.value_for("medkit"))
        self.assertEqual("brass key", state.value_for("primary_slot"))
        self.assertEqual("active", state.value_for("repair_engine"))
        self.assertEqual("engine room", state.value_for("location"))
        self.assertEqual(Decimal("15"), state.value_for("clock"))
        self.assertNotIn("primary_slot", state.public_values())

    def test_invalid_or_out_of_bounds_operations_fail_without_mutating_prior_state(self):
        state = AdventureResourceState.initial(catalog())
        with self.assertRaisesRegex(AdventureResourceStateError, "outside declared bounds"):
            state.apply(AdventureResourceOperation("fuel", "decrement", 1))
        with self.assertRaisesRegex(AdventureResourceStateError, "not permitted"):
            state.apply(AdventureResourceOperation("fuel", "add", ("fuel", 1)))
        with self.assertRaisesRegex(AdventureResourceStateError, "not declared"):
            state.apply(AdventureResourceOperation("ammo", "set", 1))
        with self.assertRaisesRegex(AdventureResourceStateError, "exceeds available"):
            state.apply(AdventureResourceOperation("medkit", "remove", ("repair_kit", 1)))
        with self.assertRaisesRegex(AdventureResourceStateError, "enum value is not declared"):
            state.apply(AdventureResourceOperation("airlock", "set", "broken"))
        with self.assertRaisesRegex(AdventureResourceStateError, "requires an item"):
            state.apply(AdventureResourceOperation("primary_slot", "equip"))
        self.assertEqual(0, state.value_for("fuel"))
        self.assertEqual((), state.value_for("medkit"))

    def test_complete_state_requires_exactly_one_valid_value_per_declared_resource(self):
        definitions = catalog()
        initial = AdventureResourceState.initial(definitions)
        values = dict(initial.values)
        values.pop("clock")
        with self.assertRaisesRegex(AdventureResourceStateError, "exactly"):
            AdventureResourceState.from_values(definitions, values)
        values = dict(initial.values)
        values["fuel"] = 101
        with self.assertRaisesRegex(AdventureResourceStateError, "outside declared bounds"):
            AdventureResourceState.from_values(definitions, values)


if __name__ == "__main__":
    unittest.main()
