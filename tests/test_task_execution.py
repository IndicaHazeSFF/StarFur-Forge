import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.provider_registry import ChatProviderRegistration, ChatProviderRegistry
from pipeline.task_execution import RoutedChatExecutor, RoutedTaskExecutionError
from pipeline.task_profiles import TaskProfile, TaskProfiles
from pipeline.task_routing import ProviderRouteRegistry, ProviderRouteStatus, TaskRoutePlanner


class FakeChatProvider:
    name = "fake"

    def __init__(self, response=None, error=None):
        self.response = response if response is not None else {"message": {"content": "ok"}}
        self.error = error
        self.calls = []

    def complete(self, messages, *, model=None, options=None, stream=False):
        self.calls.append((messages, model, options, stream))
        if self.error is not None:
            raise self.error
        return self.response

    def complete_structured(self, messages, *, schema, model=None, options=None):
        self.calls.append((messages, model, options, False, schema))
        if self.error is not None:
            raise self.error
        return self.response

    def list_models(self):
        return []

    def probe_health(self):
        return {"models": []}


class TaskExecutionTests(unittest.TestCase):
    def _executor(self, *, primary_status="available", include_adapter=True, provider=None):
        profiles = TaskProfiles({
            "assistant_chat": TaskProfile(
                "assistant_chat", provider="local", model="small", max_output_tokens=123,
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
        return RoutedChatExecutor(planner, registry), provider

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

        public = result.public_dict()
        self.assertEqual({
            "requested_task_id": "assistant_chat",
            "selected_task_id": "assistant_chat",
            "provider": "local",
            "model": "small",
            "fallback_used": False,
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

    def test_provider_failures_do_not_silently_trigger_another_request(self):
        executor, provider = self._executor(provider=FakeChatProvider(error=RuntimeError("offline")))
        with self.assertRaisesRegex(RoutedTaskExecutionError, "request failed") as captured:
            executor.execute("assistant_chat", (), default_model="fallback", default_provider_id="local")
        self.assertEqual("provider_request_failed", captured.exception.reason)
        self.assertEqual(1, len(provider.calls))

    def test_structured_execution_uses_exact_route_schema_and_no_stream(self):
        executor, provider = self._executor()
        decision = executor.plan(
            "assistant_chat", default_model="fallback", default_provider_id="local",
        )
        schema = {"type": "object", "required": ["answer"]}

        result = executor.execute_structured_planned(decision, (), schema=schema)

        self.assertEqual("local", result.provider_id)
        self.assertEqual(((), "small", {"num_predict": 123}, False, schema), provider.calls[0])

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


if __name__ == "__main__":
    unittest.main()
