from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
import time
from pathlib import Path

import ollama

from pipeline.db import (
    create_assistant_memory,
    create_assistant_memory_proposal,
    upsert_assistant_memory_proposal,
    list_assistant_memory_proposals, approve_assistant_memory_proposal, reject_assistant_memory_proposal,
    inspect_assistant_memory_proposal, inspect_assistant_memory,
    assistant_public_id, resolve_assistant_id,
    get_assistant_memory,
    get_assistant_memory_proposal,
    list_assistant_memories,
    search_assistant_memories,
    update_assistant_memory,
    update_assistant_memory_proposal_visibility_scope,
    assistant_memory_type_prompt,
)
from pipeline.domains import normalize_domain
from pipeline.memory_proposal_validation import PROPOSAL_FIELDS, validate_memory_proposal
from pipeline.retrieval_debug import RetrievalTrace, normalize_debug_level
from pipeline.persona import Persona, load_persona, load_persona_state
from pipeline.context import ContextManager, ContextPlan, estimate_tokens
from pipeline.persona_state import BehaviorContext
from pipeline.persona_registry import PersonaPackage, PersonaRegistry
from pipeline.behavior import derive_behavior_guidance
from pipeline.persona_development import PersonaDevelopmentState
from pipeline.persona_attention import select_persona_attention
from pipeline.persona_runtime import PersonaRuntimeRegistry, PersonaRuntimeState
from pipeline.persona_visibility import (
    SharedMemoryVisibilityPolicy,
    evaluate_shared_memory_scope_visibility,
    evaluate_shared_memory_visibility,
)
from pipeline.roleplay import RoleplaySessionState, detect_casual_roleplay_start
from pipeline.adventure_registry import AdventureNotFoundError, AdventureRegistry, AdventureRegistryError
from pipeline.adventure_session import AdventureSessionState

