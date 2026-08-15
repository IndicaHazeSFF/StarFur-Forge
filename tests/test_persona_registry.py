import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.persona import NEUTRAL_PERSONA
from pipeline.persona_registry import PersonaPackage, PersonaRegistry, load_persona_package


class PersonaRegistryTests(unittest.TestCase):
    def test_packages_are_fallback_safe_and_public_metadata_excludes_prompt(self):
        package = load_persona_package("missing-persona.md", persona_id="murr", display_name="Murr")

        self.assertEqual(package.persona.render_prompt(), NEUTRAL_PERSONA)
        self.assertEqual(package.initial_state.persona_id, "murr")
        self.assertEqual(package.public_dict(), {"persona_id": "murr", "display_name": "Murr"})
        self.assertNotIn("prompt", package.public_dict())

    def test_registry_has_deterministic_lookup_and_no_duplicate_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            alpha_path = root / "alpha.md"
            beta_path = root / "beta.md"
            alpha_path.write_text("# Alpha Persona\n\nCalm.", encoding="utf-8")
            beta_path.write_text("# Beta Persona\n\nDirect.", encoding="utf-8")
            alpha = load_persona_package(alpha_path)
            beta = load_persona_package(beta_path)

        registry = PersonaRegistry((beta, alpha))
        self.assertEqual([item.persona_id for item in registry.packages()], ["alpha", "beta"])
        self.assertIs(registry.get("ALPHA"), alpha)
        self.assertIsNone(registry.get("unknown"))
        with self.assertRaisesRegex(ValueError, "already registered"):
            PersonaRegistry((alpha, alpha))

    def test_package_rejects_state_or_prompt_mismatch(self):
        package = load_persona_package(None, persona_id="murr", display_name="Murr")
        with self.assertRaisesRegex(ValueError, "persona_id"):
            PersonaPackage("other", package.display_name, package.persona, package.initial_state)
        with self.assertRaisesRegex(TypeError, "Persona"):
            PersonaPackage(package.persona_id, package.display_name, "not-persona", package.initial_state)


if __name__ == "__main__":
    unittest.main()
