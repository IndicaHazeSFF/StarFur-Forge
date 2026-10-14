import json
import sys
import tempfile
import types
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.application import AssistantApplication
from pipeline.adventure_registry import AdventureRegistry
from pipeline.assistant import AssistantConfig, AssistantSession, ProviderCapacityBusyError, load_config
from pipeline.document_intake import prepare_document_text
from pipeline.provider_registry import ChatProviderRegistration, ChatProviderRegistry
from pipeline.task_profiles import (
    TASK_ADVENTURE_TURN_GENERATION, TASK_ADVENTURE_TURN_MUTATION_GENERATION, TASK_ADVENTURE_TURN_RESOURCE_GENERATION, TASK_ASSISTANT_CHAT, TASK_DOCUMENT_ANNOTATION, TASK_DOCUMENT_ANNOTATION_FALLBACK, TASK_RESEARCH_CLAIM_GENERATION, TASK_RESEARCH_RELATIONSHIP_GENERATION, TaskProfile, TaskProfiles,
    load_task_profiles,
)


class FakeProvider:
    name = "Ollama"

    def __init__(self):
        self.calls = []
        self.probe_calls = 0

    def complete(self, messages, *, model=None, options=None, stream=False):
        self.calls.append({"model": model, "options": dict(options or {}), "stream": stream})
        return {"message": {"content": "answer"}}

    def complete_structured(self, messages, *, schema, model=None, options=None):
        self.calls.append({
            "model": model, "options": dict(options or {}), "stream": False,
            "schema": schema,
        })
        return {"message": {"content": "answer"}}

    def list_models(self):
        return {"models": [{"model": "chat-model"}]}

    def probe_health(self):
        self.probe_calls += 1
        return self.list_models()


class CompletionOnlyProvider:
    """Specialist test double intentionally lacking discovery/probe methods."""

    name = "Ollama"

    def __init__(self):
        self.calls = []

    def complete(self, messages, *, model=None, options=None, stream=False):
        self.calls.append({"model": model, "options": dict(options or {}), "stream": stream})
        return {"message": {"content": "specialist answer"}}


def config_with_profiles(profiles):
    return AssistantConfig(
        "chat-model", Path("persona/default.md"), Path("config/assistant_policy.md"),
        "personal", 4, 0, "off", "off", {"temperature": 0.4}, profiles,
    )


