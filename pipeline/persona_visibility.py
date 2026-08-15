"""Pure, explainable shared-memory visibility rules for persona runtimes.

This module deliberately does not load memory, change retrieval, or persist
anything. It gives later retrieval integration one deterministic policy
boundary without changing today's shared-memory behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real
import re


_PERSONA_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")

# These are deliberately derived only from the existing validated memory type.
# Explicit per-memory metadata may use the additional scopes below, but nothing
# infers them from memory prose.
MEMORY_TYPE_SCOPES = {
    "preference": "preference",
    "personal_fact": "personal",
    "experience": "personal",
    "project_context": "project",
    "relationship_context": "relationship",
    "ongoing_situation": "personal",
    "goal": "personal",
    "routine": "routine",
}
DERIVED_MEMORY_SCOPES = tuple(sorted(set(MEMORY_TYPE_SCOPES.values())))
# ``roleplay`` is available only as explicit user/Core-assigned metadata.  It
# is deliberately not mapped from any normal assistant-memory type.
EXPLICIT_MEMORY_SCOPES = tuple(sorted((*DERIVED_MEMORY_SCOPES, "roleplay")))
MEMORY_SCOPES = EXPLICIT_MEMORY_SCOPES


def _normalise_persona_id(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("persona_id must be a string")
    normalised = value.strip().casefold()
    if not _PERSONA_ID_RE.fullmatch(normalised):
        raise ValueError("persona_id must contain lowercase letters, digits, underscores, or hyphens")
    return normalised


def _confidence(value: Real, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{field_name} must be a number")
    normalised = float(value)
    if not isfinite(normalised) or not 0.0 <= normalised <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    return normalised


def _normalise_scopes(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        raise TypeError("allowed_memory_scopes must be a sequence of scope names or None")
    try:
        values = tuple(value)
    except TypeError as error:
        raise TypeError("allowed_memory_scopes must be a sequence of scope names or None") from error
    normalised = []
    for scope in values:
        if not isinstance(scope, str):
            raise TypeError("allowed_memory_scopes entries must be strings")
        name = scope.strip().casefold()
        if name not in MEMORY_SCOPES:
            raise ValueError(f"Unknown assistant-memory scope: {scope!r}")
        normalised.append(name)
    return tuple(sorted(set(normalised)))


def normalize_memory_visibility_scope(value: object) -> str | None:
    """Validate optional explicit scope metadata without inspecting prose."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("visibility_scope must be a scope name or None")
    scope = value.strip().casefold()
    if not scope:
        return None
    if scope not in EXPLICIT_MEMORY_SCOPES:
        raise ValueError(f"Unknown assistant-memory scope: {value!r}")
    return scope


@dataclass(frozen=True)
class SharedMemoryVisibilityPolicy:
    """Minimum confidence required before a persona may see shared memory.

    The default of ``0.0`` is intentionally backward compatible: when this
    policy is eventually wired into retrieval, existing personas will retain
    the same visibility unless a package explicitly chooses a threshold.
    """

    persona_id: str
    minimum_shared_memory_confidence: float = 0.0
    allowed_memory_scopes: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "persona_id", _normalise_persona_id(self.persona_id))
        object.__setattr__(
            self,
            "minimum_shared_memory_confidence",
            _confidence(
                self.minimum_shared_memory_confidence,
                field_name="minimum_shared_memory_confidence",
            ),
        )
        object.__setattr__(self, "allowed_memory_scopes", _normalise_scopes(self.allowed_memory_scopes))


