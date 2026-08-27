import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession
from pipeline.persona_registry import PersonaRegistry, load_persona_package


class ResidentActionCommandTests(unittest.TestCase):
    def _session(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        murr_path = root / "murr.md"
        nova_path = root / "nova.md"
        murr_path.write_text("# Murr Persona\n\nMurr prompt.", encoding="utf-8")
        nova_path.write_text("# Nova Persona\n\nNova prompt.", encoding="utf-8")
        murr = load_persona_package(murr_path)
        nova = load_persona_package(nova_path)
        calls = []
        session = AssistantSession(
            AssistantConfig("test-model", Path("persona/default.md"), Path("config/assistant_policy.md"), "personal", 4, 2, "off", "off"),
            murr,
            persona_registry=PersonaRegistry((murr, nova)),
            chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "model output"}},
            memory_loader=lambda **kwargs: [],
            policy="Policy",
        )
        return session, calls

    def test_explicit_action_is_persona_local_and_never_calls_the_model(self):
        session, calls = self._session()

        self.assertIn("Resident action: idle", session.respond("resident status"))
        self.assertIn("Resident action set to: reading", session.respond("resident action reading"))
        self.assertEqual(session.persona_runtime_state.resident_action.kind, "reading")
        self.assertEqual(session.persona_runtime_state.resident_action.source, "explicit_core")
        self.assertIn("Active persona set to: nova", session.respond("persona use nova"))
        self.assertIn("Resident action: idle", session.respond("resident status"))
        self.assertIn("Active persona set to: murr", session.respond("persona use murr"))
        self.assertIn("Resident action: reading", session.respond("resident status"))
        self.assertEqual(calls, [])

    def test_malformed_resident_forms_stay_in_core_and_clear_restores_idle(self):
        session, calls = self._session()

        self.assertIn("invalid", session.respond("resident action definitely-not-real"))
        self.assertIn("Unknown or malformed resident command", session.respond("resident schedule work"))
        self.assertIn("Resident action set to: working", session.respond("resident action working"))
        self.assertIn("Resident action set to: idle", session.respond("resident action clear"))
        self.assertEqual(session.persona_runtime_state.resident_action.source, "core_default")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