class TaskProfileTests(unittest.TestCase):
    def test_stock_chat_and_adventure_profiles_have_bounded_output_ceilings(self):
        config = load_config(Path(__file__).resolve().parents[1] / "config" / "assistant.json")
        chat = config.task_profiles.resolve(
            TASK_ASSISTANT_CHAT, default_model=config.chat_model, base_options=config.ollama_options,
        )
        proposal = config.task_profiles.resolve(
            "assistant_proposal", default_model=config.chat_model, base_options=config.ollama_options,
        )
        turn = config.task_profiles.resolve(
            TASK_ADVENTURE_TURN_GENERATION, default_model=config.chat_model, base_options=config.ollama_options,
        )
        mutation = config.task_profiles.resolve(
            TASK_ADVENTURE_TURN_MUTATION_GENERATION, default_model=config.chat_model, base_options=config.ollama_options,
        )
        resource = config.task_profiles.resolve(
            TASK_ADVENTURE_TURN_RESOURCE_GENERATION, default_model=config.chat_model, base_options=config.ollama_options,
        )
        self.assertEqual(8192, chat.options["num_ctx"])
        self.assertEqual(1024, chat.options["num_predict"])
        self.assertIs(False, chat.model_thinking)
        self.assertEqual(4096, proposal.options["num_ctx"])
        self.assertEqual(256, proposal.options["num_predict"])
        self.assertEqual(512, turn.options["num_predict"])
        self.assertEqual(256, mutation.options["num_predict"])
        self.assertEqual(256, resource.options["num_predict"])

    def test_stock_participant_thinking_request_does_not_raise_its_budget_or_change_other_tasks(self):
        config = load_config(Path(__file__).resolve().parents[1] / "config" / "assistant.json")
        participant = config.task_profiles.resolve(
            "adventure_participant_action_generation", default_model=config.chat_model,
        )
        self.assertIs(False, participant.model_thinking)
        self.assertEqual({"num_ctx": 4096, "num_predict": 256}, dict(participant.options))
        self.assertEqual(0, participant.model_keep_alive_seconds)
        for task_id in (TASK_ADVENTURE_TURN_GENERATION, TASK_ADVENTURE_TURN_MUTATION_GENERATION,
                        TASK_ADVENTURE_TURN_RESOURCE_GENERATION, TASK_RESEARCH_CLAIM_GENERATION,
                        TASK_RESEARCH_RELATIONSHIP_GENERATION, TASK_DOCUMENT_ANNOTATION):
            self.assertIsNone(config.task_profiles.resolve(task_id, default_model=config.chat_model).model_thinking)

    def test_config_parses_validated_profiles_without_changing_legacy_fields(self):
        payload = {
            "chat_model": "chat-model",
            "task_profiles": {
                "assistant_chat": {
                    "provider": "ollama", "model": "profile-model",
                    "generation_options": {"temperature": 0.2}, "context_size": 4096,
                    "resource_profile": "interactive", "max_concurrent_requests": 2,
                    "model_keep_alive_seconds": 0,
                    "model_thinking": False,
                },
                "vision": {"provider": "future-vision", "fallback_task": "assistant_chat"},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "assistant.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            config = load_config(path)
        profile = config.task_profiles.resolve(TASK_ASSISTANT_CHAT, default_model=config.chat_model, base_options=config.ollama_options)
        self.assertEqual(profile.model, "profile-model")
        self.assertEqual(profile.options, {"temperature": 0.2, "num_ctx": 4096})
        self.assertEqual("interactive", profile.resource_profile)
        self.assertEqual(2, profile.max_concurrent_requests)
        self.assertEqual(0, profile.model_keep_alive_seconds)
        self.assertIs(False, profile.model_thinking)
        self.assertEqual(config.chat_model, "profile-model")

    def test_invalid_profile_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown field"):
            load_task_profiles({"assistant_chat": {"unexpected": True}})
        with self.assertRaisesRegex(ValueError, "positive"):
            load_task_profiles({"assistant_chat": {"max_output_tokens": 0}})
        with self.assertRaisesRegex(ValueError, "Unknown task profile generation option"):
            load_task_profiles({"assistant_chat": {"generation_options": {"num_predict": 42}}})
        with self.assertRaisesRegex(ValueError, "resource_profile"):
            load_task_profiles({"assistant_chat": {"resource_profile": "unbounded"}})
        with self.assertRaisesRegex(ValueError, "max_concurrent_requests"):
            load_task_profiles({"assistant_chat": {"max_concurrent_requests": 0}})
        with self.assertRaisesRegex(ValueError, "model_keep_alive_seconds"):
            load_task_profiles({"assistant_chat": {"model_keep_alive_seconds": -1}})
        for invalid in (0, 1, "false", "high", [], {}):
            with self.assertRaisesRegex(ValueError, "model_thinking"):
                load_task_profiles({"assistant_chat": {"model_thinking": invalid}})

    def test_thinking_preview_is_passive_and_omission_preserves_provider_default(self):
        profiles = load_task_profiles({"assistant_chat": {"model_thinking": False}})
        session = AssistantSession(config_with_profiles(profiles), "Persona", provider=FakeProvider(), memory_loader=lambda **_kwargs: [], policy="Policy")
        self.assertIn("thinking=off", session.command("routing status"))
        self.assertEqual([], session.provider.calls)
        self.assertIsNone(TaskProfiles().resolve("assistant_chat", default_model="legacy").model_thinking)

    def test_provider_mode_is_validated_and_disabled_mode_never_routes_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "assistant.json"
            path.write_text(json.dumps({"provider_mode": "invalid"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "provider_mode"):
                load_config(path)

        session = AssistantSession(
            replace(config_with_profiles(TaskProfiles()), provider_mode="disabled"), "Persona",
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        self.assertIn("provider disabled (unavailable)", session.command("routing status"))
        with self.assertRaisesRegex(RuntimeError, "no configured provider route"):
            session._provider_complete(({"role": "user", "content": "hello"},))

        with self.assertRaisesRegex(ValueError, "provider_mode 'disabled'"):
            AssistantSession(
                replace(config_with_profiles(TaskProfiles()), provider_mode="disabled"), "Persona",
                provider=FakeProvider(), memory_loader=lambda **_kwargs: [], policy="Policy",
            )

    def test_focus_mode_defers_only_noninteractive_work_before_provider_use(self):
        profiles = TaskProfiles({
            TASK_ASSISTANT_CHAT: TaskProfile(
                TASK_ASSISTANT_CHAT, provider="ollama", resource_profile="interactive",
            ),
            TASK_ADVENTURE_TURN_GENERATION: TaskProfile(
                TASK_ADVENTURE_TURN_GENERATION, provider="ollama", resource_profile="balanced",
            ),
            TASK_RESEARCH_CLAIM_GENERATION: TaskProfile(
                TASK_RESEARCH_CLAIM_GENERATION, provider="ollama", resource_profile="background",
            ),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )

        self.assertIn("Focus Mode: off", session.command("focus mode status"))
        self.assertIn("Focus Mode: on", session.command("focus mode on"))
        focus_status = session.command("routing status")
        self.assertIn("adventure_turn_generation: ollama / chat-model [unprobed] (workload=balanced, focus=deferred)", focus_status)
        self.assertIn("assistant_chat: ollama / chat-model [unprobed] (workload=interactive)", focus_status)
        with self.assertRaisesRegex(RuntimeError, "deferred by Focus Mode"):
            session._provider_complete(
                ({"role": "user", "content": "generate"},),
                task_id=TASK_ADVENTURE_TURN_GENERATION,
            )
        with self.assertRaisesRegex(RuntimeError, "deferred by Focus Mode"):
            session._task_route(TASK_RESEARCH_CLAIM_GENERATION)
        application = AssistantApplication(session)
        with self.assertRaisesRegex(RuntimeError, "deferred by Focus Mode"):
            application._document_annotation_route(session, TASK_RESEARCH_CLAIM_GENERATION)
        self.assertEqual([], provider.calls)
        self.assertEqual(
            {"message": {"content": "answer"}},
            session._provider_complete(({"role": "user", "content": "hello"},)),
        )
        self.assertEqual(1, len(provider.calls))
        self.assertIn("Focus Mode: off", session.command("focus mode off"))

    def test_application_attaches_one_shared_capacity_gate_before_routed_provider_use(self):
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(TaskProfiles({
                TASK_ASSISTANT_CHAT: TaskProfile(TASK_ASSISTANT_CHAT, provider="ollama"),
            })),
            "Persona", provider=provider, memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        application = AssistantApplication(session)
        gate = application._workload_gate
        self.assertIsNotNone(gate)
        held = gate.try_acquire("ollama", 1)
        with self.assertRaisesRegex(RuntimeError, "capacity is currently busy"):
            session._provider_complete(({"role": "user", "content": "hello"},))
        self.assertEqual([], provider.calls)
        self.assertTrue(gate.release(held.lease))
        self.assertEqual(
            {"message": {"content": "answer"}},
            session._provider_complete(({"role": "user", "content": "hello"},)),
        )

    def test_document_annotation_uses_shared_capacity_gate_only_for_live_adapter(self):
        provider = FakeProvider()

        def annotation_complete(messages, *, model=None, options=None, stream=False):
            provider.calls.append({"model": model, "options": dict(options or {}), "stream": stream})
            return {"message": {"content": '{"proposals": []}'}}

        provider.complete = annotation_complete
        session = AssistantSession(
            config_with_profiles(TaskProfiles({
                TASK_DOCUMENT_ANNOTATION: TaskProfile(
                    TASK_DOCUMENT_ANNOTATION, provider="ollama", resource_profile="background",
                ),
            })),
            "Persona", provider=provider, memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        application = AssistantApplication(session)
        gate = application._workload_gate
        held = gate.try_acquire("ollama", 1)
        document = prepare_document_text("No durable facts.", "notes.md", domain="personal")
        with self.assertRaises(ProviderCapacityBusyError):
            application.annotate_document(document)
        self.assertEqual([], provider.calls)
        self.assertTrue(gate.release(held.lease))

        result = application.annotate_document(document)
        self.assertEqual((), result.candidates)
        self.assertEqual(1, len(provider.calls))
        self.assertEqual(0, gate.active_count("ollama"))

    def test_chat_profile_options_apply_but_active_model_remains_authoritative(self):
        profiles = TaskProfiles({
            TASK_ASSISTANT_CHAT: TaskProfile(
                TASK_ASSISTANT_CHAT, provider="ollama", generation_options={"top_p": 0.8}, context_size=2048,
            ),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        self.assertEqual(session.respond("hello"), "answer")
        self.assertEqual(provider.calls[0]["model"], "chat-model")
        self.assertEqual(provider.calls[0]["options"], {"temperature": 0.4, "top_p": 0.8, "num_ctx": 2048})
        self.assertEqual([{
            "requested_task_id": "assistant_chat",
            "selected_task_id": "assistant_chat",
            "provider": "ollama",
            "model": "chat-model",
            "fallback_used": False,
            "outcome": "completed",
        }], session.last_turn_diagnostics["task_routes"])

    def test_exact_task_profile_can_select_an_injected_specialist_provider(self):
        profiles = TaskProfiles({
            TASK_ASSISTANT_CHAT: TaskProfile(TASK_ASSISTANT_CHAT, provider="specialist", model="small-model"),
        })
        primary = FakeProvider()
        specialist = CompletionOnlyProvider()
        registry = ChatProviderRegistry({
            "ollama": ChatProviderRegistration("ollama", primary),
            "specialist": ChatProviderRegistration("specialist", specialist),
        })
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=primary, provider_registry=registry,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )

        self.assertEqual("specialist answer", session.respond("hello"))
        self.assertEqual([], primary.calls)
        self.assertEqual("small-model", specialist.calls[0]["model"])
        self.assertEqual("specialist", session.last_turn_diagnostics["task_routes"][0]["provider"])
        self.assertEqual("specialist", session.provider_lifecycle.public_dict()["provider"])
        self.assertIn("assistant_chat: specialist / small-model [unprobed]", session.command("routing status"))
        self.assertEqual(0, primary.probe_calls)

    def test_injected_provider_registry_must_include_the_active_provider(self):
        provider = FakeProvider()
        registry = ChatProviderRegistry({
            "specialist": ChatProviderRegistration("specialist", FakeProvider()),
        })
        with self.assertRaisesRegex(ValueError, "active provider"):
            AssistantSession(
                config_with_profiles(TaskProfiles()), "Persona", provider=provider, provider_registry=registry,
                memory_loader=lambda **_kwargs: [], policy="Policy",
            )

    def test_document_annotation_uses_its_profile_without_touching_chat(self):
        profiles = TaskProfiles({
            TASK_DOCUMENT_ANNOTATION: TaskProfile(
                TASK_DOCUMENT_ANNOTATION, provider="ollama", model="annotation-model",
                generation_options={"temperature": 0.1}, max_output_tokens=333,
            ),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        document = prepare_document_text("Roger prefers tea.", "notes.md", domain="personal")
        result = AssistantApplication(session).annotate_document(
            document,
            annotator=None,
        )
        # The fake's plain text response produces one chunk failure, but proves
        # profile resolution, provider invocation, and non-persistent handling.
        self.assertEqual(result.candidates, ())
        self.assertEqual(provider.calls[0]["model"], "annotation-model")
        self.assertEqual(provider.calls[0]["options"], {"temperature": 0.1, "num_predict": 333})

    def test_research_claim_provider_uses_one_exact_local_route(self):
        profiles = TaskProfiles({
            TASK_RESEARCH_CLAIM_GENERATION: TaskProfile(
                TASK_RESEARCH_CLAIM_GENERATION,
                provider="ollama",
                model="research-model",
                max_output_tokens=777,
            ),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        adapter = session.local_research_claim_provider()

        content = adapter.propose_claims(
            ({"role": "system", "content": "strict"}, {"role": "user", "content": "packet"}),
            model="research-model",
            schema={"type": "object"},
        )

        self.assertEqual("answer", content)
        self.assertEqual("local", adapter.target.deployment)
        self.assertEqual("ollama", adapter.target.provider_id)
        self.assertEqual("research-model", provider.calls[0]["model"])
        self.assertEqual({"temperature": 0.4, "num_predict": 777}, provider.calls[0]["options"])
        self.assertEqual({"type": "object"}, provider.calls[0]["schema"])
        self.assertEqual(1, len(provider.calls))

    def test_research_claim_provider_rejects_configured_fallback_route(self):
        profiles = TaskProfiles({
            TASK_RESEARCH_CLAIM_GENERATION: TaskProfile(
                TASK_RESEARCH_CLAIM_GENERATION,
                provider="missing",
                model="missing-model",
                fallback_task=TASK_ASSISTANT_CHAT,
            ),
            TASK_ASSISTANT_CHAT: TaskProfile(
                TASK_ASSISTANT_CHAT,
                provider="ollama",
                model="qwen3:8b",
            ),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )

        with self.assertRaisesRegex(RuntimeError, "local research provider route is unavailable"):
            session.local_research_claim_provider()
        self.assertEqual([], provider.calls)

    def test_research_claim_provider_requires_explicit_structured_output_capability(self):
        profiles = TaskProfiles({
            TASK_RESEARCH_CLAIM_GENERATION: TaskProfile(
                TASK_RESEARCH_CLAIM_GENERATION,
                provider="ollama",
                model="research-model",
            ),
        })
        provider = CompletionOnlyProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        adapter = session.local_research_claim_provider()

        with self.assertRaisesRegex(RuntimeError, "does not support structured output"):
            adapter.propose_claims(
                ({"role": "system", "content": "strict"}, {"role": "user", "content": "packet"}),
                model="research-model",
                schema={"type": "object"},
            )

        self.assertEqual([], provider.calls)
        self.assertEqual("provider_capability_unavailable", session._current_task_routes[-1]["outcome"])

    def test_research_relationship_provider_uses_one_exact_local_route(self):
        profiles = TaskProfiles({
            TASK_RESEARCH_RELATIONSHIP_GENERATION: TaskProfile(
                TASK_RESEARCH_RELATIONSHIP_GENERATION,
                provider="ollama",
                model="relationship-model",
                max_output_tokens=555,
            ),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        adapter = session.local_research_relationship_provider()

        content = adapter.propose_relationships(
            ({"role": "system", "content": "strict"}, {"role": "user", "content": "review"}),
            model="relationship-model",
            schema={"type": "object"},
        )

        self.assertEqual("answer", content)
        self.assertEqual("local", adapter.target.deployment)
        self.assertEqual("relationship-model", provider.calls[0]["model"])
        self.assertEqual({"temperature": 0.4, "num_predict": 555}, provider.calls[0]["options"])
        self.assertEqual({"type": "object"}, provider.calls[0]["schema"])

    def test_research_relationship_provider_rejects_configured_fallback_route(self):
        profiles = TaskProfiles({
            TASK_RESEARCH_RELATIONSHIP_GENERATION: TaskProfile(
                TASK_RESEARCH_RELATIONSHIP_GENERATION,
                provider="missing",
                model="missing-model",
                fallback_task=TASK_ASSISTANT_CHAT,
            ),
            TASK_ASSISTANT_CHAT: TaskProfile(
                TASK_ASSISTANT_CHAT, provider="ollama", model="qwen3:8b",
            ),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )

        with self.assertRaisesRegex(RuntimeError, "local research relationship provider route is unavailable"):
            session.local_research_relationship_provider()
        self.assertEqual([], provider.calls)

    def test_document_annotation_uses_explicit_bounded_fallback_profile(self):
        profiles = TaskProfiles({
            TASK_DOCUMENT_ANNOTATION: TaskProfile(
                TASK_DOCUMENT_ANNOTATION, provider="ollama", model="phi4-mini:latest",
                fallback_task=TASK_DOCUMENT_ANNOTATION_FALLBACK,
            ),
            TASK_DOCUMENT_ANNOTATION_FALLBACK: TaskProfile(
                TASK_DOCUMENT_ANNOTATION_FALLBACK, provider="ollama", model="qwen3:8b",
            ),
        })
        provider = FakeProvider()
        calls = []

        def complete(messages, *, model=None, options=None, stream=False):
            calls.append(model)
            content = "not json" if model == "phi4-mini:latest" else json.dumps({"proposals": []})
            return {"message": {"content": content}}

        provider.complete = complete
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        document = prepare_document_text("No durable facts.", "notes.md", domain="personal")
        result = AssistantApplication(session).annotate_document(document)

        self.assertEqual((), result.candidates)
        self.assertEqual(["phi4-mini:latest", "phi4-mini:latest", "qwen3:8b"], calls)
        self.assertTrue(result.execution.fallback_used)

    def test_document_annotation_without_fallback_retries_the_selected_primary_only(self):
        profiles = TaskProfiles({
            TASK_DOCUMENT_ANNOTATION: TaskProfile(
                TASK_DOCUMENT_ANNOTATION, provider="ollama", model="qwen3:8b",
            ),
        })
        provider = FakeProvider()
        calls = []

        def complete(messages, *, model=None, options=None, stream=False):
            calls.append(model)
            return {"message": {"content": "not json"}}

        provider.complete = complete
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        result = AssistantApplication(session).annotate_document(
            prepare_document_text("No durable facts.", "notes.md", domain="personal"),
        )

        self.assertEqual(["qwen3:8b", "qwen3:8b", "qwen3:8b"], calls)
        self.assertIsNone(result.execution.fallback_model)
        self.assertFalse(result.execution.fallback_used)

    def test_document_annotation_primary_profile_mismatch_fails_before_provider_call(self):
        profiles = TaskProfiles({
            TASK_DOCUMENT_ANNOTATION: TaskProfile(
                TASK_DOCUMENT_ANNOTATION, provider="another-provider", model="annotation-model",
            ),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )

        with self.assertRaisesRegex(RuntimeError, "route is unavailable"):
            AssistantApplication(session).annotate_document(
                prepare_document_text("No durable facts.", "notes.md", domain="personal"),
            )
        self.assertEqual([], provider.calls)

    def test_document_annotation_fallback_profile_mismatch_fails_before_fallback_call(self):
        profiles = TaskProfiles({
            TASK_DOCUMENT_ANNOTATION: TaskProfile(
                TASK_DOCUMENT_ANNOTATION,
                provider="ollama",
                model="primary-model",
                fallback_task=TASK_DOCUMENT_ANNOTATION_FALLBACK,
            ),
            TASK_DOCUMENT_ANNOTATION_FALLBACK: TaskProfile(
                TASK_DOCUMENT_ANNOTATION_FALLBACK,
                provider="another-provider",
                model="fallback-model",
            ),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )

        with self.assertRaisesRegex(RuntimeError, "route is unavailable"):
            AssistantApplication(session).annotate_document(
                prepare_document_text("No durable facts.", "notes.md", domain="personal"),
            )
        self.assertEqual([], provider.calls)

    def test_mismatched_profile_provider_fails_instead_of_routing_silently(self):
        profiles = TaskProfiles({
            TASK_ASSISTANT_CHAT: TaskProfile(TASK_ASSISTANT_CHAT, provider="another-provider"),
        })
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=FakeProvider(),
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        with self.assertRaisesRegex(RuntimeError, "no configured provider route"):
            session.respond("hello")

    def test_routing_status_is_read_only_and_reports_configured_models(self):
        profiles = TaskProfiles({
            TASK_ASSISTANT_CHAT: TaskProfile(TASK_ASSISTANT_CHAT, provider="ollama", model="chat-model"),
            TASK_DOCUMENT_ANNOTATION: TaskProfile(TASK_DOCUMENT_ANNOTATION, provider="ollama", model="annotation-model"),
        })
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(profiles), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )

        result = session.command("routing status")

        self.assertIn("assistant_chat: ollama / chat-model [unprobed]", result)
        self.assertIn("document_annotation: ollama / annotation-model [unprobed]", result)
        self.assertIn("Read-only route preview", result)
        self.assertEqual([], provider.calls)
        self.assertEqual(0, provider.probe_calls)

        budgeted = AssistantSession(
            config_with_profiles(TaskProfiles({
                TASK_DOCUMENT_ANNOTATION: TaskProfile(
                    TASK_DOCUMENT_ANNOTATION, provider="ollama", model="annotation-model",
                    context_size=2048, max_output_tokens=333,
                    resource_profile="background", model_keep_alive_seconds=0,
                ),
            })), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        budgeted_status = budgeted.command("routing status")
        self.assertIn(
            "document_annotation: ollama / annotation-model [unprobed] "
            "(context=2048, output=333, workload=background, keep_alive=0s)",
            budgeted_status,
        )

    def test_routing_probe_is_explicit_non_generating_and_updates_route_status(self):
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(TaskProfiles()), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )

        result = session.command("routing probe")

        self.assertIn("provider Ollama is available (1 model(s) reported)", result)
        self.assertIn("No text was generated", result)
        self.assertEqual("healthy", session.provider_health_snapshot["status"])
        self.assertIn("assistant_chat: ollama / chat-model [available]", session.command("routing status"))
        self.assertEqual([], provider.calls)
        self.assertEqual(1, provider.probe_calls)

    def test_explicitly_unavailable_provider_never_receives_a_routed_session_call(self):
        provider = FakeProvider()
        session = AssistantSession(
            config_with_profiles(TaskProfiles()), "Persona", provider=provider,
            memory_loader=lambda **_kwargs: [], policy="Policy",
        )
        session.provider_health_snapshot = {"status": "unavailable"}

        with self.assertRaisesRegex(RuntimeError, "no configured provider route"):
            session.respond("hello")
        self.assertEqual([], provider.calls)

    def test_adventure_turn_profile_uses_its_own_model_and_options(self):
        profiles = TaskProfiles({
            TASK_ADVENTURE_TURN_GENERATION: TaskProfile(
                TASK_ADVENTURE_TURN_GENERATION, provider="ollama", model="turn-model",
                generation_options={"temperature": 0.1}, max_output_tokens=222,
            ),
        })
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider()
            session = AssistantSession(
                config_with_profiles(profiles), "Persona", provider=provider,
                memory_loader=lambda **_kwargs: [], policy="Policy",
                adventure_registry=AdventureRegistry(directory),
            )
            session.adventure_registry.create("Quiet Ember")
            session.adventure_load("Quiet Ember")

            with self.assertRaisesRegex(RuntimeError, "failed safely"):
                session.generate_adventure_turn_candidates(user_text="I inspect the hatch.")

            self.assertEqual("turn-model", provider.calls[0]["model"])
            self.assertEqual({"temperature": 0.1, "num_predict": 222}, provider.calls[0]["options"])

    def test_typed_adventure_mutation_task_is_a_distinct_profile_key(self):
        profiles = TaskProfiles({
            TASK_ADVENTURE_TURN_MUTATION_GENERATION: TaskProfile(
                TASK_ADVENTURE_TURN_MUTATION_GENERATION, model="mutation-model", max_output_tokens=111,
            ),
        })
        resolved = profiles.resolve(
            TASK_ADVENTURE_TURN_MUTATION_GENERATION, default_model="chat-model",
        )
        self.assertEqual("mutation-model", resolved.model)
        self.assertEqual({"num_predict": 111}, resolved.options)
        self.assertNotEqual(TASK_ADVENTURE_TURN_GENERATION, TASK_ADVENTURE_TURN_MUTATION_GENERATION)


if __name__ == "__main__":
    unittest.main()