@dataclass(frozen=True)
class KnowledgeVisibilityDecision:
    """Explainable result of evaluating one shared-memory confidence value."""

    persona_id: str
    source_confidence: float
    minimum_shared_memory_confidence: float
    visible: bool
    reason: str

    @property
    def knowledge_confidence(self) -> float | None:
        """The usable confidence, or ``None`` when this persona cannot know it."""
        return self.source_confidence if self.visible else None

    def public_dict(self) -> dict[str, object]:
        return {
            "persona_id": self.persona_id,
            "source_confidence": self.source_confidence,
            "minimum_shared_memory_confidence": self.minimum_shared_memory_confidence,
            "visible": self.visible,
            "knowledge_confidence": self.knowledge_confidence,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ScopeVisibilityDecision:
    """Explainable result of evaluating an existing memory type's derived scope."""

    persona_id: str
    memory_type: str | None
    memory_scope: str | None
    allowed_memory_scopes: tuple[str, ...] | None
    visible: bool
    reason: str

    def public_dict(self) -> dict[str, object]:
        return {
            "persona_id": self.persona_id,
            "memory_type": self.memory_type,
            "memory_scope": self.memory_scope,
            "allowed_memory_scopes": self.allowed_memory_scopes,
            "visible": self.visible,
            "reason": self.reason,
        }


def memory_scope_for_type(memory_type: object) -> str | None:
    """Return the conservative scope derived from a known assistant-memory type."""
    if not isinstance(memory_type, str):
        return None
    return MEMORY_TYPE_SCOPES.get(memory_type.strip().casefold())


def memory_scope_for_record(memory_type: object, visibility_scope: object = None) -> str | None:
    """Return explicit scope when present, otherwise the legacy type fallback."""
    explicit_scope = normalize_memory_visibility_scope(visibility_scope)
    return explicit_scope if explicit_scope is not None else memory_scope_for_type(memory_type)


def evaluate_shared_memory_visibility(
    policy: SharedMemoryVisibilityPolicy,
    memory_confidence: Real,
) -> KnowledgeVisibilityDecision:
    """Evaluate one memory confidence against a persona's policy.

    This is intentionally a pure function so a future retriever can apply it
    consistently and expose the same reason in diagnostics.
    """

    if not isinstance(policy, SharedMemoryVisibilityPolicy):
        raise TypeError("policy must be a SharedMemoryVisibilityPolicy")
    source_confidence = _confidence(memory_confidence, field_name="memory_confidence")
    threshold = policy.minimum_shared_memory_confidence
    visible = source_confidence >= threshold
    comparison = "meets" if visible else "is below"
    reason = f"source confidence {source_confidence:.3f} {comparison} persona threshold {threshold:.3f}"
    return KnowledgeVisibilityDecision(
        persona_id=policy.persona_id,
        source_confidence=source_confidence,
        minimum_shared_memory_confidence=threshold,
        visible=visible,
        reason=reason,
    )


def evaluate_shared_memory_scope_visibility(
    policy: SharedMemoryVisibilityPolicy,
    memory_type: object,
    visibility_scope: object = None,
) -> ScopeVisibilityDecision:
    """Evaluate access to an explicit scope or existing type-derived fallback.

    This does not inspect memory text, infer sensitive categories, or access a
    database. A configured allowlist fails closed for an unmapped type.
    """

    if not isinstance(policy, SharedMemoryVisibilityPolicy):
        raise TypeError("policy must be a SharedMemoryVisibilityPolicy")
    normalised_type = memory_type.strip().casefold() if isinstance(memory_type, str) else None
    scope = memory_scope_for_record(memory_type, visibility_scope)
    allowed_scopes = policy.allowed_memory_scopes
    if allowed_scopes is None:
        visible = True
        reason = "persona has unrestricted assistant-memory scopes"
    elif scope is None:
        visible = False
        reason = "memory type has no approved scope mapping for this persona"
    else:
        visible = scope in allowed_scopes
        reason = (
            f"memory scope {scope!r} is allowed for this persona"
            if visible else f"memory scope {scope!r} is not allowed for this persona"
        )
    return ScopeVisibilityDecision(
        persona_id=policy.persona_id,
        memory_type=normalised_type,
        memory_scope=scope,
        allowed_memory_scopes=allowed_scopes,
        visible=visible,
        reason=reason,
    )


__all__ = [
    "KnowledgeVisibilityDecision",
    "DERIVED_MEMORY_SCOPES",
    "EXPLICIT_MEMORY_SCOPES",
    "MEMORY_SCOPES",
    "MEMORY_TYPE_SCOPES",
    "ScopeVisibilityDecision",
    "SharedMemoryVisibilityPolicy",
    "evaluate_shared_memory_visibility",
    "evaluate_shared_memory_scope_visibility",
    "memory_scope_for_record",
    "memory_scope_for_type",
    "normalize_memory_visibility_scope",
]
