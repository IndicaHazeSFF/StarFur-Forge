import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.application import AssistantApplication, create_assistant_application


class FakeConfig:
    chat_model = "fake:latest"
    persona_path = Path("persona.md")
    policy_path = Path("policy.md")


class FakeSession:
    def __init__(self, config=None, *args, **kwargs):
        self.config = config or FakeConfig()
        self.active_model = "fake:latest"
        self.stream = False
        self.stream_writer = None
        self.calls = []

    def respond(self, text):
        self.calls.append((text, self.stream))
        if self.stream and self.stream_writer:
            self.stream_writer("chunk")
        return "answer"

    def context_stats(self):
        return "stats"


class FailingSession(FakeSession):
    def respond(self, text):
        self.calls.append((text, self.stream))
        raise RuntimeError("expected failure")


class AssistantApplicationTests(unittest.TestCase):
    def test_respond_delegates_and_preserves_normal_session_streaming(self):
        session = FakeSession()
        app = AssistantApplication(session)

        self.assertEqual(app.respond("hello"), "answer")

        self.assertEqual(session.calls, [("hello", False)])
        self.assertFalse(session.stream)
        self.assertIsNone(session.stream_writer)
        self.assertEqual(app.active_model, "fake:latest")

    def test_request_scoped_streaming_is_restored_after_response(self):
        session = FakeSession()
        app = AssistantApplication(session)
        chunks = []

        self.assertEqual(app.respond("stream", stream_writer=chunks.append), "answer")

        self.assertEqual(chunks, ["chunk"])
        self.assertEqual(session.calls, [("stream", True)])
        self.assertFalse(session.stream)
        self.assertIsNone(session.stream_writer)

    def test_request_scoped_streaming_is_restored_after_error(self):
        session = FailingSession()
        app = AssistantApplication(session)

        with self.assertRaisesRegex(RuntimeError, "expected failure"):
            app.respond("stream", stream_writer=lambda text: None)

        self.assertFalse(session.stream)
        self.assertIsNone(session.stream_writer)

    def test_context_stats_delegates_without_a_turn(self):
        self.assertEqual(AssistantApplication(FakeSession()).context_stats(), "stats")

    def test_factory_centralizes_standard_session_dependencies(self):
        config = FakeConfig()
        captured = {}

        def session_factory(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return FakeSession(*args, **kwargs)

        with patch("pipeline.application.load_config", return_value=config), patch(
            "pipeline.application.load_persona", return_value="persona"
        ), patch("pipeline.application.load_policy", return_value="policy"):
            app = create_assistant_application(
                "custom.json",
                stream=True,
                stream_writer=lambda text: None,
                debug_level="verbose",
                session_factory=session_factory,
            )

        self.assertIsInstance(app, AssistantApplication)
        self.assertEqual(captured["args"], (config, "persona"))
        self.assertEqual(captured["kwargs"]["policy"], "policy")
        self.assertTrue(captured["kwargs"]["stream"])
        self.assertEqual(captured["kwargs"]["debug_level"], "verbose")
        self.assertIsNotNone(captured["kwargs"]["proposal_creator"])


if __name__ == "__main__":
    unittest.main()