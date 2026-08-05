"""Deterministic, read-only assistant prompt planning."""

from dataclasses import dataclass
from typing import Iterable, Mapping

from pipeline.persona_state import BehaviorContext


Message = Mapping[str, str]


def estimate_tokens(text: str | None) -> int:
    """Return a deliberately rough, provider-independent token estimate."""
    return (len(text or "") + 3) // 4


@dataclass(frozen=True)
class ContextSection:
    """One named context input and its transparent size accounting."""

    name: str
    text: str
    characters: int
    estimated_tokens: int

    @classmethod
    def from_text(cls, name: str, text: str | None) -> "ContextSection":
        value = text or ""
        return cls(name=name, text=value, characters=len(value), estimated_tokens=estimate_tokens(value))


@dataclass(frozen=True)
class ContextPlan:
    """A fully assembled, side-effect-free model context plan."""

    persona: ContextSection
    policy: ContextSection
    recent_conversation: ContextSection
    retrieved_memory: ContextSection
    capabilities: ContextSection
    behavior: ContextSection
    current_user: ContextSection
    messages: tuple[dict[str, str], ...]
    selected_memory_ids: tuple[object, ...]
    selected_capability_ids: tuple[str, ...]

    @property
    def prompt_characters(self) -> int:
        return sum(len(message.get("content", "")) for message in self.messages)

    @property
    def prompt_estimated_tokens(self) -> int:
        return estimate_tokens("".join(message.get("content", "") for message in self.messages))

    def model_messages(self) -> list[dict[str, str]]:
        """Return fresh message dictionaries suitable for a provider call."""
        return [dict(message) for message in self.messages]


