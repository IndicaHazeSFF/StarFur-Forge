import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.provider_registry import ChatProviderRegistration, ChatProviderRegistry
from pipeline.task_execution import RoutedChatExecutor, RoutedTaskExecutionError
from pipeline.task_profiles import TaskProfile, TaskProfiles
from pipeline.task_routing import ProviderRouteRegistry, ProviderRouteStatus, TaskRoutePlanner
from pipeline.provider_workload_gate import ProviderWorkloadGate
from pipeline.providers import ChatCompletion, ChatProviderOutputLimitError


class FakeChatProvider:
    name = "fake"
    supports_model_keep_alive_seconds = True

    def __init__(self, response=None, error=None):
        self.response = response if response is not None else {"message": {"content": "ok"}}
        self.error = error
        self.calls = []

    def complete(self, messages, *, model=None, options=None, stream=False, keep_alive_seconds=None):
        self.calls.append((messages, model, options, stream, keep_alive_seconds))
        if self.error is not None:
            raise self.error
        return self.response

    def complete_structured(self, messages, *, schema, model=None, options=None, keep_alive_seconds=None):
        self.calls.append((messages, model, options, False, schema, keep_alive_seconds))
        if self.error is not None:
            raise self.error
        return self.response

    def list_models(self):
        return []

    def probe_health(self):
        return {"models": []}


