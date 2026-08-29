import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.persona_asset_resolver import InstalledPersonaAssetPackage, PersonaAssetResolver
from pipeline.persona_assets import PersonaAssetManifest


class PersonaAssetResolverTests(unittest.TestCase):
    def test_resolves_only_declared_existing_slot_inside_trusted_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sprite = root / "sprites" / "murr-idle.png"
            sprite.parent.mkdir()
            sprite.write_bytes(b"png")
            resolver = PersonaAssetResolver((InstalledPersonaAssetPackage(
                PersonaAssetManifest("murr", {"idle": "sprites/murr-idle.png"}), root,
            ),))

            self.assertEqual(resolver.resolve("MURR", "idle"), sprite.resolve())
            self.assertIsNone(resolver.resolve("murr", "reading"))
            self.assertIsNone(resolver.resolve("nova", "idle"))

    def test_missing_declared_file_falls_back_without_exposing_a_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            resolver = PersonaAssetResolver((InstalledPersonaAssetPackage(
                PersonaAssetManifest("murr", {"idle": "sprites/missing.png"}), Path(temporary),
            ),))
            self.assertIsNone(resolver.resolve("murr", "idle"))

    def test_resolves_missing_visual_state_to_declared_idle_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sprite = root / "sprites" / "murr-idle.png"
            sprite.parent.mkdir()
            sprite.write_bytes(b"png")
            resolver = PersonaAssetResolver((InstalledPersonaAssetPackage(
                PersonaAssetManifest("murr", {"idle": "sprites/murr-idle.png"}), root,
            ),))

            self.assertEqual(
                resolver.resolve_with_fallback("murr", "reading"), sprite.resolve(),
            )
            self.assertIsNone(resolver.resolve_with_fallback("nova", "reading"))

    def test_rejects_duplicate_installed_persona_packages(self):
        manifest = PersonaAssetManifest("murr", {})
        with tempfile.TemporaryDirectory() as temporary:
            package = InstalledPersonaAssetPackage(manifest, Path(temporary))
            with self.assertRaisesRegex(ValueError, "already registered"):
                PersonaAssetResolver((package, package))


if __name__ == "__main__":
    unittest.main()