from pipeline.capabilities import CapabilityManifest
from pipeline.command_help import detect_command_help
from pipeline.providers import CallableChatProvider, ChatProvider, OllamaChatProvider
from pipeline.provider_state import ProviderLifecycle
from pipeline.retrieval import DeterministicMemoryRetriever, MemoryLoaderRetriever, MemoryRetriever
from pipeline.task_profiles import (
    TASK_ASSISTANT_CHAT, TASK_ASSISTANT_PROPOSAL, TaskProfiles,
    load_task_profiles, provider_matches, validate_generation_options,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "assistant.json"
DEFAULT_POLICY_PATH = PROJECT_ROOT / "config" / "assistant_policy.md"
MEMORY_POLICIES = ("off", "conservative")
@dataclass(frozen=True)
class AssistantConfig:
    chat_model: str
    persona_path: Path
    policy_path: Path
    domain: str
    max_session_messages: int
    max_memories: int
    memory_policy: str
    debug_level: str
    ollama_options: dict[str, int | float] = field(default_factory=dict)
    task_profiles: TaskProfiles = field(default_factory=TaskProfiles)
    persona_registry: PersonaRegistry | None = None
    active_persona_id: str | None = None
    adventure_root: Path = PROJECT_ROOT / "adventures"


def validate_ollama_options(value):
    """Validate the narrow, portable Ollama generation-options surface."""
    try:
        return validate_generation_options(value)
    except ValueError as error:
        raise ValueError(str(error).replace("Task profile", "Ollama")) from error


def load_config(path=DEFAULT_CONFIG_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    task_profiles = load_task_profiles(data.get("task_profiles"))
    chat_profile = task_profiles.get(TASK_ASSISTANT_CHAT)
    persona_path = Path(data.get("persona_path", "persona/default.md"))
    if not persona_path.is_absolute():
        persona_path = PROJECT_ROOT / persona_path
    raw_persona_packages = data.get("persona_packages")
    if raw_persona_packages is not None:
        if not isinstance(raw_persona_packages, list):
            raise ValueError("persona_packages must be a list when configured.")
        resolved_packages = []
        for item in raw_persona_packages:
            if not isinstance(item, dict):
                raise ValueError("persona_packages entries must be objects.")
            resolved = dict(item)
            package_path = resolved.get("persona_path")
            if isinstance(package_path, str):
                candidate = Path(package_path)
                resolved["persona_path"] = candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
            resolved_packages.append(resolved)
    else:
        resolved_packages = None
    from pipeline.persona_registry import load_persona_packages
    persona_registry = load_persona_packages(persona_path, resolved_packages)
    requested_persona_id = data.get("active_persona_id")
    if requested_persona_id is not None and not isinstance(requested_persona_id, str):
        raise ValueError("active_persona_id must be a string when configured.")
    active_persona_id = requested_persona_id or load_persona_state(persona_path).persona_id
    if persona_registry.get(active_persona_id) is None:
        raise ValueError("active_persona_id must name a configured persona package.")
    policy_path = Path(data.get("policy_path", "config/assistant_policy.md"))
    if not policy_path.is_absolute():
        policy_path = PROJECT_ROOT / policy_path
    policy = data.get("memory_policy", "conservative")
    if policy not in MEMORY_POLICIES:
        raise ValueError(f"Invalid memory_policy: {policy!r}")
    adventure_root = Path(data.get("adventure_root", "adventures"))
    if not adventure_root.is_absolute():
        adventure_root = PROJECT_ROOT / adventure_root
    return AssistantConfig(
        # A chat profile model is the declarative startup default. Later
        # ``model use`` selections remain per-session runtime state.
        chat_model=(chat_profile.model if chat_profile and chat_profile.model else data.get("chat_model", "qwen3:8b")),
        persona_path=persona_path,
        policy_path=policy_path,
        domain=normalize_domain(data.get("domain", "personal")),
        max_session_messages=int(data.get("max_session_messages", 20)),
        max_memories=int(data.get("max_memories", 5)),
        memory_policy=policy,
        debug_level=normalize_debug_level(data.get("debug_level", "off")),
        ollama_options=validate_ollama_options(data.get("ollama_options")),
        task_profiles=task_profiles,
        persona_registry=persona_registry,
        active_persona_id=active_persona_id,
        adventure_root=adventure_root,
    )


def load_policy(path=DEFAULT_POLICY_PATH):
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Assistant policy file is empty.")
    return text


class GenerationInterrupted(Exception):
    """Internal control flow for a user-interrupted model generation."""


def _has_explicit_user_intent(normalized_text):
    return any(phrase in normalized_text for phrase in (
        "i want", "i'd like", "i would like", "i plan", "i intend",
        "my goal", "i'm going to", "i am going to", "i will ",
        "we plan", "we want", "our goal",
    ))


def _is_speculative_non_memory_observation(normalized_text):
    """Reject future/roleplay framing unless the user explicitly expresses intent."""
    future_markers = (
        "one day", "in the future", "you will be able", "you'll be able",
        "when you can", "imagine", "would be", "could be",
    )
    return (
        not _has_explicit_user_intent(normalized_text)
        and any(marker in normalized_text for marker in future_markers)
    )


class AssistantSession:
    def __init__(self, config, persona, chat=None, memory_loader=list_assistant_memories,
                 memory_creator=create_assistant_memory, memory_searcher=search_assistant_memories,
                 memory_updater=update_assistant_memory, debug_level=None, policy=None, proposal_creator=None,
                 stream=False, stream_writer=None, model_lister=None, provider: ChatProvider | None = None,
                 capability_manifest: CapabilityManifest | None = None, retriever: MemoryRetriever | None = None,
                 persona_development_state: PersonaDevelopmentState | None = None,
                 persona_registry: PersonaRegistry | None = None,
                 persona_runtime_registry: PersonaRuntimeRegistry | None = None,
                 adventure_registry: AdventureRegistry | None = None):
        if config.max_session_messages <= 0:
            raise ValueError("max_session_messages must be positive")
        if provider is not None and chat is not None:
            raise ValueError("Provide either provider or legacy chat, not both.")
        self.config = config
        if persona_registry is not None and not isinstance(persona_registry, PersonaRegistry):
            raise TypeError("persona_registry must be a PersonaRegistry or None.")
        package = persona if isinstance(persona, PersonaPackage) else None
        self.persona_registry = persona_registry or (PersonaRegistry((package,)) if package is not None else None)
        self.persona = package.persona if package is not None else (persona if hasattr(persona, "render_prompt") else Persona(str(persona)))
        initial_persona_state = package.initial_state if package is not None else load_persona_state(getattr(config, "persona_path", None))
        if persona_runtime_registry is not None and not isinstance(persona_runtime_registry, PersonaRuntimeRegistry):
            raise TypeError("persona_runtime_registry must be a PersonaRuntimeRegistry or None.")
        if self.persona_registry is not None and self.persona_registry.get(initial_persona_state.persona_id) is None:
            raise ValueError("active persona must be registered in persona_registry.")
        requested_development_state = persona_development_state or PersonaDevelopmentState.empty(
            initial_persona_state.persona_id
        )
        if requested_development_state.persona_id != initial_persona_state.persona_id:
            raise ValueError("persona_development_state persona_id must match the active persona.")
        self.persona_runtime_registry = persona_runtime_registry or PersonaRuntimeRegistry()
        runtime = self.persona_runtime_registry.ensure(initial_persona_state, requested_development_state)
        self.persona_runtime_state = runtime
        self.persona_state = runtime.persona_state
        self.persona_development_state = runtime.development_state
        self.policy = policy or load_policy()
        self.context_manager = ContextManager()
        self.capability_manifest = capability_manifest
        # chat= remains accepted for fakes and existing integrations while
        # all assistant calls now travel through the explicit provider API.
        self.provider = provider or (
            CallableChatProvider(chat, model_lister=model_lister)
            if chat is not None
            else OllamaChatProvider(ollama)
        )
        self.chat = self.provider.complete  # Compatibility for callers inspecting this attribute.
        self._provider_name = getattr(self.provider, "name", type(self.provider).__name__)
        self.provider_lifecycle = ProviderLifecycle(self._provider_name, config.chat_model)
        # Configuration remains the startup default. Switching is deliberately
        # session-only so it cannot rewrite a user's configuration or data.
        self.active_model = config.chat_model
        self.model_lister = model_lister
        self.memory_loader = memory_loader
        self._uses_default_memory_store = memory_loader is list_assistant_memories
        self.retriever = retriever or (
            DeterministicMemoryRetriever()
            if self._uses_default_memory_store else MemoryLoaderRetriever(memory_loader)
        )
        self._validate_retriever(self.retriever)
        self.memory_creator = memory_creator
        self.memory_searcher = memory_searcher
        self.memory_updater = memory_updater
        self.proposal_creator = proposal_creator
        self.stream = stream
        self.stream_writer = stream_writer
        self.messages = []
        self.roleplay_state = RoleplaySessionState.inactive()
        self.adventure_registry = adventure_registry or AdventureRegistry(
            getattr(config, "adventure_root", PROJECT_ROOT / "adventures")
        )
        self.adventure_session = AdventureSessionState.unmounted()
        self.proposals = []
        self.last_memory_ids = []
        self._pending_bulk_proposal_ids = None
        self.last_turn_diagnostics = None
        self._current_context_diagnostics = None
        self._current_proposal_diagnostics = {"ran": False, "outcome": "skipped"}
        self._generation_started_at = None
        self._first_token_seconds = None
        self._turn_started_at = None
        self.debug_level = normalize_debug_level(debug_level or getattr(config, "debug_level", "off"))
        self.trace = RetrievalTrace(self.debug_level)

    def set_capability_manifest(self, capability_manifest: CapabilityManifest | None) -> None:
        """Attach presentation-neutral core capabilities without changing session state."""
        if capability_manifest is not None and not isinstance(capability_manifest, CapabilityManifest):
            raise TypeError("capability_manifest must be a CapabilityManifest or None.")
        self.capability_manifest = capability_manifest

    @staticmethod
    def _validate_retriever(retriever) -> None:
        if not callable(getattr(retriever, "retrieve", None)):
            raise TypeError("retriever must provide a callable retrieve method.")

    def set_retriever(self, retriever: MemoryRetriever) -> None:
        """Attach a read-only retrieval dependency without changing memory data."""
        self._validate_retriever(retriever)
        self.retriever = retriever

    def _display_memory_id(self, memory):
        memory_id = memory.get("id")
        if memory_id is None:
            return "unknown"
        if self._uses_default_memory_store:
            return assistant_public_id("memory", memory_id, self.config.domain)
        return f"M-{int(memory_id):03d}"

    def _shared_memory_visibility_policy(self) -> SharedMemoryVisibilityPolicy:
        package = (
            self.persona_registry.get(self.persona_state.persona_id)
            if self.persona_registry is not None else None
        )
        if package is not None:
            return package.shared_memory_visibility_policy
        return SharedMemoryVisibilityPolicy(self.persona_state.persona_id)

    def _apply_shared_memory_visibility(self, retrieved):
        """Filter already-ranked records without changing their ordering or scores."""
        policy = self._shared_memory_visibility_policy()
        visible = []
        decisions = []
        for item in retrieved:
            memory = item.get("memory", {})
            confidence = memory.get("confidence")
            if confidence is None:
                allowed = policy.minimum_shared_memory_confidence == 0.0
                decision = {
                    "persona_id": policy.persona_id,
                    "source_confidence": None,
                    "minimum_shared_memory_confidence": policy.minimum_shared_memory_confidence,
                    "visible": allowed,
                    "knowledge_confidence": None,
                    "reason": (
                        "memory confidence unavailable; retained by backward-compatible zero threshold"
                        if allowed else "memory confidence unavailable; cannot satisfy persona threshold"
                    ),
                }
            else:
                decision = evaluate_shared_memory_visibility(policy, confidence).public_dict()
                allowed = decision["visible"]
            confidence_visible = allowed
            confidence_reason = decision["reason"]
            scope_decision = evaluate_shared_memory_scope_visibility(
                policy,
                memory.get("memory_type"),
                memory.get("visibility_scope"),
            ).public_dict()
            scope_visible = scope_decision["visible"]
            allowed = confidence_visible and scope_visible
            decision.update({
                "memory_type": scope_decision["memory_type"],
                "memory_scope": scope_decision["memory_scope"],
                "explicit_visibility_scope": memory.get("visibility_scope"),
                "allowed_memory_scopes": scope_decision["allowed_memory_scopes"],
                "confidence_visible": confidence_visible,
                "confidence_reason": confidence_reason,
                "scope_visible": scope_visible,
                "scope_reason": scope_decision["reason"],
                "visible": allowed,
                "reason": f"confidence: {confidence_reason}; scope: {scope_decision['reason']}",
            })
            decision["public_id"] = self._display_memory_id(memory)
            decisions.append(decision)
            if allowed:
                visible.append(item)
        return visible, decisions

    def _begin_turn_diagnostics(self, plan: ContextPlan, retrieved, phase_timings=None, visibility_decisions=()):
        selected = []
        for item in retrieved:
            memory = item.get("memory", {})
            selected.append({
                "public_id": self._display_memory_id(memory),
                "score": item.get("score"),
                "reasons": list(item.get("reasons") or []),
                "origin": item.get("origin", "assistant memory"),
            })
        self._current_context_diagnostics = {
            "model": self.active_model,
            "provider": self._provider_name,
            "persona_characters": plan.persona.characters,
            "behavior_characters": plan.behavior.characters,
            "behavior_estimated_tokens": plan.behavior.estimated_tokens,
            "persona_attention_characters": plan.persona_attention.characters,
            "persona_attention_estimated_tokens": plan.persona_attention.estimated_tokens,
            "adventure_characters": plan.adventure.characters,
            "adventure_estimated_tokens": plan.adventure.estimated_tokens,
            "policy_characters": plan.policy.characters,
            "recent_message_count": len(plan.messages) - 2,
            "recent_characters": plan.recent_conversation.characters,
            "recent_estimated_tokens": plan.recent_conversation.estimated_tokens,
            "retrieved": selected,
            "shared_memory_visibility": list(visibility_decisions),
            "external_document_characters": plan.external_document.characters,
            "external_document_estimated_tokens": plan.external_document.estimated_tokens,
            "selected_document_chunk_ids": list(plan.selected_document_chunk_ids),
            "selected_capability_ids": list(plan.selected_capability_ids),
            "capability_characters": plan.capabilities.characters,
            "prompt_characters": plan.prompt_characters,
            "prompt_estimated_tokens": plan.prompt_estimated_tokens,
            "ollama_options": self._ollama_options(),
            "roleplay_session": self.roleplay_state.public_dict(),
            "adventure_session": self.adventure_session.public_dict(),
            "phase_timings": dict(phase_timings or {}),
        }

    def _finish_turn_diagnostics(self, *, completed, response, latency_seconds, proposal=None, status=None):
        context = self._current_context_diagnostics or {}
        self.last_turn_diagnostics = {
            **context,
            "completed": completed,
            "turn_status": status or ("completed" if completed else "interrupted"),
            "response_characters": len(response or ""),
            "response_latency_ms": round(latency_seconds * 1000, 2),
            "time_to_first_token_ms": (
                round(self._first_token_seconds * 1000, 2)
                if self._first_token_seconds is not None else None
            ),
            "proposal_ran": bool((proposal or {}).get("ran")),
            "proposal_outcome": (proposal or {}).get("outcome", "skipped"),
            "completion_estimated_tokens": estimate_tokens(response or ""),
            "total_turn_ms": round((time.perf_counter() - self._turn_started_at) * 1000, 2) if self._turn_started_at is not None else None,
        }
        self._current_context_diagnostics = None
        self._generation_started_at = None
        self._first_token_seconds = None
        self._turn_started_at = None

    def context_stats(self):
        """Render the bounded diagnostics snapshot without touching any service."""
        snapshot = self.last_turn_diagnostics
        if snapshot is None:
            return "No turn diagnostics are available yet."
        persona_chars = snapshot.get("persona_characters", 0)
        behavior_chars = snapshot.get("behavior_characters", 0)
        attention_chars = snapshot.get("persona_attention_characters", 0)
        policy_chars = snapshot.get("policy_characters", 0)
        lines = [
            "=== CONTEXT STATS ===",
            f"Turn: {snapshot.get('turn_status', 'completed' if snapshot.get('completed') else 'interrupted')}",
            f"Provider: {snapshot.get('provider', 'unknown')}",
            f"Model: {snapshot.get('model', 'unknown')}",
            "Generation options: " + self._format_ollama_options(snapshot.get("ollama_options", {})),
            f"Persona: {persona_chars} characters (estimated {(persona_chars + 3) // 4} tokens)",
            f"Persona runtime state: {behavior_chars} characters (estimated {snapshot.get('behavior_estimated_tokens', 0)} tokens)",
            f"Persona attention: {attention_chars} characters (estimated {snapshot.get('persona_attention_estimated_tokens', 0)} tokens)",
            f"Adventure context: {snapshot.get('adventure_characters', 0)} characters (estimated {snapshot.get('adventure_estimated_tokens', 0)} tokens)",
            f"Policy: {policy_chars} characters (estimated {(policy_chars + 3) // 4} tokens)",
            f"Recent conversation: {snapshot.get('recent_message_count', 0)} messages, {snapshot.get('recent_characters', 0)} characters (estimated {snapshot.get('recent_estimated_tokens', 0)} tokens)",
            "Roleplay session: " + (
                f"active ({snapshot['roleplay_session'].get('title') or 'unnamed'}; session-ephemeral)"
                if snapshot.get("roleplay_session", {}).get("active") else "inactive"
            ),
            "Adventure workspace: " + (
                f"loaded ({snapshot['adventure_session'].get('title')}; session-ephemeral metadata mount)"
                if snapshot.get("adventure_session", {}).get("mounted") else "none loaded"
            ),
            f"Retrieved memories: {len(snapshot.get('retrieved', []))}",
        ]
        selected = snapshot.get("retrieved", [])
        lines.append("Selected memory IDs: " + (", ".join(item["public_id"] for item in selected) if selected else "(none)"))
        visibility = snapshot.get("shared_memory_visibility", [])
        if visibility:
            policy_persona = visibility[0]["persona_id"]
            threshold = visibility[0]["minimum_shared_memory_confidence"]
            visible_count = sum(1 for item in visibility if item["visible"])
            lines.append(
                "Shared-memory visibility: "
                f"{policy_persona}, threshold {threshold:.2f}; {visible_count}/{len(visibility)} visible"
            )
            hidden = [item["public_id"] for item in visibility if not item["visible"]]
            if hidden:
                lines.append("Hidden memory IDs: " + ", ".join(hidden))
            lines.append("Visibility details:")
            for item in visibility:
                confidence = "unavailable" if item["source_confidence"] is None else f"{item['source_confidence']:.3f}"
                state = "visible" if item["visible"] else "hidden"
                lines.append(f"  {item['public_id']} confidence={confidence} {state}: {item['reason']}")
                scope = item.get("memory_scope") or "unmapped"
                lines.append(
                    f"    scope: {scope} ({'allowed' if item.get('scope_visible') else 'denied'})"
                )
        capability_ids = snapshot.get("selected_capability_ids", [])
        if capability_ids:
            lines.append("Capability context: " + ", ".join(capability_ids))
        document_chunks = snapshot.get("selected_document_chunk_ids", [])
        if document_chunks:
            lines.append(
                "External document context: "
                f"{len(document_chunks)} chunk(s), {snapshot.get('external_document_characters', 0)} characters "
                f"(estimated {snapshot.get('external_document_estimated_tokens', 0)} tokens)"
            )
            lines.append("Selected document chunks: " + ", ".join(document_chunks))
        if selected:
            lines.append("Retrieval details:")
            for item in selected:
                score = "unscored" if item["score"] is None else f"{item['score']:.6g}"
                lines.append(f"  {item['public_id']} score={score}")
                lines.append("    reasons: " + ("; ".join(item["reasons"]) if item["reasons"] else "(none)"))
                if item.get("origin") != "assistant memory":
                    lines.append(f"    origin: {item['origin']}")
        lines.extend([
            f"Prompt: {snapshot.get('prompt_characters', 0)} characters (estimated {snapshot.get('prompt_estimated_tokens', 0)} tokens)",
            f"Completion: {snapshot.get('response_characters', 0)} characters (estimated {snapshot.get('completion_estimated_tokens', 0)} tokens)",
            f"Response: {snapshot.get('response_characters', 0)} characters",
            f"Response latency: {snapshot.get('response_latency_ms', 0):.2f} ms",
            "Time to first streamed token: " + (f"{snapshot['time_to_first_token_ms']:.2f} ms" if snapshot.get("time_to_first_token_ms") is not None else "unavailable"),
            f"Prompt build time: {self._format_phase_ms(snapshot, 'prompt_build_ms')}",
            f"Retrieval time: {self._format_phase_ms(snapshot, 'retrieval_ms')}",
            f"Association time: {self._format_phase_ms(snapshot, 'association_ms')}",
            f"Provider time: {snapshot.get('response_latency_ms', 0):.2f} ms",
            f"Proposal time: {self._format_phase_ms(snapshot, 'proposal_ms')}",
            f"Total turn time: {self._format_phase_ms(snapshot, 'total_turn_ms')}",
            f"Proposal extraction ran: {'yes' if snapshot.get('proposal_ran') else 'no'}",
            f"Proposal outcome: {snapshot.get('proposal_outcome', 'skipped')}",
            "=== END CONTEXT STATS ===",
        ])
        return "\n".join(lines)

    @staticmethod
    def _format_phase_ms(snapshot, name):
        value = snapshot.get(name)
        if value is None:
            value = (snapshot.get("phase_timings") or {}).get(name)
        return "unavailable" if value is None else f"{value:.2f} ms"

    def _ollama_options(self):
        """Return a fresh provider options dict without mutating configuration."""
        return dict(getattr(self.config, "ollama_options", {}) or {})

    @staticmethod
    def _format_ollama_options(options):
        if not options:
            return "provider defaults"
        return ", ".join(f"{name}={options[name]}" for name in sorted(options))

    def _task_profile(self, task_id, *, model=None):
        profiles = getattr(self.config, "task_profiles", TaskProfiles())
        profile = profiles.resolve(
            task_id,
            default_model=model or self.active_model,
            base_options=self._ollama_options(),
        )
        if not provider_matches(profile.provider, getattr(self.provider, "name", None)):
            raise RuntimeError(
                f"Task profile {task_id!r} requires provider {profile.provider!r}; "
                f"active provider is {getattr(self.provider, 'name', 'unknown')!r}."
            )
        return profile

    def _model_request_kwargs(self, messages, *, model=None, task_id=TASK_ASSISTANT_CHAT):
        profile = self._task_profile(task_id, model=model)
        kwargs = {"model": profile.model, "messages": messages}
        options = dict(profile.options)
        if options:
            kwargs["options"] = options
        return kwargs

    def _provider_complete(self, messages, *, model=None, stream=False, task_id=TASK_ASSISTANT_CHAT):
        """Call the selected provider through the stable chat boundary."""
        kwargs = self._model_request_kwargs(messages, model=model, task_id=task_id)
        self.provider_lifecycle.begin_generation(stream=stream, model=kwargs["model"])
        try:
            response = self.provider.complete(
                kwargs["messages"],
                model=kwargs["model"],
                options=kwargs.get("options"),
                stream=stream,
            )
            if not stream:
                self.provider_lifecycle.finish()
            return response
        except Exception as error:
            self.provider_lifecycle.fail(error)
            raise
    def _chat_complete(self, messages, *, model=None, stream=None, task_id=TASK_ASSISTANT_CHAT):
        """Return complete content while optionally rendering streamed chunks."""
        use_stream = self.stream if stream is None else stream
        if not use_stream:
            response = self._provider_complete(messages, model=model, task_id=task_id)
            self.provider_lifecycle.finish()
            return response.get("message", {}).get("content", "")
        try:
            response = self._provider_complete(messages, model=model, stream=True, task_id=task_id)
            if isinstance(response, dict):
                self.provider_lifecycle.finish()
                return response.get("message", {}).get("content", "")
            parts = []
            for chunk in response:
                if isinstance(chunk, dict):
                    message = chunk.get("message", {}) or {}
                    piece = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
                else:
                    message = getattr(chunk, "message", None)
                    piece = getattr(message, "content", "") if message is not None else ""
                if piece:
                    if self._generation_started_at is not None and self._first_token_seconds is None:
                        self._first_token_seconds = time.perf_counter() - self._generation_started_at
                    parts.append(piece)
                    if self.stream_writer:
                        self.stream_writer(piece)
            self.provider_lifecycle.finish()
            return "".join(parts)
        except KeyboardInterrupt as error:
            self.provider_lifecycle.fail("Generation interrupted")
            raise GenerationInterrupted() from error
        except Exception as error:
            self.provider_lifecycle.fail(error)
            raise

    def _context_plan(self, user_text, *, external_document_context=None):
        self.trace = RetrievalTrace(self.debug_level)
        phase_timings = {}
        retrieval_started = time.perf_counter()
        retrieved = self.retriever.retrieve(
            user_text,
            domain=self.config.domain,
            limit=max(1, self.config.max_memories),
            timings=phase_timings,
        )
        phase_timings.setdefault(
            "retrieval_ms",
            round((time.perf_counter() - retrieval_started) * 1000, 2),
        )
        phase_timings.setdefault("association_ms", 0.0)
        retrieved, visibility_decisions = self._apply_shared_memory_visibility(retrieved)
        memories = [item["memory"] for item in retrieved]
        prompt_started = time.perf_counter()
        recent = self.messages[-self.config.max_session_messages:]
        selected_capabilities = (
            self.capability_manifest.select_for_query(user_text)
            if self.capability_manifest is not None else ()
        )
        persona_attention = select_persona_attention(
            user_text,
            self.persona_development_state,
            as_of=datetime.now(timezone.utc),
        )
        plan = self.context_manager.build_chat(
            persona_text=self.persona.render_prompt(),
            policy_text=self.policy,
            recent_messages=recent,
            retrieved_memories=memories,
            capabilities=selected_capabilities,
            behavior_context=BehaviorContext.from_persona_state(self.persona_state),
            persona_attention=persona_attention,
            external_document_context=external_document_context,
            roleplay_context=self.roleplay_state.context_text(),
            adventure_context=self.adventure_session.context_text(),
            user_text=user_text,
        )
        phase_timings["prompt_build_ms"] = round((time.perf_counter() - prompt_started) * 1000, 2)
        self.last_memory_ids = list(plan.selected_memory_ids)
        self.trace.record(
            "memory_lookup",
            domain=self.config.domain,
            count=len(memories),
            query=user_text,
            results=retrieved,
        )
        self.trace.record(
            "context_assembly",
            domain=self.config.domain,
            selected_count=len(memories),
            message_count=len(self.messages) + 1,
            context=plan.retrieved_memory.text,
            capability_ids=list(plan.selected_capability_ids),
            document_chunk_ids=list(plan.selected_document_chunk_ids),
            persona_attention=[item.concept for item in persona_attention.items],
        )
        self._begin_turn_diagnostics(plan, retrieved, phase_timings, visibility_decisions)
        return plan

    def _proposal(self, user_text, assistant_text=None):
        self._current_proposal_diagnostics = {"ran": False, "outcome": "skipped"}
        if self.config.memory_policy == "off":
            return None
        # Questions and information requests are not user observations. This
        # application-level guard prevents model answers from becoming memory.
        normalized = user_text.strip().casefold()
        question_starters = ("who ", "what ", "when ", "where ", "why ", "how ", "can ", "could ", "would ", "do ", "does ", "did ", "is ", "are ", "will ", "tell ", "explain ", "define ", "describe ", "list ", "give ", "show ", "summarize ", "help ")
        if normalized.endswith("?") or normalized.startswith(question_starters):
            self.trace.record("proposal_skipped", reason="user_question", source="user_observation")
            return None
        if _is_speculative_non_memory_observation(normalized):
            self.trace.record("proposal_skipped", reason="speculative_without_explicit_intent", source="user_observation")
            return None
        self._current_proposal_diagnostics["ran"] = True
        taxonomy = assistant_memory_type_prompt()
        system_prompt = (
            "Return ONLY one JSON object. Extract facts ONLY from the USER OBSERVATION below. "
            "The user observation is the sole authoritative source. Never use assistant-generated content, "
            "general knowledge, answers, questions, requests, roleplay, jokes, metaphors, hypotheticals, "
            "invented history, filler, or suggestions as memory evidence. If the user observation does not "
            "clearly state a durable fact about the user or their project, return store=false. Future wishes or "
            "plans are eligible only when the user explicitly expresses their own intent (for example, 'I plan "
            "to...' or 'I want to...'). Playful statements about what the assistant may do one day are not user "
            "memories and must return store=false. Choose the most specific type below; never default broadly to "
            "personal_fact. For an explicit correction, classify "
            "the corrected fact by its underlying type and state the correction in details. If the observation "
            "is ambiguous, return store=false rather than guessing. MEMORY TYPE TAXONOMY:\n"
            + taxonomy
            + "\nAllowed retention values are exactly: session, short_term, long_term. importance and confidence "
            "must be JSON numbers from 0.0 to 1.0, never labels. Required fields: store, subject, memory_type, "
            "summary, details, importance, confidence, retention. The engine supplies domain and source."
        )
        prompt = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"USER OBSERVATION (sole evidence source):\n{user_text}"},
        ]
        self.trace.record("proposal_request", model=self.active_model, messages=prompt, domain=self.config.domain, source="assistant_turn_proposal")
        response = self._provider_complete(prompt, task_id=TASK_ASSISTANT_PROPOSAL)
        content = response.get("message", {}).get("content", "").strip()
        self.trace.record("proposal_response", status="received" if content else "empty", response=content)
        try:
            raw = json.loads(content)
            raw.pop("domain", None)
            raw.pop("source", None)
            raw["domain"] = self.config.domain
            raw["source"] = "assistant_turn_proposal"
            proposal = validate_memory_proposal(raw, self.config.domain)
        except Exception as error:
            self.trace.record("proposal_validation", status="invalid", error=str(error))
            repair_prompt = [
                {"role": "system", "content": "Return ONLY corrected JSON. Do not add facts. Use the most specific valid memory_type from the taxonomy. Use numeric importance/confidence. Return store=false if uncertain or ambiguous."},
                {"role": "user", "content": f"Invalid proposal: {content}\nValidation error: {error}\nMEMORY TYPE TAXONOMY:\n{taxonomy}\nAllowed retention: session, short_term, long_term"},
            ]
            self.trace.record("proposal_repair_request", attempt=1, messages=repair_prompt)
            repaired = self._provider_complete(repair_prompt, task_id=TASK_ASSISTANT_PROPOSAL)
            repaired_content = repaired.get("message", {}).get("content", "").strip()
            self.trace.record("proposal_repair_response", status="received" if repaired_content else "empty", response=repaired_content)
            raw = json.loads(repaired_content)
            raw.pop("domain", None)
            raw.pop("source", None)
            raw["domain"] = self.config.domain
            raw["source"] = "assistant_turn_proposal"
            proposal = validate_memory_proposal(raw, self.config.domain)
        self.trace.record("proposal_validation", status="accepted", store=proposal["store"], domain=proposal["domain"])
        if proposal["store"] and self.roleplay_state.active:
            # The model never selects a scope. An explicit Core-owned session
            # state adds this metadata only after normal validation succeeds.
            proposal["visibility_scope"] = "roleplay"
        if proposal["store"] and self.proposal_creator:
            result = self.proposal_creator(proposal, domain=self.config.domain, observation_text=user_text)
            proposal["id"] = result.get("proposal_id", result) if isinstance(result, dict) else result
            action = result.get("action", "created") if isinstance(result, dict) else "created"
            self._current_proposal_diagnostics["outcome"] = action
            self.trace.record("proposal_persisted", proposal_id=proposal["id"], status=action)
        elif proposal["store"]:
            self._current_proposal_diagnostics["outcome"] = "created"
        else:
            self._current_proposal_diagnostics["outcome"] = "store_false"
        self.proposals.append(proposal)
        return proposal

    def explicit_remember(self, text):
        summary = text.strip()
        if not summary:
            raise ValueError("Remember command needs content.")
        memory_id = self.memory_creator(
            subject="User", memory_type="personal_fact", summary=summary,
            importance=0.9, confidence=1.0, retention="long_term",
            source="explicit:user", domain=self.config.domain,
            **({"visibility_scope": "roleplay"} if self.roleplay_state.active else {}),
        )
        return f"Remembered (memory {assistant_public_id('memory', memory_id, self.config.domain)})."

    def explicit_forget(self, text):
        reference = text.strip()
        memory_id = resolve_assistant_id(reference, "memory", self.config.domain)
        if memory_id is not None:
            memory = get_assistant_memory(memory_id, domain=self.config.domain)
            if memory is None or memory.get("status") != "active":
                return "No active matching memory found."
            self.memory_updater(memory["id"], domain=self.config.domain, status="forgotten")
            return f"Forgotten memory {assistant_public_id('memory', memory['id'], self.config.domain)}."
        matches = self.memory_searcher(reference, domain=self.config.domain, status="active", limit=1)
        if not matches:
            return "No active matching memory found."
        memory = matches[0]
        self.memory_updater(memory["id"], domain=self.config.domain, status="forgotten")
        return f"Forgotten memory {assistant_public_id('memory', memory['id'], self.config.domain)}."

    def _approve_all_pending(self):
        proposal_ids = self._pending_bulk_proposal_ids or []
        self._pending_bulk_proposal_ids = None
        approved = []
        failed = []
        for proposal_id in proposal_ids:
            try:
                memory = approve_assistant_memory_proposal(proposal_id, domain=self.config.domain)
                approved.append((proposal_id, memory["id"] if memory else None))
            except ValueError as error:
                failed.append((proposal_id, str(error)))
        lines = [f"Approved {len(approved)} proposal(s)."]
        for proposal_id, memory_id in approved:
            memory_ref = assistant_public_id("memory", memory_id, self.config.domain) if memory_id is not None else "(memory unavailable)"
            lines.append(f"  {assistant_public_id('proposal', proposal_id, self.config.domain)} -> {memory_ref}")
        if failed:
            lines.append(f"Skipped {len(failed)} proposal(s) that were no longer pending.")
            for proposal_id, error in failed:
                lines.append(f"  {assistant_public_id('proposal', proposal_id, self.config.domain)}: {error}")
        return "\n".join(lines)

    def _review_bulk_approval(self):
        rows = list_assistant_memory_proposals(domain=self.config.domain, status="pending")
        if not rows:
            self._pending_bulk_proposal_ids = None
            return "No pending assistant proposals."
        self._pending_bulk_proposal_ids = [row["id"] for row in rows]
        lines = [f"Pending proposals in domain {self.config.domain}:"]
        warnings = []
        for row in rows:
            lines.append(f"  {assistant_public_id('proposal', row['id'], self.config.domain)} [{row['memory_type']}] {row['summary']} (confidence {row.get('confidence', 'unknown')}, importance {row.get('importance', 'unknown')})")
            if isinstance(row.get("confidence"), (int, float)) and row["confidence"] < 0.7:
                warnings.append(f"{assistant_public_id('proposal', row['id'], self.config.domain)} has low confidence")
        if warnings:
            lines.append("Warnings:")
            lines.extend(f"  - {warning}" for warning in warnings)
        lines.append('Type "approve all" to continue, or anything else to cancel.')
        return "\n".join(lines)

    def _installed_model_names(self):
        """Return normalized installed Ollama model names in stable order."""
        lister = self.model_lister or getattr(self.provider, "list_models", None)
        if not callable(lister):
            raise RuntimeError("Unable to list Ollama models: Ollama model listing is unavailable.")
        try:
            response = lister()
        except Exception as error:
            raise RuntimeError(f"Unable to list Ollama models: {error}") from error
        models = response.get("models", []) if isinstance(response, dict) else getattr(response, "models", [])
        names = []
        for model in models or []:
            if isinstance(model, dict):
                name = model.get("model") or model.get("name")
            else:
                name = getattr(model, "model", None) or getattr(model, "name", None)
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        return sorted(set(names), key=str.casefold)

    def model_list(self):
        names = self._installed_model_names()
        if not names:
            return "No Ollama models are installed."
        lines = ["Installed Ollama models:"]
        for name in names:
            marker = "*" if name == self.active_model else " "
            suffix = " (active)" if name == self.active_model else ""
            lines.append(f"{marker} {name}{suffix}")
        return "\n".join(lines)

    def model_current(self):
        return f"Active model: {self.active_model}"

    def model_use(self, requested_name):
        requested_name = requested_name.strip()
        if not requested_name:
            return "Usage: model use <model-name>"
        names = self._installed_model_names()
        selected = next((name for name in names if name.casefold() == requested_name.casefold()), None)
        if selected is None:
            return f"Model not installed: {requested_name}"
        if selected == self.active_model:
            return f"Model is already active: {selected}"
        self.active_model = selected
        self.trace.record("model_selected", model=selected)
        return f"Active model set to: {selected}"

    def persona_inspect(self):
        """Return a read-only, bounded persona-runtime diagnostic."""
        state = self.persona_state
        development = self.persona_development_state
        traits = state.dynamic_traits.public_dict()
        momentary = state.momentary_state.public_dict()
        guidance = derive_behavior_guidance(BehaviorContext.from_persona_state(state)).public_dict()
        lines = [
            "Persona Runtime",
            f"ID: {state.persona_id}",
            f"Display name: {state.display_name}",
            f"Static identity: {len(state.static_identity)} characters (not displayed)",
            "Dynamic traits:",
        ]
        lines.extend(f"  {name}: {traits[name]:.2f}" for name in sorted(traits))
        lines.extend([
            "Momentary state:",
            f"  energy: {momentary['energy']:.2f}",
            f"  attention: {momentary['attention']:.2f}",
            f"  valence: {momentary['valence']:.2f}",
            f"  activity: {momentary['activity']}",
            "Derived behavior controls:",
        ])
        lines.extend(
            f"  {name}: {guidance[name]:.2f}"
            for name in (
                "warmth", "directness", "humor", "initiative", "patience", "verbosity",
                "clarification_threshold", "interruption_tolerance",
            )
        )
        lines.extend([
            "Persona-local development:",
            f"  interests: {len(development.interests)}",
            f"  verified skills: {len(development.skills)}",
            f"  learning records: {len(development.learning_records)}",
            f"  reference records: {len(development.reference_records)}",
            f"  real-world relationships: {len(self.persona_runtime_state.relationship_states)}",
            "  storage: restart-ephemeral",
            "Read-only runtime snapshot; its bounded behavior guidance is injected into normal chat prompts.",
        ])
        return "\n".join(lines)

    def persona_list(self):
        if self.persona_registry is None:
            return "No persona packages are configured for this session."
        lines = ["Configured persona packages:"]
        for package in self.persona_registry.packages():
            suffix = " (active)" if package.persona_id == self.persona_state.persona_id else ""
            lines.append(f"{'*' if suffix else ' '} {package.persona_id} - {package.display_name}{suffix}")
        return "\n".join(lines)

    def persona_current(self):
        return f"Active persona: {self.persona_state.persona_id} ({self.persona_state.display_name})"

    def persona_use(self, requested_id):
        requested_id = requested_id.strip().casefold()
        if not requested_id:
            return "Usage: persona use <persona-id>"
        if self.persona_registry is None:
            return "No persona packages are configured for this session."
        package = self.persona_registry.get(requested_id)
        if package is None:
            return f"Persona package not found: {requested_id}"
        if package.persona_id == self.persona_state.persona_id:
            return f"Persona is already active: {package.persona_id}"
        self.persona = package.persona
        runtime = self.persona_runtime_registry.ensure(package.initial_state)
        self.persona_runtime_state = runtime
        self.persona_state = runtime.persona_state
        self.persona_development_state = runtime.development_state
        self.messages.clear()
        self.last_memory_ids = []
        self._pending_bulk_proposal_ids = None
        self.last_turn_diagnostics = None
        self.trace.record("persona_selected", persona_id=package.persona_id)
        return f"Active persona set to: {package.persona_id}. Recent conversation context was cleared."

    def _set_roleplay_state(self, state):
        self.roleplay_state = state
        self.messages.clear()
        self.last_memory_ids = []

    def roleplay_begin(self, title=None):
        try:
            self._set_roleplay_state(self.roleplay_state.begin(title))
        except (TypeError, ValueError) as error:
            return f"Assistant error: {error}"
        label = f" ({self.roleplay_state.title})" if self.roleplay_state.title else ""
        return f"Roleplay mode started{label}. Recent conversation context was cleared; eligible new memories are roleplay-scoped."

    def roleplay_end(self):
        if not self.roleplay_state.active:
            return "Roleplay mode is not active."
        self._set_roleplay_state(self.roleplay_state.end())
        return "Roleplay mode ended. Recent conversation context was cleared."

    def roleplay_status(self):
        if not self.roleplay_state.active:
            return "Roleplay mode: inactive."
        label = self.roleplay_state.title or "unnamed"
        return f"Roleplay mode: active ({label}; session-ephemeral, no adventure workspace loaded)."

    def adventure_list(self):
        """List only registered workspace metadata; this never mounts a story."""
        try:
            records = self.adventure_registry.list()
        except AdventureRegistryError as error:
            return f"Adventure registry error: {error}"
        if not records:
            return "No adventure workspaces are registered."
        lines = ["Registered adventure workspaces:"]
        lines.extend(f"  {record.title} ({record.adventure_id}; {record.status})" for record in records)
        return "\n".join(lines)

    def adventure_create(self, title):
        if not title or not title.strip():
            return "Usage: adventure create <title>"
        try:
            record = self.adventure_registry.create(title)
        except (AdventureRegistryError, TypeError) as error:
            return f"Adventure workspace was not created: {error}"
        return (
            f"Created adventure workspace: {record.title} ({record.adventure_id}). "
            "It is metadata-only and is not loaded into this conversation yet."
        )

    def adventure_inspect(self, title):
        if not title or not title.strip():
            return "Usage: adventure inspect <title>"
        try:
            record = self.adventure_registry.resolve_title(title)
        except AdventureNotFoundError:
            return "Adventure workspace not found."
        except (AdventureRegistryError, TypeError) as error:
            return f"Adventure registry error: {error}"
        return "\n".join((
            f"Adventure workspace: {record.title}",
            f"ID: {record.adventure_id}",
            f"Created: {record.created_at}",
            f"Status: {record.status}",
            "Storage: manifest only; no story event log, database, semantic index, or mounted session.",
        ))

    def _set_adventure_session(self, state):
        self.adventure_session = state
        self.messages.clear()
        self.last_memory_ids = []
        self.last_turn_diagnostics = None

    def adventure_load(self, title):
        if not title or not title.strip():
            return "Usage: adventure load <title>"
        try:
            record = self.adventure_registry.resolve_title(title)
        except AdventureNotFoundError:
            return "Adventure workspace not found."
        except (AdventureRegistryError, TypeError) as error:
            return f"Adventure registry error: {error}"
        if self.adventure_session.record == record:
            return f"Adventure workspace is already loaded: {record.title}."
        self._set_adventure_session(self.adventure_session.mount(record))
        return (
            f"Adventure workspace loaded: {record.title}. Recent conversation context was cleared. "
            "The workspace is metadata-only; no story, replay state, or roleplay mode was started."
        )

    def adventure_unload(self):
        if not self.adventure_session.active:
            return "No adventure workspace is loaded."
        title = self.adventure_session.record.title
        self._set_adventure_session(self.adventure_session.unmount())
        return f"Adventure workspace unloaded: {title}. Recent conversation context was cleared."

    def adventure_status(self):
        if not self.adventure_session.active:
            return "Adventure workspace: none loaded."
        record = self.adventure_session.record
        return (
            f"Adventure workspace: loaded ({record.title}; {record.adventure_id}; metadata-only, "
            "session-ephemeral mount; no story state or replay loaded)."
        )

    def command(self, text):
        lowered = text.strip().casefold()
        # Keep a tiny, explicit correction surface for typo-prone persona
        # diagnostics. Do not apply fuzzy matching to mutating commands.
        if lowered == "persona curretn":
            lowered = "persona current"
        if lowered == "context stats":
            return self.context_stats()
        if lowered == "roleplay status":
            return self.roleplay_status()
        if lowered == "roleplay end":
            return self.roleplay_end()
        if lowered == "roleplay begin" or lowered.startswith("roleplay begin "):
            return self.roleplay_begin(text.strip()[len("roleplay begin"):])
        if lowered in {"adventure list", "adventures"}:
            return self.adventure_list()
        if lowered == "adventure create" or lowered.startswith("adventure create "):
            return self.adventure_create(text.strip()[len("adventure create"):])
        if lowered == "adventure inspect" or lowered.startswith("adventure inspect "):
            return self.adventure_inspect(text.strip()[len("adventure inspect"):])
        if lowered == "adventure load" or lowered.startswith("adventure load "):
            return self.adventure_load(text.strip()[len("adventure load"):])
        if lowered in {"adventure unload", "adventure unmount"}:
            return self.adventure_unload()
        if lowered in {"adventure status", "what is loaded", "what is loaded?", "what's loaded", "what's loaded?"}:
            return self.adventure_status()
        if lowered == "persona inspect":
            return self.persona_inspect()
        if lowered in {"persona list", "list personas"}:
            return self.persona_list()
        if lowered == "persona current":
            return self.persona_current()
        if lowered == "persona use" or lowered.startswith("persona use "):
            return self.persona_use(text.strip()[len("persona use"):])
        if lowered in {"model list", "list models"}:
            try:
                return self.model_list()
            except RuntimeError as error:
                return str(error)
        if lowered == "model current":
            return self.model_current()
        if lowered == "model use" or lowered.startswith("model use "):
            try:
                return self.model_use(text.strip()[len("model use"):])
            except RuntimeError as error:
                return str(error)
        if lowered.startswith("remember this:") or lowered.startswith("remember:"):
            return self.explicit_remember(text.split(":", 1)[1])
        if lowered.startswith("forget this:") or lowered.startswith("forget:"):
            return self.explicit_forget(text.split(":", 1)[1])
        if lowered == "memory list":
            memories = self.memory_loader(domain=self.config.domain, status="active", limit=100)
            return "\n".join(f"{assistant_public_id('memory', m['id'], self.config.domain)} [{m['memory_type']}] {m['summary']}" for m in memories) or "No active memories."
        if lowered.startswith("memory search "):
            memories = self.memory_searcher(text.strip()[14:], domain=self.config.domain, status="active", limit=20)
            return "\n".join(f"{assistant_public_id('memory', m['id'], self.config.domain)} [{m['memory_type']}] {m['summary']}" for m in memories) or "No matching active memories."
        if lowered == "proposal list":
            rows = list_assistant_memory_proposals(domain=self.config.domain)
            return "\n".join(f"{assistant_public_id('proposal', row['id'], self.config.domain)} [{row['memory_type']}] {row['summary']}" for row in rows) or "No pending assistant proposals."
        if lowered == "proposal approve all":
            return self._review_bulk_approval()
        if lowered == "memory scope" or lowered.startswith("memory scope "):
            return self._set_memory_visibility_scope(text)
        if lowered == "proposal scope" or lowered.startswith("proposal scope "):
            return self._set_proposal_visibility_scope(text)
        if lowered.startswith("memory inspect"):
            parts = text.strip().split()
            if len(parts) != 3:
                return "Usage: memory inspect <M-### or numeric id>"
            memory_id = resolve_assistant_id(parts[2], "memory", self.config.domain)
            if memory_id is None:
                return "Memory not found."
            inspected = inspect_assistant_memory(memory_id, domain=self.config.domain)
            return format_assistant_memory(inspected) if inspected else "Memory not found."
        if lowered.startswith("proposal inspect"):
            parts = text.strip().split()
            if len(parts) != 3:
                return "Usage: proposal inspect <P-### or numeric id>"
            proposal_id = resolve_assistant_id(parts[2], "proposal", self.config.domain)
            if proposal_id is None:
                return "Proposal not found."
            inspected = inspect_assistant_memory_proposal(proposal_id, domain=self.config.domain)
            return format_assistant_memory_proposal(inspected) if inspected else "Proposal not found."
        for action, handler in (("approve", approve_assistant_memory_proposal), ("reject", reject_assistant_memory_proposal)):
            if lowered.startswith("proposal " + action + " "):
                parts = text.strip().split()
                if len(parts) != 3:
                    return f"Usage: proposal {action} <P-### or numeric id>"
                proposal_id = resolve_assistant_id(parts[2], "proposal", self.config.domain)
                if proposal_id is None:
                    return "Proposal not found."
                try:
                    if action == "approve":
                        memory = handler(proposal_id, domain=self.config.domain)
                        return f"Approved {assistant_public_id('proposal', proposal_id, self.config.domain)} as {assistant_public_id('memory', memory['id'], self.config.domain)}."
                    handler(proposal_id, domain=self.config.domain)
                    return f"Rejected {assistant_public_id('proposal', proposal_id, self.config.domain)}."
                except ValueError as error:
                    return f"Assistant error: {error}"
        return None

    def _parse_visibility_scope_command(self, text, *, kind):
        parts = text.strip().split()
        label = "memory" if kind == "memory" else "proposal"
        if len(parts) != 4:
            return None, None, f"Usage: {label} scope <{'M' if kind == 'memory' else 'P'}-### or numeric id> <scope|type-derived>"
        record_id = resolve_assistant_id(parts[2], kind, self.config.domain)
        if record_id is None:
            return None, None, f"{label.title()} not found."
        scope = None if parts[3].casefold() in {"type-derived", "default", "clear"} else parts[3]
        return record_id, scope, None

    def _set_memory_visibility_scope(self, text):
        memory_id, scope, error = self._parse_visibility_scope_command(text, kind="memory")
        if error:
            return error
        if get_assistant_memory(memory_id, domain=self.config.domain) is None:
            return "Memory not found."
        try:
            memory = update_assistant_memory(
                memory_id, domain=self.config.domain, visibility_scope=scope,
            )
        except (TypeError, ValueError) as error:
            return f"Assistant error: {error}"
        display = memory.get("visibility_scope") or "type-derived"
        return f"Set {assistant_public_id('memory', memory_id, self.config.domain)} visibility scope to: {display}."

    def _set_proposal_visibility_scope(self, text):
        proposal_id, scope, error = self._parse_visibility_scope_command(text, kind="proposal")
        if error:
            return error
        if get_assistant_memory_proposal(proposal_id, domain=self.config.domain) is None:
            return "Proposal not found."
        try:
            proposal = update_assistant_memory_proposal_visibility_scope(
                proposal_id, scope, domain=self.config.domain,
            )
        except (TypeError, ValueError) as error:
            return f"Assistant error: {error}"
        display = proposal.get("visibility_scope") or "type-derived"
        return f"Set {assistant_public_id('proposal', proposal_id, self.config.domain)} visibility scope to: {display}."

    def explain_memory(self, query=None):
        """Return a bounded, provenance-safe explanation payload."""
        retrieval_items = []
        if self._uses_default_memory_store:
            retrieval_items = (
                self.retriever.retrieve(query, domain=self.config.domain, limit=self.config.max_memories)
                if query is not None else [{"memory":{"id": memory_id}, "reasons": []} for memory_id in self.last_memory_ids]
            )
            if query is not None:
                retrieval_items, _ = self._apply_shared_memory_visibility(retrieval_items)
            target_ids = [item["memory"]["id"] for item in retrieval_items]
            source_memories = {memory_id: inspect_assistant_memory(memory_id, domain=self.config.domain) for memory_id in target_ids}
        else:
            custom = self.memory_loader(domain=self.config.domain, status="active", limit=self.config.max_memories)
            custom_items, _ = self._apply_shared_memory_visibility(
                [{"memory": memory, "reasons": ["custom memory loader"]} for memory in custom]
            )
            custom = [item["memory"] for item in custom_items]
            target_ids = self.last_memory_ids if query is None else [memory["id"] for memory in custom if any(token in (memory.get("summary","")+" "+memory.get("details","")).casefold() for token in query.casefold().split())]
            source_memories = {memory["id"]: {"memory": memory, "evidence": []} for memory in custom if memory["id"] in target_ids}
        if not target_ids: return {"status": "ambiguous" if query is None else "no_match", "memories": []}
        payload=[]
        for memory_id in target_ids[:self.config.max_memories]:
            inspected = source_memories.get(memory_id)
            if inspected:
                memory=inspected["memory"]
                payload.append({"memory_id":memory["id"],"summary":memory["summary"],"details":memory.get("details"),"confidence":memory.get("confidence"),"importance":memory.get("importance"),"source":memory.get("source"),"approved_memory_id":memory.get("id"),"evidence":inspected.get("evidence",[]),"retrieval_reasons":next((item.get("reasons",[]) for item in retrieval_items if item["memory"].get("id")==memory["id"]),[])})
        return {"status":"ok" if payload else "no_match","memories":payload}

    def _memory_introspection(self, user_text):
        lowered=user_text.casefold()
        why=any(phrase in lowered for phrase in ("why do you remember", "where did that memory come from", "what made you think that"))
        direct=lowered.startswith("what do you remember about")
        if not (why or direct): return None
        query=None if why else user_text.split("about",1)[1].strip().rstrip("?")
        self._turn_started_at = time.perf_counter()
        retrieval_started = time.perf_counter()
        explanation=self.explain_memory(query)
        phase_timings = {"retrieval_ms": round((time.perf_counter() - retrieval_started) * 1000, 2), "association_ms": 0.0}
        if explanation["status"] == "ambiguous": return "I am not sure which memory you mean. Which one should I explain?"
        if explanation["status"] == "no_match": return "I do not have an active canonical memory that matches that."
        explanation_json = json.dumps(explanation, ensure_ascii=False)
        retrieved = [
            {
                "memory": {"id": item["memory_id"]},
                "score": None,
                "reasons": item.get("retrieval_reasons", []),
            }
            for item in explanation["memories"]
        ]
        plan = self.context_manager.build_introspection(
            persona_text=self.persona.render_prompt(),
            policy_text=self.policy,
            explanation_json=explanation_json,
            user_text=user_text,
            selected_memory_ids=[item["memory_id"] for item in explanation["memories"]],
        )
        prompt = plan.model_messages()
        phase_timings["prompt_build_ms"] = round((time.perf_counter() - retrieval_started) * 1000, 2) - phase_timings["retrieval_ms"]
        self._begin_turn_diagnostics(plan, retrieved, phase_timings)
        self.trace.record("memory_explanation", query=query, memory_ids=[item["memory_id"] for item in explanation["memories"]], payload=explanation)
        self._generation_started_at = time.perf_counter()
        self._first_token_seconds = None
        try:
            content=self._chat_complete(prompt).strip()
        except GenerationInterrupted:
            self._finish_turn_diagnostics(completed=False, response="", latency_seconds=time.perf_counter() - self._generation_started_at, proposal={"ran": False, "outcome": "interrupted"})
            raise
        latency_seconds = time.perf_counter() - self._generation_started_at
        if not content:
            self._finish_turn_diagnostics(completed=False, response="", latency_seconds=latency_seconds, proposal={"ran": False, "outcome": "skipped"}, status="failed")
            raise RuntimeError("Assistant model returned empty content.")
        self._finish_turn_diagnostics(completed=True, response=content, latency_seconds=latency_seconds, proposal={"ran": False, "outcome": "skipped"})
        return content

    def respond(self, user_text, *, external_document_context=None):
        user_text = user_text.strip()
        if not user_text:
            return ""
        if self._pending_bulk_proposal_ids is not None:
            if user_text == "approve all":
                return self._approve_all_pending()
            self._pending_bulk_proposal_ids = None
            return "Bulk approval cancelled."
        if user_text.casefold() == "context stats":
            return self.context_stats()
        if detect_casual_roleplay_start(user_text):
            result = self.roleplay_begin()
            self.trace.record("roleplay_start", source="casual_explicit_phrase")
            return result
        command_result = self.command(user_text)
        if command_result is not None:
            self.trace.record("command", command=user_text)
            return command_result
        direct_help = detect_command_help(user_text)
        if direct_help is not None:
            self.trace.record("command_help", intent=direct_help.intent, command=user_text)
            return direct_help.render()
        introspection = self._memory_introspection(user_text)
        if introspection is not None:
            return introspection
        previous_memory_ids = list(self.last_memory_ids)
        self._turn_started_at = time.perf_counter()
        plan = self._context_plan(user_text, external_document_context=external_document_context)
        messages = plan.model_messages()
        self.trace.record("model_request", model=self.active_model, message_count=len(messages), messages=messages)
        self._generation_started_at = time.perf_counter()
        self._first_token_seconds = None
        try:
            content = self._chat_complete(messages).strip()
        except GenerationInterrupted:
            self.last_memory_ids = previous_memory_ids
            self._finish_turn_diagnostics(
                completed=False,
                response="",
                latency_seconds=time.perf_counter() - self._generation_started_at,
                proposal={"ran": False, "outcome": "interrupted"},
            )
            raise
        latency_seconds = time.perf_counter() - self._generation_started_at
        if not content:
            self._finish_turn_diagnostics(
                completed=False,
                response="",
                latency_seconds=latency_seconds,
                proposal={"ran": False, "outcome": "skipped"},
                status="failed",
            )
            self.trace.record("model_response", model=self.active_model, status="empty")
            raise RuntimeError("Assistant model returned empty content.")
        self.trace.record("model_response", model=self.active_model, status="ok", response=content)
        self.messages.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": content}])
        self.messages = self.messages[-self.config.max_session_messages:]
        proposal_started = time.perf_counter()
        try:
            self._proposal(user_text, content)
        except Exception as error:
            self._current_proposal_diagnostics = {"ran": True, "outcome": "skipped"}
            self.trace.record("proposal_error", status="rejected", error=str(error))
        if self._current_context_diagnostics is not None:
            self._current_context_diagnostics.setdefault("phase_timings", {})["proposal_ms"] = round((time.perf_counter() - proposal_started) * 1000, 2)
        self._finish_turn_diagnostics(
            completed=True,
            response=content,
            latency_seconds=latency_seconds,
            proposal=self._current_proposal_diagnostics,
        )
        return content

