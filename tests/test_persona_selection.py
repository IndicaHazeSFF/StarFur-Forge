import sys
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession, load_config
from pipeline.persona_development import PersonaDevelopmentState
from pipeline.persona_registry import PersonaRegistry, load_persona_package
from pipeline.persona_runtime import PersonaRuntimeRegistry, PersonaRuntimeState
from pipeline.persona_state import DynamicTraits


class PersonaSelectionTests(unittest.TestCase):
    def _config(self):
        return AssistantConfig("test-model", Path("persona/default.md"), Path("config/assistant_policy.md"), "personal", 4, 2, "off", "off")

    def _packages(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        first = root / "murr.md"
        second = root / "nova.md"
        first.write_text("# Murr Persona\n\nMurr prompt.", encoding="utf-8")
        second.write_text("# Nova Persona\n\nNova prompt.", encoding="utf-8")
        return temporary, load_persona_package(first), load_persona_package(second)

    def test_selection_is_session_scoped_and_clears_only_recent_conversation(self):
        temporary, murr, nova = self._packages()
        self.addCleanup(temporary.cleanup)
        registry = PersonaRegistry((murr, nova))
        calls = []
        session = AssistantSession(
            self._config(), murr, persona_registry=registry,
            chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: [], policy="Policy",
        )
        session.messages[:] = [{"role": "user", "content": "old context"}]
        session.last_memory_ids[:] = [9]

        self.assertIn("nova", session.persona_list())
        self.assertEqual(session.persona_current(), "Active persona: murr (Murr)")
        self.assertIn("context was cleared", session.persona_use("NOVA"))
        self.assertEqual(session.persona_current(), "Active persona: nova (Nova)")
        self.assertEqual(session.messages, [])
        self.assertEqual(session.last_memory_ids, [])
        self.assertEqual(session.persona.render_prompt(), nova.persona.render_prompt())
        self.assertEqual(session.respond("hello"), "answer")
        self.assertIn("Nova prompt.", calls[-1]["messages"][0]["content"])

    def test_selection_commands_do_not_call_model_or_change_shared_memory_dependencies(self):
        temporary, murr, nova = self._packages()
        self.addCleanup(temporary.cleanup)
        calls = []
        loader = lambda **kwargs: []
        session = AssistantSession(
            self._config(), murr, persona_registry=PersonaRegistry((murr, nova)),
            chat=lambda **kwargs: calls.append(kwargs), memory_loader=loader, policy="Policy",
        )

        self.assertEqual(session.respond("persona use missing"), "Persona package not found: missing")
        self.assertIn("Active persona set to: nova", session.respond("persona use nova"))
        self.assertIs(session.memory_loader, loader)
        self.assertEqual(calls, [])
        self.assertIn("already active", session.respond("persona use nova"))

    def test_persona_current_has_command_precedence_and_a_bounded_typo_alias(self):
        temporary, murr, nova = self._packages()
        self.addCleanup(temporary.cleanup)
        calls = []
        session = AssistantSession(
            self._config(), murr, persona_registry=PersonaRegistry((murr, nova)),
            chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "model output"}},
            memory_loader=lambda **kwargs: [], policy="Policy",
        )

        expected = "Active persona: murr (Murr)"
        self.assertEqual(session.respond("Persona current"), expected)
        self.assertEqual(session.respond("persona curretn"), expected)
        self.assertEqual(calls, [])
        self.assertEqual(session.proposals, [])

    def test_switch_reads_only_the_selected_persona_runtime_namespace(self):
        temporary, murr, nova = self._packages()
        self.addCleanup(temporary.cleanup)
        runtimes = PersonaRuntimeRegistry()
        runtimes.replace(PersonaRuntimeState(
            replace(murr.initial_state, dynamic_traits=DynamicTraits(warmth=0.8)),
            PersonaDevelopmentState.empty("murr"),
        ))
        session = AssistantSession(
            self._config(), murr, persona_registry=PersonaRegistry((murr, nova)),
            persona_runtime_registry=runtimes, chat=lambda **kwargs: {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: [], policy="Policy",
        )

        self.assertEqual(session.persona_state.dynamic_traits.warmth, 0.8)
        session.persona_use("nova")
        self.assertEqual(session.persona_state.persona_id, "nova")
        self.assertEqual(session.persona_state.dynamic_traits.warmth, 0.5)
        session.persona_use("murr")
        self.assertEqual(session.persona_state.dynamic_traits.warmth, 0.8)

    def test_stock_config_registers_murr_and_selectable_personas(self):
        config = load_config(Path(__file__).resolve().parents[1] / "config" / "assistant.json")

        self.assertEqual(config.active_persona_id, "murr")
        self.assertEqual(
            [package.persona_id for package in config.persona_registry.packages()],
            ["murr", "neutral", "nova"],
        )


if __name__ == "__main__":
    unittest.main()
