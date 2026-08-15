import sys
import types
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.persona_development import PersonaDevelopmentState
from pipeline.persona_runtime import PersonaRuntimeRegistry, PersonaRuntimeState
from pipeline.persona_state import DynamicTraits, PersonaState
from pipeline.relationship import RelationshipState


def persona(persona_id):
    return PersonaState(persona_id, persona_id.title(), f"{persona_id} prompt")


class PersonaRuntimeTests(unittest.TestCase):
    def test_registry_seeds_and_isolates_persona_namespaces(self):
        registry = PersonaRuntimeRegistry()
        murr = registry.ensure(persona("murr"))
        nova = registry.ensure(persona("nova"))

        self.assertEqual(murr.persona_id, "murr")
        self.assertEqual(nova.persona_id, "nova")
        self.assertEqual(murr.development_state.interests, ())
        self.assertIs(registry.ensure(persona("murr")), murr)

    def test_replacement_preserves_one_persona_without_leaking_to_another(self):
        registry = PersonaRuntimeRegistry()
        murr = registry.ensure(persona("murr"))
        registry.ensure(persona("nova"))
        changed_persona = replace(murr.persona_state, dynamic_traits=DynamicTraits(warmth=0.8))
        changed_development = PersonaDevelopmentState.empty("murr").record_interest(
            "Rust", observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        registry.replace(PersonaRuntimeState(changed_persona, changed_development))

        self.assertEqual(registry.snapshot("murr").persona_state.dynamic_traits.warmth, 0.8)
        self.assertEqual(registry.snapshot("murr").development_state.interests[0].concept, "Rust")
        self.assertEqual(registry.snapshot("nova").persona_state.dynamic_traits.warmth, 0.5)
        self.assertEqual(registry.snapshot("nova").development_state.interests, ())

    def test_state_rejects_mismatched_persona_ids(self):
        with self.assertRaises(ValueError):
            PersonaRuntimeState(persona("murr"), PersonaDevelopmentState.empty("nova"))

    def test_relationship_snapshots_are_persona_local_and_subject_stable(self):
        registry = PersonaRuntimeRegistry()
        murr = registry.ensure(persona("murr"))
        nova = registry.ensure(persona("nova"))
        first = RelationshipState("murr", "user", familiarity=0.2, trust=0.6, confidence=0.1)
        updated = RelationshipState("murr", "user", familiarity=0.3, trust=0.7, confidence=0.2)

        registry.replace(murr.with_relationship_state(first).with_relationship_state(updated))

        self.assertEqual(registry.snapshot("murr").relationship_states, (updated,))
        self.assertEqual(registry.snapshot("nova").relationship_states, ())
        with self.assertRaises(ValueError):
            murr.with_relationship_state(RelationshipState("nova", "user"))

    def test_public_snapshot_is_bounded_and_does_not_create_state(self):
        registry = PersonaRuntimeRegistry()
        self.assertIsNone(registry.public_snapshot("murr"))
        runtime = registry.ensure(persona("murr")).with_relationship_state(
            RelationshipState("murr", "user", familiarity=0.2, trust=0.6, confidence=0.1)
        )
        registry.replace(runtime)

        snapshot = registry.public_snapshot("murr")

        self.assertEqual(snapshot["persona_id"], "murr")
        self.assertEqual(snapshot["development"]["interest_count"], 0)
        self.assertEqual(snapshot["real_world_relationship_count"], 1)
        self.assertEqual(snapshot["storage"], "restart_ephemeral")
        self.assertNotIn("static_identity", snapshot)
        self.assertNotIn("user", str(snapshot))


if __name__ == "__main__":
    unittest.main()
