import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tempfile
import unittest
from pathlib import Path

from pipeline.persona import NEUTRAL_PERSONA, Persona, load_persona, load_persona_state


class PersonaLayerTests(unittest.TestCase):
    def test_default_persona_loading_and_rendering(self):
        persona = load_persona(Path("persona/default.md"))
        self.assertIsInstance(persona, Persona)
        self.assertIn("You are StarFur", persona.render_prompt())

    def test_missing_and_malformed_persona_use_neutral_fallback(self):
        self.assertEqual(load_persona(Path("does-not-exist.md")).render_prompt(), NEUTRAL_PERSONA)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.md"
            path.write_text("   ", encoding="utf-8")
            self.assertEqual(load_persona(path).render_prompt(), NEUTRAL_PERSONA)

    def test_persona_remains_string_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "persona.md"
            path.write_text("A concise test persona.", encoding="utf-8")
            persona = load_persona(path)
            self.assertEqual(persona, "A concise test persona.")
            self.assertEqual(str(persona), persona.render_prompt())


class PersonaStateLoadingTests(unittest.TestCase):
    def test_state_loader_preserves_current_persona_prompt_exactly(self):
        path = Path("persona/default.md")
        state = load_persona_state(path)
        self.assertEqual(state.static_identity, load_persona(path).render_prompt())
        self.assertEqual(state.persona_id, "default")
        self.assertEqual(state.display_name, "StarFur")
        self.assertEqual(state.dynamic_traits.warmth, 0.5)
        self.assertEqual(state.momentary_state.activity, "idle")

    def test_state_loader_supports_explicit_identity_and_neutral_fallback(self):
        state = load_persona_state(Path("does-not-exist.md"), persona_id="murr", display_name="Murr")
        self.assertEqual(state.persona_id, "murr")
        self.assertEqual(state.display_name, "Murr")
        self.assertEqual(state.static_identity, NEUTRAL_PERSONA)

    def test_state_loader_derives_safe_identity_from_custom_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Murr Fox!.md"
            path.write_text("# Murr Assistant Persona\n\nWarm and practical.", encoding="utf-8")
            state = load_persona_state(path)
        self.assertEqual(state.persona_id, "murr-fox")
        self.assertEqual(state.display_name, "Murr")

if __name__ == "__main__":
    unittest.main()