def format_assistant_memory(inspected):
    memory = inspected["memory"]; evidence = inspected.get("evidence", [])
    lines=[f"Memory {assistant_public_id('memory', memory['id'], memory.get('domain', 'personal'))}",f"Domain: {memory.get('domain','unknown')}",f"Type: {memory.get('memory_type','unknown')}",f"Subject: {memory.get('subject','unknown')}","","Summary:",memory.get('summary') or '(none)',"","Details:",memory.get('details') or '(none)',"",f"Confidence: {memory.get('confidence','unknown')}",f"Importance: {memory.get('importance','unknown')}",f"Retention: {memory.get('retention','unknown')}",f"Visibility scope: {memory.get('visibility_scope') or 'type-derived (legacy fallback)'}",f"Status: {memory.get('status','unknown')}","","Evidence:"]
    if not evidence: lines.append("no recorded evidence provenance")
    for i,item in enumerate(evidence,1): lines.extend([f'{i}. "{item.get("raw_excerpt") or "(observation text unavailable)"}"',f"   Source: {item.get('source','unknown')}",f"   Added: {item.get('observed_at','unknown')}",f"   Observation key: {item.get('evidence_hash') or 'legacy/unavailable'}",f"   Proposal: {assistant_public_id('proposal', item.get('proposal_id'), memory.get('domain', 'personal')) if item.get('proposal_id') else 'unknown'}"])
    lines.extend(["",f"Created: {memory.get('created_at','unknown')}",f"Updated: {memory.get('updated_at','unknown')}"])
    return "\n".join(lines)

