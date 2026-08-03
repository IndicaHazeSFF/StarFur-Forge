import json
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession, validate_memory_proposal
from pipeline.db import ASSISTANT_MEMORY_TYPES, assistant_memory_type_prompt


class AssistantClassificationTests(unittest.TestCase):
    def setUp(self):
        self.config = AssistantConfig(
            "fake", Path("persona/default.md"), Path("config/assistant_policy.md"),
            "personal", 20, 0, "conservative", "verbose",
        )

    def _proposal_for(self, observation, memory_type, *, details="", store=True):
        calls = []
        payload = {
            "store": store,
            "subject": "User",
            "memory_type": memory_type,
            "summary": "Test memory",
            "details": details,
            "importance": 0.7,
            "confidence": 0.8,
            "retention": "long_term",
            "domain": "personal",
            "source": "ignored-by-engine",
        }
        def chat(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {"message": {"content": "Acknowledged."}}
            return {"message": {"content": json.dumps(payload)}}
        session = AssistantSession(self.config, "Persona", chat=chat, memory_loader=lambda **kwargs: [])
        session.respond(observation)
        return session, calls

    def test_taxonomy_has_only_existing_stored_types(self):
        prompt = assistant_memory_type_prompt()
        self.assertEqual(set(ASSISTANT_MEMORY_TYPES), {
            "preference", "personal_fact", "experience", "project_context",
            "relationship_context", "ongoing_situation", "goal", "routine",
        })
        for memory_type in ASSISTANT_MEMORY_TYPES:
            self.assertIn(f"- {memory_type}:", prompt)

    def test_legacy_stored_types_remain_valid(self):
        for memory_type in ASSISTANT_MEMORY_TYPES:
            with self.subTest(memory_type=memory_type):
                proposal = validate_memory_proposal({
                    "store": True, "subject": "User", "memory_type": memory_type,
                    "summary": "Legacy-compatible memory", "details": "",
                    "importance": 0.5, "confidence": 0.5, "retention": "long_term",
                    "domain": "personal", "source": "legacy-test",
                }, "personal")
                self.assertEqual(proposal["memory_type"], memory_type)

    def test_specific_user_observations_accept_expected_types(self):
        cases = (
            ("I prefer jasmine rice mixed with basmati rice.", "preference", ""),
            ("My goal is to finish the StarFur prototype this month.", "goal", ""),
            ("Actually, I no longer like coffee.", "preference", "Correction: current preference replaces an earlier coffee preference."),
            ("StarFur Forge stores structured memories in SQLite.", "project_context", ""),
            ("Murr is my close friend.", "relationship_context", ""),
            ("I usually make coffee before I start work.", "routine", ""),
            ("My desktop has an RTX graphics card.", "personal_fact", ""),
            ("My right eye sometimes loses focus.", "personal_fact", ""),
        )
        for observation, expected_type, details in cases:
            with self.subTest(observation=observation):
                session, calls = self._proposal_for(observation, expected_type, details=details)
                self.assertEqual(session.proposals[-1]["memory_type"], expected_type)
                self.assertIn("MEMORY TYPE TAXONOMY", calls[1]["messages"][0]["content"])
                self.assertNotIn("assistant-generated content", calls[1]["messages"][1]["content"])

    def test_ambiguous_observation_can_safely_decline_storage(self):
        session, _ = self._proposal_for("Things have been weird lately.", "ongoing_situation", store=False)
        self.assertFalse(session.proposals[-1]["store"])

    def test_general_knowledge_question_skips_proposal_generation(self):
        calls = []
        def chat(**kwargs):
            calls.append(kwargs)
            return {"message": {"content": "A factual answer."}}
        session = AssistantSession(self.config, "Persona", chat=chat, memory_loader=lambda **kwargs: [])
        self.assertEqual(session.respond("Explain the origin of the gaslighting term"), "A factual answer.")
        self.assertEqual(len(calls), 1)
        self.assertEqual(session.proposals, [])
        self.assertIn("proposal_skipped", [event["event"] for event in session.trace.events])


    def test_speculative_future_statement_skips_proposal_generation(self):
        calls = []
        def chat(**kwargs):
            calls.append(kwargs)
            return {"message": {"content": "Warm response."}}
        session = AssistantSession(self.config, "Persona", chat=chat, memory_loader=lambda **kwargs: [])
        observation = "One day you will be able to paint pictures on my graphics card while I am away."
        self.assertEqual(session.respond(observation), "Warm response.")
        self.assertEqual(len(calls), 1)
        self.assertEqual(session.proposals, [])
        skipped = [event for event in session.trace.events if event["event"] == "proposal_skipped"]
        self.assertEqual(skipped[-1]["reason"], "speculative_without_explicit_intent")

    def test_explicit_future_goal_remains_eligible_for_proposal(self):
        session, calls = self._proposal_for(
            "I want StarFur to generate images while I am away.", "goal",
        )
        self.assertEqual(session.proposals[-1]["memory_type"], "goal")
        self.assertEqual(len(calls), 2)
if __name__ == "__main__":
    unittest.main()