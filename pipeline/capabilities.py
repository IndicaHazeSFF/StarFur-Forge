"""Core-owned, presentation-neutral capability metadata.

The registry describes what StarFur may explain or expose.  It intentionally
does not execute a capability, inspect private state, or construct model
prompts.  Presentation layers will consume the immutable manifest in a later
step.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import re
from typing import Iterable, Mapping


CAPABILITY_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
CAPABILITY_STATES = frozenset({
    "available",
    "disabled",
    "unavailable",
    "experimental",
    "requires_confirmation",
})


@dataclass(frozen=True)
class Capability:
    """Public conceptual and runtime metadata for one stable capability ID."""

    id: str
    title: str
    category: str
    summary: str
    details: str
    user_controls: tuple[str, ...] = ()
    surfaces: tuple[str, ...] = ()
    activation_terms: tuple[str, ...] = ()
    state: str = "available"
    requires_confirmation: bool = False

    def __post_init__(self):
        if not CAPABILITY_ID_RE.fullmatch(self.id):
            raise ValueError(f"Invalid capability id: {self.id!r}")
        if not self.title.strip() or not self.category.strip():
            raise ValueError("Capability title and category must be non-empty.")
        if not self.summary.strip() or not self.details.strip():
            raise ValueError("Capability summary and details must be non-empty.")
        if self.state not in CAPABILITY_STATES:
            raise ValueError(f"Invalid capability state: {self.state!r}")
        if self.requires_confirmation and self.state == "available":
            object.__setattr__(self, "state", "requires_confirmation")
        if len(set(self.user_controls)) != len(self.user_controls):
            raise ValueError("Capability user controls must be unique.")
        if len(set(self.surfaces)) != len(self.surfaces):
            raise ValueError("Capability surfaces must be unique.")
        if len(set(self.activation_terms)) != len(self.activation_terms):
            raise ValueError("Capability activation terms must be unique.")

    def with_state(self, state: str) -> "Capability":
        """Return a runtime-state projection without mutating the registry."""
        return replace(self, state=state)

    def public_dict(self) -> dict:
        """Return JSON-safe metadata suitable for future clients and prompts."""
        return asdict(self)


@dataclass(frozen=True)
class CapabilityManifest:
    """An immutable, stable-order snapshot of registered capabilities."""

    schema_version: int
    capabilities: tuple[Capability, ...]

    def __post_init__(self):
        ids = tuple(capability.id for capability in self.capabilities)
        if ids != tuple(sorted(ids)):
            raise ValueError("Capability manifests must be ordered by stable capability id.")
        if len(set(ids)) != len(ids):
            raise ValueError("Capability manifests cannot contain duplicate ids.")

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(self.public_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get(self, capability_id: str) -> Capability | None:
        return next((item for item in self.capabilities if item.id == capability_id), None)

    def public_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "capabilities": [capability.public_dict() for capability in self.capabilities],
        }

    def select_for_query(self, user_text: str) -> tuple[Capability, ...]:
        """Return deterministic, public capability context for explicit help queries.

        This deliberately does not try to infer a capability from every ordinary
        question. Broad help asks for the full manifest; named capability terms
        select only their matching entries.
        """
        query = (user_text or "").casefold()
        broad_help = (
            "what can you do",
            "what are you capable of",
            "your capabilities",
            "available capabilities",
            "available features",
            "what features",
            "show commands",
            "list commands",
            "starfur help",
        )
        if any(phrase in query for phrase in broad_help):
            return self.capabilities
        return tuple(
            capability
            for capability in self.capabilities
            if any(term.casefold() in query for term in capability.activation_terms)
        )


class CapabilityRegistry:
    """Core registration point for public StarFur capabilities."""

    def __init__(self, capabilities: Iterable[Capability] = ()):
        self._capabilities: dict[str, Capability] = {}
        for capability in capabilities:
            self.register(capability)

    def register(self, capability: Capability) -> None:
        if not isinstance(capability, Capability):
            raise TypeError("CapabilityRegistry accepts Capability objects only.")
        if capability.id in self._capabilities:
            raise ValueError(f"Capability already registered: {capability.id}")
        self._capabilities[capability.id] = capability

    def build_manifest(self, *, states: Mapping[str, str] | None = None) -> CapabilityManifest:
        """Project optional runtime states without altering registered definitions."""
        states = states or {}
        unknown = set(states) - set(self._capabilities)
        if unknown:
            raise ValueError(f"Unknown capability state override(s): {sorted(unknown)}")
        capabilities = tuple(
            self._capabilities[capability_id].with_state(states[capability_id])
            if capability_id in states
            else self._capabilities[capability_id]
            for capability_id in sorted(self._capabilities)
        )
        return CapabilityManifest(schema_version=1, capabilities=capabilities)


def build_core_capability_registry() -> CapabilityRegistry:
    """Return the current core capability definitions without runtime probing."""
    return CapabilityRegistry((
        Capability(
            id="assistant.chat",
            title="Conversational assistant",
            category="assistant",
            summary="StarFur can hold a local conversation through the selected chat model.",
            details="Conversation uses engine policy, the active persona, bounded recent context, and selected memory context.",
            surfaces=("cli", "openai_api"),
            activation_terms=("chat model", "conversation"),
        ),
        Capability(
            id="assistant.context_diagnostics",
            title="Context diagnostics",
            category="diagnostics",
            summary="StarFur can show read-only statistics for the most recent completed turn.",
            details="Diagnostics report bounded context accounting, selected memory IDs, retrieval reasons, generation timing, and proposal outcome without calling a model or changing stored data.",
            user_controls=("context stats",),
            surfaces=("cli", "openai_api"),
            activation_terms=("context stats", "context diagnostic", "context diagnostics", "debug context", "show context diagnostics"),
        ),
        Capability(
            id="assistant.memory.explicit",
            title="Explicit personal memory controls",
            category="memory",
            summary="Users can explicitly create, inspect, search, correct, and softly forget personal memories.",
            details="Assistant memories are domain-scoped structured records. Forgetting changes status instead of silently deleting historical provenance.",
            user_controls=("remember this:", "forget this:", "memory list", "memory search", "memory inspect"),
            surfaces=("cli", "openai_api"),
            activation_terms=("remember this", "forget this", "memory list", "memory search", "memory inspect", "personal memory"),
        ),
        Capability(
            id="assistant.memory.introspection",
            title="Memory introspection",
            category="memory",
            summary="StarFur can explain active recalled memories and approved provenance through a controlled interface.",
            details="It can answer questions about remembered information and its approved evidence, but does not expose rejected proposals, raw database access, hidden reasoning, or unrestricted conversation history.",
            surfaces=("cli", "openai_api"),
        ),
        Capability(
            id="assistant.memory.proposals",
            title="Memory proposals and review",
            category="memory",
            summary="StarFur can suggest user-observation memories for explicit human review.",
            details="Proposals are not automatically approved. Review preserves evidence and provenance; approved proposals become active assistant memories.",
            user_controls=("proposal list", "proposal inspect <id>", "proposal approve <id>", "proposal reject <id>", "proposal approve all"),
            surfaces=("cli", "openai_api"),
            requires_confirmation=True,
            activation_terms=("memory proposal", "memory proposals", "proposal list", "proposal approve", "proposal reject", "review new memories", "review your new memories", "review my new memories", "review memories", "pending memories", "how do i approve", "how can i approve", "approve new memories", "approve memories", "look at proposals", "show proposals", "where are proposals", "see proposals", "view proposals", "how do i review", "how can i review"),
        ),
        Capability(
            id="assistant.model_selection",
            title="Runtime model selection",
            category="provider",
            summary="The active local chat model can be viewed and changed for the current assistant session.",
            details="Model selection uses the configured local Ollama installation and affects later chat and proposal-extraction calls without rewriting persistent configuration or memory.",
            user_controls=("model list", "model current", "model use <model-name>"),
            surfaces=("cli", "openai_api"),
            activation_terms=("model list", "list models", "model current", "model use", "switch model", "change model", "select a model"),
        ),
        Capability(
            id="assistant.persona_selection",
            title="Runtime persona selection",
            category="assistant",
            summary="Configured declarative personas can be listed and selected for the current assistant session.",
            details="Selecting a persona changes only later presentation/runtime state in that session and clears its recent conversation context. Shared Core memory, providers, tools, permissions, and other conversations remain unchanged.",
            user_controls=("persona list", "persona current", "persona use <persona-id>", "persona inspect"),
            surfaces=("cli", "openai_api"),
            activation_terms=("persona list", "list personas", "persona current", "persona use", "switch persona", "change persona", "select a persona"),
        ),
        Capability(
            id="assistant.roleplay_session",
            title="Session roleplay mode",
            category="assistant",
            summary="Users can explicitly enter or leave a bounded fictional roleplay mode for the current conversation session.",
            details="This initial mode is session-ephemeral: it clears recent chat context on transitions and may tag eligible user-memory proposals as roleplay-scoped. It does not create an adventure workspace, replay history, or persistent story state.",
            user_controls=("roleplay begin [optional title]", "roleplay status", "roleplay end"),
            surfaces=("cli", "openai_api"),
            activation_terms=("roleplay", "roleplay mode", "start an adventure", "go on an adventure", "roleplay begin", "roleplay end"),
        ),
        Capability(
            id="assistant.adventure_registry",
            title="Adventure workspace registry",
            category="assistant",
            summary="StarFur can create and inspect isolated metadata-only workspaces for future persistent adventures.",
            details="A workspace has exact title resolution and a local manifest. It may be mounted as metadata in one conversation, but does not yet create an event log, retain replay state, or mix story content with personal memory.",
            user_controls=("adventure list", "adventure create <title>", "adventure inspect <title>", "adventure load <title>", "adventure status", "adventure unload"),
            surfaces=("cli", "openai_api"),
            activation_terms=("adventure workspace", "create an adventure", "list adventures", "inspect adventure", "load adventure", "resume adventure", "adventure create", "adventure load"),
            state="experimental",
        ),
        Capability(
            id="provider.ollama",
            title="Ollama chat provider",
            category="provider",
            summary="StarFur currently uses a local Ollama chat-provider adapter for normal conversation and model listing.",
            details="Provider-specific calls stay behind the ChatProvider boundary so future local or remote providers can be added without changing assistant orchestration.",
            surfaces=("cli", "openai_api"),
            activation_terms=("ollama", "provider", "providers", "openwebui"),
        ),
    ))


__all__ = [
    "CAPABILITY_ID_RE",
    "CAPABILITY_STATES",
    "Capability",
    "CapabilityManifest",
    "CapabilityRegistry",
    "build_core_capability_registry",
]
