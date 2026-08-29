import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.persona_assets import PersonaAssetManifest


class PersonaAssetManifestTests(unittest.TestCase):
    def test_manifest_exposes_only_validated_declarative_slots(self):
        manifest = PersonaAssetManifest("murr", {
            "reading": "sprites/murr-reading.webp",
            "idle": "sprites/murr-idle.png",
        })

        self.assertEqual(manifest.reference_for("idle"), "sprites/murr-idle.png")
        self.assertIsNone(manifest.reference_for("working"))
        self.assertEqual(manifest.public_dict(), {
            "schema_version": 1,
            "persona_id": "murr",
            "visual_states": ["idle", "reading"],
            "storage": "package_declarative",
        })

    def test_manifest_rejects_untrusted_paths_and_unknown_visual_states(self):
        with self.assertRaisesRegex(ValueError, "unsafe"):
            PersonaAssetManifest("murr", {"idle": "../outside.png"})
        with self.assertRaisesRegex(ValueError, "POSIX"):
            PersonaAssetManifest("murr", {"idle": "sprites\\outside.png"})
        with self.assertRaisesRegex(ValueError, "supported image"):
            PersonaAssetManifest("murr", {"idle": "sprites/runner.exe"})
        with self.assertRaisesRegex(ValueError, "visual state"):
            PersonaAssetManifest("murr", {"dance": "sprites/murr-dance.png"})
        with self.assertRaisesRegex(ValueError, "visual state"):
            PersonaAssetManifest("murr", {}).reference_for("dance")


if __name__ == "__main__":
    unittest.main()
