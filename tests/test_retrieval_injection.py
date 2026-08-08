from pathlib import Path
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession
from pipeline.application import create_assistant_application


class RecordingRetriever:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def retrieve(self, query, *, domain=None, limit=8, timings=None):
        self.calls.append({"query": query, "domain": domain, "limit": limit})
        if timings is not None:
            timings["retrieval_ms"] = 1.25
            timings["association_ms"] = 0.5
        return list(self.results)


class RetrievalInjectionTests(unittest.TestCase):
    def _config(self):
        return AssistantConfig(
            "test-model",
            Path("persona/default.md"),
            Path("config/assistant_policy.md"),
            "personal",
            6,
            2,
            "off",
            "off",
        )

    def test_session_uses_injected_retriever_without_invoking_legacy_loader(self):
        calls = []
        retriever = RecordingRetriever([{
            "memory": {"id": 9, "summary": "Injected retrieval memory", "details": "Exact context."},
            "score": 0.9,
            "reasons": ["injected test result"],
        }])

        def legacy_loader(**_kwargs):
            raise AssertionError("normal chat must use the injected retriever")

        session = AssistantSession(
            self._config(),
            "Persona",
            chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "answer"}},
            memory_loader=legacy_loader,
            retriever=retriever,
            policy="Policy",
        )

        self.assertEqual(session.respond("What is remembered?"), "answer")
        self.assertEqual(retriever.calls, [{"query": "What is remembered?", "domain": "personal", "limit": 2}])
        self.assertIn("Injected retrieval memory", calls[0]["messages"][0]["content"])
        self.assertEqual(session.last_memory_ids, [9])
        self.assertIn("injected test result", session.context_stats())

    def test_session_rejects_invalid_retriever(self):
        with self.assertRaisesRegex(TypeError, "callable retrieve"):
            AssistantSession(self._config(), "Persona", chat=lambda **_kwargs: {}, retriever=object())

    def test_application_factory_passes_one_shared_retriever_to_all_sessions(self):
        config = self._config()
        retriever = RecordingRetriever([])
        received = []

        class FakeSession:
            def __init__(self, *_args, **kwargs):
                self.config = config
                self.active_model = config.chat_model
                self.retriever = kwargs.get("retriever")
                received.append(self.retriever)

            def set_capability_manifest(self, _manifest):
                pass

            def set_retriever(self, retriever_value):
                self.retriever = retriever_value

        from unittest.mock import patch
        with patch("pipeline.application.load_config", return_value=config), patch(
            "pipeline.application.load_persona", return_value="persona"
        ), patch("pipeline.application.load_policy", return_value="policy"):
            app = create_assistant_application(
                "custom.json",
                retriever=retriever,
                session_factory=FakeSession,
            )
            app._session_for("isolated-chat")

        self.assertEqual(received, [retriever, retriever])
        self.assertIs(app.retriever, retriever)


if __name__ == "__main__":
    unittest.main()
