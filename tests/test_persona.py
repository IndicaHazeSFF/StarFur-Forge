import tempfile
import unittest
from pathlib import Path

from pipeline.persona import NEUTRAL_PERSONA, Persona, load_persona


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


if __name__ == "__main__":
    unittest.main()