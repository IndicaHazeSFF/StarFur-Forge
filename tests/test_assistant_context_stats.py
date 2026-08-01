import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import (
    AssistantConfig,
    AssistantSession,
    GenerationInterrupted,
    estimate_tokens,
)


class ContextStatsTests(unittest.TestCase):
    def config(self, *, policy="off", max_memories=3):
        return AssistantConfig(
            "test-model",
            Path("persona/default.md"),
            Path("config/assistant_policy.md"),
            "personal",
            6,
            max_memories,
            policy,
            "off",
        )

    def test_before_any_turn_has_no_snapshot(self):
        session = AssistantSession(
            self.config(), "Persona", chat=lambda **kwargs: {"message": {"content": "unused"}},
            memory_loader=lambda **kwargs: [], policy="Policy",
        )
        self.assertEqual(session.respond("context stats"), "No turn diagnostics are available yet.")

    def test_completed_no_memory_turn_reports_bounded_summary(self):
        session = AssistantSession(
            self.config(), "Warm persona", chat=lambda **kwargs: {"message": {"content": "Hello!"}},
            memory_loader=lambda **kwargs: [], policy="Ground answers.",
        )
        self.assertEqual(session.respond("hello"), "Hello!")
        stats = session.respond("context stats")
        self.assertIn("Turn: completed", stats)
        self.assertIn("Provider: custom chat client", stats)
        self.assertIn("Model: test-model", stats)
        self.assertIn("Retrieved memories: 0", stats)
        self.assertIn("Selected memory IDs: (none)", stats)
        self.assertIn("Proposal extraction ran: no", stats)
        self.assertIn("Proposal outcome: skipped", stats)
        self.assertIn("estimated", stats)
        self.assertNotIn("hello", stats)
        self.assertNotIn("Warm persona", stats)

    def test_retrieval_details_have_stable_order_and_reasons(self):
        memories = [
            {"id": 7, "summary": "First memory"},
            {"id": 3, "summary": "Second memory"},
        ]
        session = AssistantSession(
            self.config(max_memories=2), "Persona", chat=lambda **kwargs: {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: memories, policy="Policy",
        )
        session.respond("recall this")
        first = session.respond("context stats")
        second = session.respond("context stats")
        self.assertEqual(first, second)
        self.assertLess(first.index("M-007"), first.index("M-003"))
        self.assertIn("score=unscored", first)
        self.assertIn("reasons: custom memory loader", first)

    def test_context_stats_is_read_only_after_completed_turn(self):
        calls = []
        session = AssistantSession(
            self.config(), "Persona",
            chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "answer"}},
            memory_loader=lambda **kwargs: [], policy="Policy",
        )
        session.respond("hello")
        before_messages = list(session.messages)
        before_proposals = list(session.proposals)
        before_calls = len(calls)
        first = session.respond("context stats")
        second = session.respond("context stats")
        self.assertEqual(first, second)
        self.assertEqual(len(calls), before_calls)
        self.assertEqual(session.messages, before_messages)
        self.assertEqual(session.proposals, before_proposals)

    def test_question_proposal_is_reported_as_skipped(self):
        session = AssistantSession(
            self.config(policy="conservative"), "Persona",
            chat=lambda **kwargs: {"message": {"content": "An answer."}},
            memory_loader=lambda **kwargs: [], policy="Policy",
        )
        session.respond("What is gaslighting?")
        stats = session.context_stats()
        self.assertIn("Proposal extraction ran: no", stats)
        self.assertIn("Proposal outcome: skipped", stats)

    def test_created_proposal_is_reported(self):
        responses = iter([
            {"message": {"content": "Got it."}},
            {"message": {"content": '{"store": true, "subject": "User", "memory_type": "preference", "summary": "Likes tea", "details": "", "importance": 0.8, "confidence": 0.9, "retention": "long_term"}'}},
        ])
        session = AssistantSession(
            self.config(policy="conservative"), "Persona", chat=lambda **kwargs: next(responses),
            memory_loader=lambda **kwargs: [], policy="Policy",
            proposal_creator=lambda proposal, **kwargs: {"proposal_id": 4, "action": "created"},
        )
        session.respond("I like tea")
        stats = session.context_stats()
        self.assertIn("Proposal extraction ran: yes", stats)
        self.assertIn("Proposal outcome: created", stats)

    def test_interrupted_turn_has_snapshot_without_partial_history(self):
        def chat(**kwargs):
            def stream():
                yield {"message": {"content": "partial"}}
                raise KeyboardInterrupt()
            return stream()
        session = AssistantSession(
            self.config(policy="conservative"), "Persona", chat=chat,
            memory_loader=lambda **kwargs: [], policy="Policy", stream=True,
            stream_writer=lambda text: None,
        )
        with self.assertRaises(GenerationInterrupted):
            session.respond("I like tea")
        stats = session.context_stats()
        self.assertIn("Turn: interrupted", stats)
        self.assertIn("Response: 0 characters", stats)
        self.assertIn("Proposal outcome: interrupted", stats)
        self.assertIn("Time to first streamed token:", stats)
        self.assertEqual(session.messages, [])
        self.assertEqual(session.proposals, [])

    def test_token_estimate_is_explicit_and_stable(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcde"), 2)


if __name__ == "__main__":
    unittest.main()