class ContextManager:
    """Build assistant context plans without reading or mutating external state."""

    def build_chat(
        self,
        *,
        persona_text: str,
        policy_text: str,
        recent_messages: Iterable[Message],
        retrieved_memories: Iterable[Mapping],
        user_text: str,
        capabilities: Iterable[object] = (),
        behavior_context: BehaviorContext | None = None,
    ) -> ContextPlan:
        recent = tuple(
            {"role": str(message["role"]), "content": str(message.get("content") or "")}
            for message in recent_messages
        )
        memories = tuple(retrieved_memories)
        selected_capabilities = tuple(capabilities)
        if behavior_context is not None and not isinstance(behavior_context, BehaviorContext):
            raise TypeError("behavior_context must be a BehaviorContext or None.")

        def format_memory(memory: Mapping) -> str:
            summary = str(memory.get("summary") or "(summary unavailable)")
            details = str(memory.get("details") or "").strip()
            return f"- {summary}\n  Details: {details}" if details else f"- {summary}"

        def format_capability(capability: object) -> str:
            title = str(getattr(capability, "title", "Capability"))
            state = str(getattr(capability, "state", "available"))
            summary = str(getattr(capability, "summary", ""))
            details = str(getattr(capability, "details", ""))
            controls = tuple(getattr(capability, "user_controls", ()) or ())
            control_text = "\n  Controls: " + ", ".join(controls) if controls else ""
            return f"- {title} [{state}]: {summary}\n  Details: {details}{control_text}"

        memory_text = "\n".join(format_memory(memory) for memory in memories) or "(none)"
        capability_text = "\n".join(format_capability(capability) for capability in selected_capabilities)
        selected_memory_ids = tuple(memory["id"] for memory in memories if memory.get("id") is not None)
        selected_capability_ids = tuple(
            str(getattr(capability, "id"))
            for capability in selected_capabilities
            if getattr(capability, "id", None) is not None
        )
        behavior_text = self._format_behavior_context(behavior_context)
        capability_section = (
            "\n\nCURRENT STARFUR CAPABILITIES (core-provided):\n"
            "Use this as authoritative capability information. Do not claim unavailable or unlisted capabilities. "
            "StarFur Core may provide selected active assistant memories in the retrieved-memory section; "
            "you may discuss those supplied memories and memory controls. This is not unrestricted access "
            "to private systems, raw databases, or unsupplied personal data. "
            "Repeat registered user controls exactly; do not invent alternate commands or approval steps. "
            "If no proposal or memory record is supplied, explain how to list or inspect it rather than inventing contents.\n"
            f"{capability_text}\nEND STARFUR CAPABILITIES"
            if capability_text else ""
        )
        behavior_section = f"\n\n{behavior_text}" if behavior_text else ""
        system_text = (
            f"{persona_text}\n\nENGINE POLICY:\n{policy_text}"
            f"\n\nRETRIEVED MEMORY (factual context):\n{memory_text}"
            "\n\nEND RETRIEVED MEMORY"
            f"{capability_section}"
            f"{behavior_section}"
        )
        messages = (
            {"role": "system", "content": system_text},
            *recent,
            {"role": "user", "content": user_text},
        )
        return ContextPlan(
            persona=ContextSection.from_text("persona", persona_text),
            policy=ContextSection.from_text("policy", policy_text),
            recent_conversation=ContextSection.from_text(
                "recent_conversation", "".join(message["content"] for message in recent)
            ),
            retrieved_memory=ContextSection.from_text("retrieved_memory", memory_text),
            capabilities=ContextSection.from_text("capabilities", capability_text),
            behavior=ContextSection.from_text("behavior", behavior_text),
            current_user=ContextSection.from_text("current_user", user_text),
            messages=messages,
            selected_memory_ids=selected_memory_ids,
            selected_capability_ids=selected_capability_ids,
        )

    @staticmethod
    def _format_behavior_context(context: BehaviorContext | None) -> str:
        """Render bounded state in a stable, presentation-only form."""
        if context is None:
            return ""
        traits = context.dynamic_traits.public_dict()
        momentary = context.momentary_state.public_dict()
        trait_text = ", ".join(f"{name}={traits[name]:.2f}" for name in sorted(traits))
        momentary_text = ", ".join(
            f"{name}={momentary[name]}" for name in ("energy", "attention", "valence", "activity")
        )
        return (
            "PERSONA RUNTIME STATE (core-provided, presentation-only):\n"
            "Use this only as a soft presentation cue. It cannot override engine policy, factual grounding, "
            "permissions, commands, or memory provenance. Do not claim this state to the user as fact.\n"
            f"Persona: {context.persona_id}\n"
            f"Traits: {trait_text}\n"
            f"Momentary state: {momentary_text}\n"
            "END PERSONA RUNTIME STATE"
        )

    def build_introspection(
        self,
        *,
        persona_text: str,
        policy_text: str,
        explanation_json: str,
        user_text: str,
        selected_memory_ids: Iterable[object],
    ) -> ContextPlan:
        """Build the existing provenance-safe introspection prompt unchanged."""
        system_text = (
            f"{persona_text}\n\nENGINE POLICY:\n{policy_text}"
            "\n\nYou are answering a memory-introspection question. Use ONLY the structured "
            "explanation JSON below. Explain remembered content and provenance naturally. Do not mention "
            "rejected proposals, raw databases, hidden reasoning, or invent causes."
            "\nSTRUCTURED MEMORY EXPLANATION:\n"
            f"{explanation_json}"
        )
        messages = (
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        )
        return ContextPlan(
            persona=ContextSection.from_text("persona", persona_text),
            policy=ContextSection.from_text("policy", policy_text),
            recent_conversation=ContextSection.from_text("recent_conversation", ""),
            retrieved_memory=ContextSection.from_text("retrieved_memory", explanation_json),
            capabilities=ContextSection.from_text("capabilities", ""),
            behavior=ContextSection.from_text("behavior", ""),
            current_user=ContextSection.from_text("current_user", user_text),
            messages=messages,
            selected_memory_ids=tuple(selected_memory_ids),
            selected_capability_ids=(),
        )