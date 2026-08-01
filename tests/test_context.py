import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession
from pipeline.context import ContextManager, estimate_tokens


class ContextManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = ContextManager()

    def test_chat_messages_match_existing_structure_exactly(self):
        recent = [
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
        ]
        memories = [{"id": 7, "summary": "Likes jasmine rice"}]
        plan = self.manager.build_chat(
            persona_text="Persona text",
            policy_text="Policy text",
            recent_messages=recent,
            retrieved_memories=memories,
            user_text="Current question",
        )
        expected = [
            {
                "role": "system",
                "content": "Persona text\n\nENGINE POLICY:\nPolicy text\n\nRETRIEVED MEMORY (factual context):\n- Likes jasmine rice\n\nEND RETRIEVED MEMORY",
            },
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
            {"role": "user", "content": "Current question"},
        ]
        self.assertEqual(plan.model_messages(), expected)
        self.assertEqual(plan.selected_memory_ids, (7,))
        self.assertEqual(plan.persona.estimated_tokens, estimate_tokens("Persona text"))
        self.assertEqual(plan.policy.characters, len("Policy text"))
        self.assertEqual(plan.retrieved_memory.text, "- Likes jasmine rice")
        self.assertEqual(plan.current_user.text, "Current question")

    def test_selected_memory_details_are_included_as_factual_context(self):
        plan = self.manager.build_chat(
            persona_text="Persona", policy_text="Policy", recent_messages=[],
            retrieved_memories=[{
                "id": 9,
                "summary": "Nozzle size correction",
                "details": "The user uses a 0.8 mm nozzle instead of a 0.6 mm nozzle.",
            }],
            user_text="What size nozzle do I use?",
        )
        prompt = plan.model_messages()[0]["content"]
        self.assertIn("- Nozzle size correction", prompt)
        self.assertIn("Details: The user uses a 0.8 mm nozzle instead of a 0.6 mm nozzle.", prompt)
        self.assertEqual(plan.retrieved_memory.text, "- Nozzle size correction\n  Details: The user uses a 0.8 mm nozzle instead of a 0.6 mm nozzle.")

    def test_no_memory_plan_matches_existing_none_format(self):
        plan = self.manager.build_chat(
            persona_text="Persona", policy_text="Policy", recent_messages=[],
            retrieved_memories=[], user_text="Hello",
        )
        self.assertEqual(plan.selected_memory_ids, ())
        self.assertIn("RETRIEVED MEMORY (factual context):\n(none)", plan.model_messages()[0]["content"])
        self.assertEqual(plan.recent_conversation.characters, 0)

    def test_planning_is_deterministic_and_does_not_mutate_inputs(self):
        recent = [{"role": "user", "content": "Earlier"}]
        memories = [{"id": 4, "summary": "A memory"}]
        first = self.manager.build_chat(
            persona_text="Persona", policy_text="Policy", recent_messages=recent,
            retrieved_memories=memories, user_text="Question",
        )
        second = self.manager.build_chat(
            persona_text="Persona", policy_text="Policy", recent_messages=recent,
            retrieved_memories=memories, user_text="Question",
        )
        self.assertEqual(first, second)
        self.assertEqual(recent, [{"role": "user", "content": "Earlier"}])
        self.assertEqual(memories, [{"id": 4, "summary": "A memory"}])
        returned = first.model_messages()
        returned[0]["content"] = "changed"
        self.assertNotEqual(first.model_messages()[0]["content"], "changed")

    def test_introspection_messages_preserve_existing_prompt(self):
        plan = self.manager.build_introspection(
            persona_text="Persona",
            policy_text="Policy",
            explanation_json='{"status": "ok"}',
            user_text="Why do you remember that?",
            selected_memory_ids=[3],
        )
        self.assertEqual(plan.selected_memory_ids, (3,))
        self.assertEqual(
            plan.model_messages(),
            [
                {
                    "role": "system",
                    "content": "Persona\n\nENGINE POLICY:\nPolicy\n\nYou are answering a memory-introspection question. Use ONLY the structured explanation JSON below. Explain remembered content and provenance naturally. Do not mention rejected proposals, raw databases, hidden reasoning, or invent causes.\nSTRUCTURED MEMORY EXPLANATION:\n{\"status\": \"ok\"}",
                },
                {"role": "user", "content": "Why do you remember that?"},
            ],
        )

    def test_assistant_uses_exact_plan_payload_and_context_stats(self):
        calls = []
        config = AssistantConfig(
            "test-model", Path("persona/default.md"), Path("config/assistant_policy.md"),
            "personal", 6, 2, "off", "off",
        )
        session = AssistantSession(
            config,
            "Persona",
            chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: [{"id": 9, "summary": "Memory summary"}],
            policy="Policy",
        )
        self.assertEqual(session.respond("Question"), "answer")
        self.assertEqual(
            calls[0]["messages"],
            [
                {
                    "role": "system",
                    "content": "Persona\n\nENGINE POLICY:\nPolicy\n\nRETRIEVED MEMORY (factual context):\n- Memory summary\n\nEND RETRIEVED MEMORY",
                },
                {"role": "user", "content": "Question"},
            ],
        )
        self.assertEqual(session.last_memory_ids, [9])
        stats = session.context_stats()
        self.assertIn("Retrieved memories: 1", stats)
        self.assertIn("M-009", stats)


if __name__ == "__main__":
    unittest.main()