def format_assistant_memory_proposal(inspected):
    proposal = inspected["proposal"]
    evidence = inspected.get("evidence", [])
    identity = proposal.get("proposal_key") or "legacy/unavailable"
    support = proposal.get("evidence_count") if proposal.get("evidence_count") is not None else "legacy/unavailable"
    lines = [f"Proposal {assistant_public_id('proposal', proposal['id'], proposal.get('domain', 'personal'))}", f"Status: {proposal.get('status', 'unknown')}", f"Domain: {proposal.get('domain', 'unknown')}", f"Type: {proposal.get('memory_type', 'unknown')}", f"Subject: {proposal.get('subject', 'unknown')}", "", "Summary:", proposal.get("summary") or "(none)", "", "Details:", proposal.get("details") or "(none)", "", f"Confidence: {proposal.get('confidence', 'unknown')}", f"Importance: {proposal.get('importance', 'unknown')}", f"Retention: {proposal.get('retention', 'unknown')}", f"Visibility scope: {proposal.get('visibility_scope') or 'type-derived on approval'}", f"Support: {support}", "", f"Identity: {identity}", "", "Evidence:"]
    if not evidence:
        lines.append("no recorded evidence provenance")
    else:
        for index, item in enumerate(evidence, 1):
            observation = item.get("raw_excerpt") or item.get("source_reference") or "(observation text unavailable)"
            lines.extend([f'{index}. "{observation}"', f"   Source: {item.get('source', 'unknown')}", f"   Added: {item.get('observed_at', 'unknown')}", f"   Observation key: {item.get('evidence_hash') or 'legacy/unavailable'}"])
    lines.extend(["", f"Created: {proposal.get('created_at', 'unknown')}", f"Updated: {proposal.get('updated_at', 'unknown')}"])
    return "\n".join(lines)