class TaskExecutionTests(unittest.TestCase):
    def _executor(self, *, primary_status="available", include_adapter=True, provider=None, workload_gate=None):
        profiles = TaskProfiles({
            "assistant_chat": TaskProfile(
                "assistant_chat", provider="local", model="small", max_output_tokens=123,
                resource_profile="interactive", model_keep_alive_seconds=0,
            ),
        })
        planner = TaskRoutePlanner(
            profiles,
            ProviderRouteRegistry({"local": ProviderRouteStatus("local", primary_status)}),
        )
        provider = provider or FakeChatProvider()
        registry = ChatProviderRegistry(
            {"local": ChatProviderRegistration("local", provider)} if include_adapter else {},
        )
        return RoutedChatExecutor(planner, registry, workload_gate=workload_gate), provider

    def test_executes_exactly_one_selected_registered_provider_with_profile_budget(self):
        executor, provider = self._executor()

        decision = executor.plan(
            "assistant_chat",
            default_model="fallback", default_provider_id="local",
        )
        self.assertEqual("small", decision.selected.profile.model)
        self.assertEqual([], provider.calls)
        result = executor.execute_planned(decision, [{"role": "user", "content": "hello"}])

        self.assertEqual("local", result.provider_id)
        self.assertEqual("assistant_chat", result.task_id)
        self.assertEqual("small", provider.calls[0][1])
        self.assertEqual({"num_predict": 123}, provider.calls[0][2])
        self.assertFalse(provider.calls[0][3])
        self.assertEqual(0, provider.calls[0][4])

        public = result.public_dict()
        self.assertEqual({
            "requested_task_id": "assistant_chat",
            "selected_task_id": "assistant_chat",
            "provider": "local",
            "model": "small",
            "fallback_used": False,
            "resource_profile": "interactive",
            "model_keep_alive_seconds": 0,
            "outcome": "submitted",
        }, public)
        self.assertNotIn("response", public)

    def test_unavailable_route_or_missing_adapter_fails_before_any_call(self):
        unavailable, provider = self._executor(primary_status="unavailable")
        with self.assertRaisesRegex(RoutedTaskExecutionError, "no configured") as captured:
            unavailable.execute("assistant_chat", (), default_model="fallback", default_provider_id="local")
        self.assertEqual("route_unavailable", captured.exception.reason)
        self.assertEqual([], provider.calls)

        missing, _ = self._executor(include_adapter=False)
        with self.assertRaisesRegex(RoutedTaskExecutionError, "adapter") as captured:
            missing.execute("assistant_chat", (), default_model="fallback", default_provider_id="local")
        self.assertEqual("provider_adapter_unavailable", captured.exception.reason)

    def test_residency_request_fails_closed_for_an_adapter_that_does_not_opt_in(self):
        class NoResidencyProvider:
            def complete(self, messages, *, model=None, options=None, stream=False):
                raise AssertionError("provider must not be called")

        executor, _ = self._executor(provider=NoResidencyProvider())
        decision = executor.plan(
            "assistant_chat", default_model="fallback", default_provider_id="local",
        )
        with self.assertRaises(RoutedTaskExecutionError) as captured:
            executor.execute_planned(decision, ())
        self.assertEqual("provider_residency_control_unavailable", captured.exception.reason)

    def test_provider_failures_do_not_silently_trigger_another_request(self):
        executor, provider = self._executor(provider=FakeChatProvider(error=RuntimeError("offline")))
        with self.assertRaisesRegex(RoutedTaskExecutionError, "request failed") as captured:
            executor.execute("assistant_chat", (), default_model="fallback", default_provider_id="local")
        self.assertEqual("provider_request_failed", captured.exception.reason)
        self.assertEqual(1, len(provider.calls))

    def test_explicit_thinking_is_forwarded_on_exact_text_and_structured_routes(self):
        class ThinkingProvider(FakeChatProvider):
            supports_model_thinking = True
            def complete(self, messages, **kwargs):
                self.calls.append(kwargs)
                return self.response
            def complete_structured(self, messages, **kwargs):
                self.calls.append(kwargs)
                return self.response

        provider = ThinkingProvider()
        executor, _ = self._executor(provider=provider)
        for enabled in (False, True):
            planner = TaskRoutePlanner(
                TaskProfiles({"assistant_chat": TaskProfile("assistant_chat", provider="local", model_thinking=enabled)}),
                ProviderRouteRegistry({"local": ProviderRouteStatus("local", "available")}),
            )
            decision = planner.plan("assistant_chat", default_model="model", default_provider_id="local")
            executor.execute_planned(decision, ())
            executor.execute_structured_planned(decision, (), schema={"type": "object"})
            self.assertIs(enabled, provider.calls[-1]["thinking"])
            self.assertIs(enabled, provider.calls[-2]["thinking"])
            self.assertNotIn("think", provider.calls[-1].get("options") or {})

    def test_unsupported_thinking_fails_before_capacity_or_provider_use(self):
        gate = ProviderWorkloadGate({"local": 1})
        executor, provider = self._executor(workload_gate=gate)
        planner = TaskRoutePlanner(
            TaskProfiles({"assistant_chat": TaskProfile("assistant_chat", provider="local", model_thinking=False)}),
            ProviderRouteRegistry({"local": ProviderRouteStatus("local", "available")}),
        )
        decision = planner.plan("assistant_chat", default_model="model", default_provider_id="local")
        for structured in (False, True):
            with self.assertRaises(RoutedTaskExecutionError) as error:
                if structured:
                    executor.execute_structured_planned(decision, (), schema={"type": "object"})
                else:
                    executor.execute_planned(decision, ())
            self.assertEqual("provider_thinking_control_unavailable", error.exception.reason)
            self.assertEqual([], provider.calls)
            self.assertEqual(0, gate.active_count("local"))

    def test_shared_workload_gate_defers_before_provider_call_and_releases_after_failure(self):
        gate = ProviderWorkloadGate({"local": 1})
        held = gate.try_acquire("local", 1)
        executor, provider = self._executor(workload_gate=gate)
        with self.assertRaises(RoutedTaskExecutionError) as busy:
            executor.execute("assistant_chat", (), default_model="fallback", default_provider_id="local")
        self.assertEqual("provider_concurrency_busy", busy.exception.reason)
        self.assertEqual([], provider.calls)
        self.assertTrue(gate.release(held.lease))

        failing, failing_provider = self._executor(
            provider=FakeChatProvider(error=RuntimeError("offline")), workload_gate=gate,
        )
        with self.assertRaises(RoutedTaskExecutionError):
            failing.execute("assistant_chat", (), default_model="fallback", default_provider_id="local")
        self.assertEqual(0, gate.active_count("local"))

    def test_streaming_response_retains_capacity_until_exhausted_or_closed(self):
        gate = ProviderWorkloadGate({"local": 1})
        executor, _ = self._executor(
            provider=FakeChatProvider(response=iter((
                {"message": {"content": "one"}},
                {"message": {"content": "two"}},
            ))),
            workload_gate=gate,
        )

        execution = executor.execute(
            "assistant_chat", (), default_model="fallback",
            default_provider_id="local", stream=True,
        )
        self.assertEqual(1, gate.active_count("local"))
        self.assertEqual("one", next(execution.response)["message"]["content"])
        self.assertEqual(1, gate.active_count("local"))
        self.assertEqual("two", next(execution.response)["message"]["content"])
        with self.assertRaises(StopIteration):
            next(execution.response)
        self.assertEqual(0, gate.active_count("local"))

        executor, _ = self._executor(
            provider=FakeChatProvider(response=iter(({"message": {"content": "held"}},))),
            workload_gate=gate,
        )
        execution = executor.execute(
            "assistant_chat", (), default_model="fallback",
            default_provider_id="local", stream=True,
        )
        self.assertEqual(1, gate.active_count("local"))
        execution.response.close()
        execution.response.close()
        self.assertEqual(0, gate.active_count("local"))

    def test_structured_execution_uses_exact_route_schema_and_no_stream(self):
        executor, provider = self._executor()
        decision = executor.plan(
            "assistant_chat", default_model="fallback", default_provider_id="local",
        )
        schema = {"type": "object", "required": ["answer"]}

        result = executor.execute_structured_planned(decision, (), schema=schema)

        self.assertEqual("local", result.provider_id)
        self.assertEqual(((), "small", {"num_predict": 123}, False, schema, 0), provider.calls[0])

    def test_structured_execution_fails_closed_when_capability_is_absent(self):
        class TextOnlyProvider:
            def complete(self, messages, *, model=None, options=None, stream=False):
                raise AssertionError("text completion must not be called")

        executor, _ = self._executor(provider=TextOnlyProvider())
        decision = executor.plan(
            "assistant_chat", default_model="fallback", default_provider_id="local",
        )
        with self.assertRaises(RoutedTaskExecutionError) as caught:
            executor.execute_structured_planned(decision, (), schema={"type": "object"})
        self.assertEqual("provider_capability_unavailable", caught.exception.reason)

    def test_structured_output_limit_is_typed_and_releases_capacity_without_retry(self):
        for raised in (False, True):
            with self.subTest(raised=raised):
                gate = ProviderWorkloadGate({"local": 1})
                provider = FakeChatProvider(
                    response=ChatCompletion('{"answer":"complete-looking"}', "length"),
                    error=ChatProviderOutputLimitError() if raised else None,
                )
                executor, _ = self._executor(provider=provider, workload_gate=gate)
                decision = executor.plan("assistant_chat", default_model="fallback", default_provider_id="local")
                with self.assertRaises(RoutedTaskExecutionError) as caught:
                    executor.execute_structured_planned(decision, (), schema={"type": "object"})
                self.assertEqual("provider_output_limit", caught.exception.reason)
                self.assertNotIn("complete-looking", str(caught.exception))
                self.assertEqual(1, len(provider.calls))
                self.assertEqual(0, gate.active_count("local"))
                provider.error = None
                provider.response = ChatCompletion("{}", "stop")
                self.assertEqual(ChatCompletion("{}", "stop"), executor.execute_structured_planned(
                    decision, (), schema={"type": "object"},
                ).response)
                self.assertEqual(0, gate.active_count("local"))


if __name__ == "__main__":
    unittest.main()
