import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession
from pipeline.providers import (
    CallableChatProvider, ChatProviderResponseError, OllamaChatProvider,
    normalize_chat_completion, normalize_chat_stream_chunk,
)


class FakeOllama:
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"message": {"content": "answer"}}

    def list(self):
        return {"models": [{"model": "qwen3:8b"}]}


class FakeProvider:
    name = "Fake provider"

    def __init__(self):
        self.calls = []

    def complete(self, messages, *, model=None, options=None, stream=False):
        self.calls.append({"messages": messages, "model": model, "options": options, "stream": stream})
        return {"message": {"content": "answer"}}

    def list_models(self):
        return {"models": [{"model": "test-model"}]}


class ChatProviderTests(unittest.TestCase):
    def config(self, *, options=None):
        return AssistantConfig(
            "test-model", Path("persona/default.md"), Path("config/assistant_policy.md"),
            "personal", 8, 2, "off", "off", options or {},
        )

    def test_ollama_adapter_preserves_supported_client_calls(self):
        client = FakeOllama()
        provider = OllamaChatProvider(client)
        response = provider.complete([{"role": "user", "content": "hello"}], model="qwen3:8b", options={"seed": 420})
        self.assertEqual(response["message"]["content"], "answer")
        self.assertEqual(client.calls, [{"model": "qwen3:8b", "messages": [{"role": "user", "content": "hello"}], "options": {"seed": 420}}])
        self.assertEqual(provider.list_models()["models"][0]["model"], "qwen3:8b")

    def test_session_routes_chat_and_diagnostics_through_injected_provider(self):
        provider = FakeProvider()
        session = AssistantSession(
            self.config(options={"temperature": 0.4}), "Persona", provider=provider,
            memory_loader=lambda **kwargs: [], policy="Policy",
        )
        self.assertEqual(session.respond("hello"), "answer")
        self.assertEqual(provider.calls[0]["model"], "test-model")
        self.assertEqual(provider.calls[0]["options"], {"temperature": 0.4})
        self.assertIn("Provider: Fake provider", session.context_stats())
        self.assertEqual(session.provider_lifecycle.public_dict()["state"], "idle")
        self.assertEqual(session.respond("model list"), "Installed Ollama models:\n* test-model (active)")

    def test_legacy_callable_remains_compatible(self):
        calls = []
        provider = CallableChatProvider(
            lambda **kwargs: calls.append(kwargs) or {"message": {"content": "answer"}},
            model_lister=lambda: {"models": [{"model": "test-model"}]},
        )
        session = AssistantSession(
            self.config(), "Persona", provider=provider,
            memory_loader=lambda **kwargs: [], policy="Policy",
        )
        self.assertEqual(session.respond("hello"), "answer")
        self.assertNotIn("options", calls[0])
        self.assertEqual(session.respond("model current"), "Active model: test-model")

    def test_provider_and_legacy_chat_are_not_ambiguous(self):
        with self.assertRaises(ValueError):
            AssistantSession(
                self.config(), "Persona", chat=lambda **kwargs: None, provider=FakeProvider(),
                memory_loader=lambda **kwargs: [], policy="Policy",
            )

    def test_provider_neutral_completion_contract_accepts_mapping_and_typed_shapes(self):
        self.assertEqual("mapping", normalize_chat_completion({"message": {"content": "mapping"}}).content)

        class Message:
            content = "typed"

        class Response:
            message = Message()

        self.assertEqual("typed", normalize_chat_completion(Response()).content)
        self.assertEqual("part", normalize_chat_stream_chunk({"content": "part"}).content)
        with self.assertRaisesRegex(ChatProviderResponseError, "no text"):
            normalize_chat_completion({"message": {}})
        with self.assertRaisesRegex(ChatProviderResponseError, "no text"):
            normalize_chat_stream_chunk(object())

    def test_session_consumes_a_typed_completion_without_provider_shape_assumptions(self):
        class Message:
            content = "typed answer"

        class Response:
            message = Message()

        class TypedProvider(FakeProvider):
            def complete(self, messages, *, model=None, options=None, stream=False):
                self.calls.append({"messages": messages, "model": model, "options": options, "stream": stream})
                return Response()

        session = AssistantSession(
            self.config(), "Persona", provider=TypedProvider(),
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        self.assertEqual("typed answer", session.respond("hello"))

    def test_session_streams_typed_fragments_and_ignores_metadata_only_chunks(self):
        class Message:
            def __init__(self, content):
                self.content = content

        class Chunk:
            def __init__(self, content):
                self.message = Message(content)

        class MetadataOnlyChunk:
            pass

        class StreamProvider(FakeProvider):
            def complete(self, messages, *, model=None, options=None, stream=False):
                self.calls.append({"messages": messages, "model": model, "options": options, "stream": stream})
                return iter((Chunk("typed "), MetadataOnlyChunk(), Chunk("stream")))

        rendered = []
        session = AssistantSession(
            self.config(), "Persona", provider=StreamProvider(), stream=True,
            stream_writer=rendered.append, memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        self.assertEqual("typed stream", session.respond("hello"))
        self.assertEqual(["typed ", "stream"], rendered)
        self.assertEqual("completed", session.last_turn_diagnostics["task_routes"][0]["outcome"])

    def test_stream_failure_is_diagnostic_only_and_never_persists_partial_chat(self):
        class FailingStreamProvider(FakeProvider):
            def complete(self, messages, *, model=None, options=None, stream=False):
                self.calls.append({"messages": messages, "model": model, "options": options, "stream": stream})

                def chunks():
                    yield {"message": {"content": "partial"}}
                    raise RuntimeError("stream disconnected")

                return chunks()

        rendered = []
        session = AssistantSession(
            self.config(), "Persona", provider=FailingStreamProvider(), stream=True,
            stream_writer=rendered.append, memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        with self.assertRaisesRegex(RuntimeError, "stream disconnected"):
            session.respond("hello")
        self.assertEqual(["partial"], rendered)
        self.assertEqual([], session.messages)
        self.assertEqual("provider_stream_failed", session.last_turn_diagnostics["task_routes"][0]["outcome"])
        self.assertEqual("failed", session.last_turn_diagnostics["turn_status"])


if __name__ == "__main__":
    unittest.main()