def run_interactive(config_path=DEFAULT_CONFIG_PATH, input_fn=input, output_fn=print, debug_level=None):
    config = load_config(config_path)
    stream_started = {"value": False}
    def stream_writer(text):
        if not stream_started["value"]:
            print("StarFur: ", end="", flush=True); stream_started["value"] = True
        print(text, end="", flush=True)
    # Import locally to avoid a module cycle: the application factory constructs
    # AssistantSession while this module owns the interactive presentation loop.
    from pipeline.application import create_assistant_application
    application = create_assistant_application(
        config_path,
        debug_level=debug_level,
        stream=True,
        stream_writer=stream_writer,
    )
    session = application.session
    output_fn("StarFur Assistant (model list/current/use, persona list/current/use/inspect, roleplay begin/end/status, adventure list/create/inspect/load/status/unload, remember/forget, memory list/search/inspect/scope, proposal list/inspect/approve/reject/approve all/scope, context stats; quit to exit)")
    while True:
        try:
            user_text = input_fn("You: ")
        except (EOFError, KeyboardInterrupt):
            output_fn("\nGoodbye.")
            return
        if user_text.strip().casefold() in {"quit", "exit"}:
            output_fn("Goodbye.")
            return
        proposal_count_before = len(session.proposals)
        try:
            answer = application.respond(user_text)
        except GenerationInterrupted:
            if stream_started["value"]:
                output_fn("")
            output_fn("Generation interrupted.")
            stream_started["value"] = False
            continue
        except Exception as error:
            output_fn(f"Assistant error: {error}")
            session.trace.emit(output_fn)
            continue
        if answer:
            if stream_started["value"]:
                output_fn("")
            else:
                output_fn(f"StarFur: {answer}")
        stream_started["value"] = False
        session.trace.emit(output_fn)
        if len(session.proposals) > proposal_count_before:
            proposal = session.proposals[-1]
            if proposal.get("store"):
                output_fn("Memory proposal available for review: " + proposal["summary"])
