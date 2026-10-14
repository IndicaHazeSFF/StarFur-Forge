import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.assistant import AssistantConfig, AssistantSession, GenerationInterrupted, ProposalGenerationInterrupted, run_interactive, load_config
from pipeline.task_profiles import TASK_ASSISTANT_CHAT
from pipeline.providers import (
    CallableChatProvider, ChatCompletion, ChatStreamChunk, ChatProviderResponseError, ChatProviderOutputLimitError, OllamaChatProvider,
    StructuredChatCompletionProvider, normalize_chat_completion, normalize_chat_stream_chunk,
)


class FakeOllama:
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter((
                {"message": {"content": "ans"}},
                {"done": True},
                {"message": {"content": "wer"}},
            ))
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
        self.assertEqual(response.content, "answer")
        self.assertEqual(client.calls, [{"model": "qwen3:8b", "messages": [{"role": "user", "content": "hello"}], "options": {"seed": 420}}])
        self.assertEqual(provider.list_models()["models"][0]["model"], "qwen3:8b")

    def test_ollama_adapter_passes_explicit_task_residency_only_when_configured(self):
        client = FakeOllama()
        provider = OllamaChatProvider(client)
        provider.complete(
            [{"role": "user", "content": "hello"}],
            model="qwen3:8b", keep_alive_seconds=0,
        )
        self.assertEqual(0, client.calls[0]["keep_alive"])

    def test_thinking_is_top_level_optional_and_strict_for_both_provider_paths(self):
        client = FakeOllama()
        provider = OllamaChatProvider(client)
        for enabled in (False, True):
            provider.complete((), thinking=enabled)
            provider.complete_structured((), schema={"type": "object"}, thinking=enabled)
            self.assertIs(enabled, client.calls[-1]["think"])
            self.assertIs(enabled, client.calls[-2]["think"])
            self.assertNotIn("think", client.calls[-1].get("options", {}))
        calls_before = len(client.calls)
        with self.assertRaises(ValueError):
            provider.complete((), thinking="false")
        self.assertEqual(calls_before, len(client.calls))

    def test_ollama_reduces_terminal_status_and_never_exposes_thinking_or_payload(self):
        class Client:
            def chat(self, **kwargs):
                return iter((
                    {"message": {"content": "", "thinking": "private reasoning"}},
                    {"message": {"content": "visible"}, "private": "payload"},
                    {"done": True, "done_reason": "length", "eval_count": 999},
                )) if kwargs.get("stream") else {
                    "message": {"content": "visible", "thinking": "private reasoning"},
                    "done_reason": "length", "private": "payload",
                }

        provider = OllamaChatProvider(Client())
        complete = provider.complete(())
        self.assertEqual(ChatCompletion("visible", "length"), complete)
        chunks = list(provider.complete((), stream=True))
        self.assertEqual([ChatStreamChunk(""), ChatStreamChunk("visible"), ChatStreamChunk("", "length")], chunks)
        self.assertNotIn("private", repr(chunks))
        with self.assertRaisesRegex(ChatProviderResponseError, "output limit"):
            provider.complete_structured((), schema={"type": "object"})

    def test_complete_looking_structured_json_still_fails_on_reported_output_limit(self):
        class Client:
            def chat(self, **kwargs):
                return iter((
                    {"message": {"content": '{"candidates": []}'}},
                    {"done": True, "done_reason": "length"},
                ))
        with self.assertRaisesRegex(ChatProviderOutputLimitError, "output limit"):
            OllamaChatProvider(Client()).complete_structured((), schema={"type": "object"})

    def test_session_preserves_structured_limit_reason_without_history_or_retry(self):
        class LimitedStructuredProvider(FakeProvider):
            def complete_structured(self, messages, **kwargs):
                self.calls.append(kwargs)
                return ChatCompletion('{"candidates":[]}', "length")

        provider = LimitedStructuredProvider()
        session = AssistantSession(self.config(), "Persona", provider=provider,
                                   memory_loader=lambda **_kwargs: [], policy="Policy")
        with self.assertRaises(ChatProviderOutputLimitError) as caught:
            session._provider_complete_structured((), schema={"type": "object"}, task_id=TASK_ASSISTANT_CHAT)
        self.assertEqual(1, len(provider.calls))
        self.assertEqual("provider_output_limit", session._current_task_routes[-1]["outcome"])
        self.assertNotIn("candidates", str(caught.exception))
        self.assertEqual([], session.messages)

    def test_unknown_provider_reason_is_reduced_without_retaining_its_value(self):
        class Client:
            def chat(self, **kwargs):
                return {"message": {"content": "answer"}, "done_reason": "private/provider/detail"}
        self.assertEqual(ChatCompletion("answer", "unknown"), OllamaChatProvider(Client()).complete(()))
        with self.assertRaises(ValueError):
            ChatCompletion("answer", "private/provider/detail")

    def test_session_reports_limit_without_retry_or_proposal_and_clears_it_for_commands(self):
        class LimitedProvider(FakeProvider):
            def complete(self, messages, **kwargs):
                self.calls.append(kwargs)
                return iter((ChatStreamChunk("partial"), ChatStreamChunk("", "length"))) if kwargs.get("stream") else ChatCompletion("partial", "length")

        for streaming in (False, True):
            provider = LimitedProvider()
            rendered = []
            session = AssistantSession(
                self.config(), "Persona", provider=provider, stream=streaming,
                stream_writer=rendered.append, memory_loader=lambda **_kwargs: [], policy="Policy",
            )
            session._proposal = lambda *_args: self.fail("limited response must not trigger proposal extraction")
            self.assertEqual("partial", session.respond("hello"))
            self.assertEqual(1, len(provider.calls))
            self.assertEqual("length", session.last_chat_finish_reason)
            self.assertEqual("output_limited", session.last_turn_diagnostics["turn_status"])
            self.assertFalse(session.last_turn_diagnostics["completed"])
            self.assertEqual("provider_output_limit", session.last_turn_diagnostics["task_routes"][0]["outcome"])
            self.assertIn("Finish reason: length", session.context_stats())
            self.assertEqual("partial", session.messages[-1]["content"])
            session.respond("model current")
            self.assertEqual("stop", session.last_chat_finish_reason)

    def test_ollama_stream_close_propagates_to_underlying_transport(self):
        class Stream:
            closed = False
            def __iter__(self):
                return self
            def __next__(self):
                return {"message": {"content": "part"}}
            def close(self):
                self.closed = True
        raw = Stream()
        class Client:
            def chat(self, **kwargs):
                return raw
        response = OllamaChatProvider(Client()).complete((), stream=True)
        self.assertEqual("part", next(response).content)
        response.close()
        self.assertTrue(raw.closed)

    def test_cli_limit_notice_is_separate_from_answer_and_history(self):
        from pipeline.application import AssistantApplication

        class LimitedProvider(FakeProvider):
            def complete(self, messages, **kwargs):
                self.calls.append(kwargs)
                return ChatCompletion("partial answer", "length")

        config = self.config()
        provider = LimitedProvider()
        session = AssistantSession(
            config, "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        inputs = iter(("hello", "quit"))
        output = []
        with patch("pipeline.assistant.load_config", return_value=config), patch(
            "pipeline.application.create_assistant_application", return_value=AssistantApplication(session),
        ):
            run_interactive(input_fn=lambda _prompt: next(inputs), output_fn=output.append)

        self.assertIn("StarFur: partial answer", output)
        self.assertIn("Response reached its output limit. Ask for a shorter answer or continue explicitly.", output)
        self.assertEqual("partial answer", session.messages[-1]["content"])
        self.assertEqual(1, len(provider.calls))

    def test_cli_mixed_input_is_rejected_but_separate_buffered_lines_work(self):
        from pipeline.application import AssistantApplication

        config = self.config()
        provider = FakeProvider()
        session = AssistantSession(
            config, "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        inputs = iter(("Write a story.\ncontext stats", "show context stats", "hello", "context stats", "quit"))
        output = []
        with patch("pipeline.assistant.load_config", return_value=config), patch(
            "pipeline.application.create_assistant_application", return_value=AssistantApplication(session),
        ):
            run_interactive(input_fn=lambda _prompt: next(inputs), output_fn=output.append)

        self.assertEqual(1, len(provider.calls))
        self.assertTrue(any("No command or model request was run" in line for line in output))
        self.assertIn("StarFur: No turn diagnostics are available yet.", output)
        self.assertTrue(any("=== CONTEXT STATS ===" in line for line in output))
        self.assertEqual("hello", session.messages[-2]["content"])

    def test_ollama_structured_output_is_an_explicit_top_level_capability(self):
        client = FakeOllama()
        provider = OllamaChatProvider(client)
        schema = {"type": "object", "additionalProperties": False}

        response = provider.complete_structured(
            [{"role": "user", "content": "return json"}],
            schema=schema,
            model="qwen3:8b",
            options={"num_predict": 123},
        )

        self.assertEqual("answer", response.content)
        self.assertIsInstance(provider, StructuredChatCompletionProvider)
        self.assertEqual({
            "model": "qwen3:8b",
            "messages": [{"role": "user", "content": "return json"}],
            "format": schema,
            "stream": True,
            "options": {"num_predict": 123},
        }, client.calls[0])
        self.assertNotIsInstance(CallableChatProvider(lambda **_kwargs: None), StructuredChatCompletionProvider)

    def test_ollama_structured_output_preserves_explicit_residency_setting(self):
        client = FakeOllama()
        provider = OllamaChatProvider(client)
        provider.complete_structured(
            [{"role": "user", "content": "return json"}],
            schema={"type": "object"}, model="qwen3:8b", keep_alive_seconds=0,
        )
        self.assertEqual(0, client.calls[0]["keep_alive"])

    def test_stock_participant_route_forwards_thinking_off_and_same_structured_budget(self):
        client = FakeOllama()
        config = load_config(Path(__file__).resolve().parents[1] / "config" / "assistant.json")
        session = AssistantSession(config, "Persona", provider=OllamaChatProvider(client),
                                   memory_loader=lambda **_kwargs: [], policy="Policy")
        session._provider_complete_structured(
            (), schema={"type": "object"}, task_id="adventure_participant_action_generation",
        )
        self.assertEqual(1, len(client.calls))
        self.assertIs(False, client.calls[0]["think"])
        self.assertIs(True, client.calls[0]["stream"])
        self.assertEqual({"num_ctx": 4096, "num_predict": 256}, client.calls[0]["options"])
        self.assertEqual(0, client.calls[0]["keep_alive"])
        self.assertEqual({"type": "object"}, client.calls[0]["format"])

    def test_ollama_structured_interrupt_closes_the_stream_before_propagating(self):
        class InterruptedStream:
            def __init__(self):
                self.closed = False

            def __iter__(self):
                return self

            def __next__(self):
                raise KeyboardInterrupt()

            def close(self):
                self.closed = True

        stream = InterruptedStream()

        class InterruptedOllama(FakeOllama):
            def chat(self, **kwargs):
                self.calls.append(kwargs)
                return stream

        provider = OllamaChatProvider(InterruptedOllama())
        with self.assertRaises(KeyboardInterrupt):
            provider.complete_structured(
                [{"role": "user", "content": "return json"}],
                schema={"type": "object"}, model="qwen3:8b",
            )
        self.assertTrue(stream.closed)

    def test_session_translates_structured_transport_interrupt_without_retry(self):
        class InterruptedStructuredProvider(FakeProvider):
            def complete_structured(self, messages, *, schema, model=None, options=None):
                self.calls.append({
                    "messages": messages, "schema": schema,
                    "model": model, "options": options,
                })
                raise KeyboardInterrupt()

        provider = InterruptedStructuredProvider()
        session = AssistantSession(
            self.config(), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )

        with self.assertRaises(GenerationInterrupted):
            session._provider_complete_structured(
                [{"role": "user", "content": "return json"}],
                schema={"type": "object"},
                task_id=TASK_ASSISTANT_CHAT,
            )

        self.assertEqual(1, len(provider.calls))
        self.assertEqual("provider_stream_cancelled", session._current_task_routes[-1]["outcome"])
        self.assertEqual("error", session.provider_lifecycle.public_dict()["state"])

    def test_nonstream_chat_interrupt_records_cancellation_without_history(self):
        class InterruptedProvider(FakeProvider):
            def complete(self, messages, **kwargs):
                self.calls.append(kwargs)
                raise KeyboardInterrupt()

        provider = InterruptedProvider()
        session = AssistantSession(self.config(), "Persona", provider=provider,
                                   memory_loader=lambda **_kwargs: [], policy="Policy")
        with self.assertRaises(GenerationInterrupted):
            session.respond("hello")
        self.assertEqual(1, len(provider.calls))
        self.assertEqual([], session.messages)
        self.assertEqual([], session.proposals)
        self.assertFalse(session.last_turn_diagnostics["completed"])
        self.assertEqual("provider_stream_cancelled", session.last_turn_diagnostics["task_routes"][-1]["outcome"])
        self.assertEqual("error", session.provider_lifecycle.public_dict()["state"])

    def test_proposal_and_repair_interrupt_keep_reply_and_release_application_capacity(self):
        from pipeline.application import AssistantApplication

        for interrupt_repair in (False, True):
            with self.subTest(repair=interrupt_repair):
                class InterruptedProvider(FakeProvider):
                    def complete(self, messages, **kwargs):
                        self.calls.append(kwargs)
                        if len(self.calls) == 1:
                            return ChatCompletion("completed reply", "stop")
                        if interrupt_repair and len(self.calls) == 2:
                            return ChatCompletion("invalid JSON")
                        raise KeyboardInterrupt()

                provider = InterruptedProvider()
                writes = []
                session = AssistantSession(
                    replace(self.config(), memory_policy="review"), "Persona", provider=provider,
                    memory_loader=lambda **_kwargs: [], policy="Policy",
                    proposal_creator=lambda *_args, **_kwargs: writes.append(True),
                )
                app = AssistantApplication(session)
                with self.assertRaises(ProposalGenerationInterrupted):
                    app.respond("I prefer jasmine rice.")
                self.assertEqual(3 if interrupt_repair else 2, len(provider.calls))
                self.assertEqual([], writes)
                self.assertEqual([], session.proposals)
                self.assertEqual(["I prefer jasmine rice.", "completed reply"],
                                 [message["content"] for message in session.messages])
                snapshot = session.last_turn_diagnostics
                self.assertTrue(snapshot["completed"])
                self.assertEqual("interrupted", snapshot["proposal_outcome"])
                self.assertEqual("assistant_proposal", snapshot["task_routes"][-1]["requested_task_id"])
                self.assertEqual("provider_stream_cancelled", snapshot["task_routes"][-1]["outcome"])
                self.assertEqual("completed", snapshot["task_routes"][0]["outcome"])
                admission = app._workload_gate.try_acquire(session._active_provider_id, 1)
                self.assertEqual("admitted", admission.status)
                app._workload_gate.release(admission.lease)

    def test_cli_proposal_interrupt_returns_to_prompt_and_next_request_recovers(self):
        from pipeline.application import AssistantApplication
        from contextlib import redirect_stdout
        from io import StringIO

        class InterruptedOnceProvider(FakeProvider):
            def complete(self, messages, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 2:
                    raise KeyboardInterrupt()
                if kwargs.get("stream"):
                    return iter((ChatStreamChunk("completed reply", "stop"),))
                return ChatCompletion("completed reply", "stop")

        config = replace(self.config(), memory_policy="review")
        provider = InterruptedOnceProvider()
        session = AssistantSession(config, "Persona", provider=provider,
                                   memory_loader=lambda **_kwargs: [], policy="Policy")
        inputs = iter(("I prefer jasmine rice.", "routing status", "How are you?", "quit"))
        output = []
        visible = StringIO()

        def factory(*_args, **kwargs):
            session.stream = kwargs["stream"]
            session.stream_writer = kwargs["stream_writer"]
            return AssistantApplication(session)

        with patch("pipeline.assistant.load_config", return_value=config), patch(
            "pipeline.application.create_assistant_application", side_effect=factory,
        ), redirect_stdout(visible):
            run_interactive(input_fn=lambda _prompt: next(inputs), output_fn=output.append)
        self.assertIn("Memory proposal generation interrupted. Completed reply kept.", output)
        self.assertEqual(2, visible.getvalue().count("StarFur: completed reply"))
        self.assertIn("Goodbye.", output)
        self.assertEqual(3, len(provider.calls))
        self.assertEqual([], session.proposals)
        self.assertEqual("How are you?", session.messages[-2]["content"])
        self.assertEqual("completed", session.last_turn_diagnostics["task_routes"][0]["outcome"])

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
