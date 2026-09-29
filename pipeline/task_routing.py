"""Pure task/provider route planning with no provider execution authority.

The planner consumes declarative task profiles plus caller-supplied provider
status records.  It neither probes nor invokes a provider and does not know
about assistant memory, prompts, adventures, or session state.  Core may later
use its bounded decision to select an already-owned provider adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Mapping

from pipeline.task_profiles import (
    TASK_ADVENTURE_TURN_GENERATION,
    TASK_ADVENTURE_TURN_MUTATION_GENERATION,
    TASK_ADVENTURE_TURN_RESOURCE_GENERATION,
    TASK_ADVENTURE_PARTICIPANT_ACTION_GENERATION,
    TASK_ASSISTANT_CHAT,
    TASK_ASSISTANT_PROPOSAL,
    TASK_CODING,
    TASK_DOCUMENT_ANNOTATION,
    TASK_DOCUMENT_ANNOTATION_FALLBACK,
    TASK_RESEARCH_CLAIM_GENERATION,
    TASK_RESEARCH_RELATIONSHIP_GENERATION,
    TASK_IMAGE_GENERATION,
    TASK_VISION,
    ResolvedTaskProfile,
    TaskProfiles,
    normalize_task_id,
)


_PROVIDER_ID_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_PROVIDER_STATUSES = frozenset({
    "configured", "unprobed", "available", "unavailable", "unsupported",
    "failed", "degraded",
})
_ROUTABLE_STATUSES = frozenset({"configured", "unprobed", "available", "degraded"})
_TASK_CAPABILITIES = {
    TASK_ASSISTANT_CHAT: "chat",
    TASK_ASSISTANT_PROPOSAL: "chat",
    TASK_ADVENTURE_TURN_GENERATION: "chat",
    TASK_ADVENTURE_TURN_MUTATION_GENERATION: "chat",
    TASK_ADVENTURE_TURN_RESOURCE_GENERATION: "chat",
    TASK_ADVENTURE_PARTICIPANT_ACTION_GENERATION: "chat",
    TASK_DOCUMENT_ANNOTATION: "chat",
    TASK_DOCUMENT_ANNOTATION_FALLBACK: "chat",
    TASK_RESEARCH_CLAIM_GENERATION: "chat",
    TASK_RESEARCH_RELATIONSHIP_GENERATION: "chat",
    TASK_CODING: "chat",
    TASK_VISION: "vision",
    TASK_IMAGE_GENERATION: "image_generation",
}


class TaskRoutePlanningError(ValueError):
    """Raised when Core cannot form one finite, declarative route plan."""


def normalize_provider_id(value: object) -> str:
    if not isinstance(value, str):
        raise TaskRoutePlanningError("provider identifier is invalid")
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().casefold()).strip("-")
    if not _PROVIDER_ID_RE.fullmatch(normalized):
        raise TaskRoutePlanningError("provider identifier is invalid")
    return normalized


def provider_route_status_from_runtime(
    provider_id: object, *, configured: bool, health_status: object,
    lifecycle_state: object = None, capabilities: frozenset[str] = frozenset({"chat"}),
) -> "ProviderRouteStatus":
    """Translate bounded runtime observation into descriptive route state.

    This helper does not probe a provider, alter lifecycle, or claim health
    from configuration alone. A lifecycle result describes the last request,
    not future eligibility: Core may retry a configured adapter unless an
    explicit health probe has reported it unavailable. An unsupported optional
    probe likewise leaves the adapter provisionally routable.
    """
    if not isinstance(configured, bool):
        raise TaskRoutePlanningError("provider configured state is invalid")
    if not configured:
        status = "unavailable"
    elif health_status == "healthy":
        status = "available"
    elif health_status == "unsupported":
        status = "unprobed"
    elif health_status == "unavailable":
        status = "unavailable"
    else:
        status = "unprobed"
    return ProviderRouteStatus(str(provider_id), status, capabilities)


def task_required_capability(task_id: object) -> str:
    """Return the one Core-owned capability a provider task requires.

    Unknown/custom task IDs are deliberately not guessed. They need an
    explicit capability-policy addition before any future provider can receive
    their input. Provider-free internal work is intentionally absent here.
    """
    normalized = normalize_task_id(task_id)
    try:
        return _TASK_CAPABILITIES[normalized]
    except KeyError as error:
            raise TaskRoutePlanningError("task has no provider-routing capability") from error


def _bounded_budget(value: object) -> int | None:
    """Expose only positive integer provider-budget options in read models."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return min(value, 1_000_000)
    return None


@dataclass(frozen=True)
class ProviderRouteStatus:
    """Bounded caller-supplied status for a provider known to Core.

    ``configured`` and ``unprobed`` are intentionally routable provisional
    states. A later executor owns any actual health probe and must convert a
    failed probe into an unavailable/failed result; this value object never
    performs that work.
    """

    provider_id: str
    status: str
    capabilities: frozenset[str] = field(default_factory=lambda: frozenset({"chat"}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", normalize_provider_id(self.provider_id))
        if self.status not in _PROVIDER_STATUSES:
            raise TaskRoutePlanningError("provider status is invalid")
        if not isinstance(self.capabilities, frozenset) or not self.capabilities:
            raise TaskRoutePlanningError("provider capabilities are invalid")
        if not all(isinstance(item, str) and _PROVIDER_ID_RE.fullmatch(item) for item in self.capabilities):
            raise TaskRoutePlanningError("provider capabilities are invalid")


@dataclass(frozen=True)
class ProviderRouteRegistry:
    """Immutable provider-status lookup, deliberately not a provider factory."""

    providers: Mapping[str, ProviderRouteStatus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized: dict[str, ProviderRouteStatus] = {}
        for key, status in dict(self.providers).items():
            provider_id = normalize_provider_id(key)
            if not isinstance(status, ProviderRouteStatus) or status.provider_id != provider_id:
                raise TaskRoutePlanningError("provider registry entry is invalid")
            normalized[provider_id] = status
        object.__setattr__(self, "providers", normalized)

    def get(self, provider_id: object) -> ProviderRouteStatus | None:
        return self.providers.get(normalize_provider_id(provider_id))


@dataclass(frozen=True)
class TaskRouteCandidate:
    """One finite fallback candidate with no live provider reference."""

    task_id: str
    profile: ResolvedTaskProfile
    provider_id: str
    provider_status: str | None
    eligible: bool
    reason: str


@dataclass(frozen=True)
class TaskRouteDecision:
    """Bounded deterministic route plan; callers separately execute it."""

    requested_task_id: str
    required_capability: str
    candidates: tuple[TaskRouteCandidate, ...]
    selected_index: int | None

    @property
    def selected(self) -> TaskRouteCandidate | None:
        return None if self.selected_index is None else self.candidates[self.selected_index]

    @property
    def status(self) -> str:
        return "routable" if self.selected is not None else "unavailable"

    def public_dict(self) -> dict[str, object]:
        """Presentation-safe route metadata with no providers, prompts, or state."""
        return {
            "task_id": self.requested_task_id,
            "required_capability": self.required_capability,
            "status": self.status,
            "selected_task_id": None if self.selected is None else self.selected.task_id,
            "selected_provider": None if self.selected is None else self.selected.provider_id,
            "fallback_used": self.selected_index not in (None, 0),
            "candidates": [
                {
                    "task_id": item.task_id,
                    "provider": item.provider_id,
                    "model": item.profile.model,
                    "provider_status": item.provider_status,
                    "eligible": item.eligible,
                    "reason": item.reason,
                    "context_size": _bounded_budget(item.profile.options.get("num_ctx")),
                    "max_output_tokens": _bounded_budget(item.profile.options.get("num_predict")),
                }
                for item in self.candidates
            ],
        }


class TaskRoutePlanner:
    """Plan an acyclic profile fallback sequence without executing anything."""

    def __init__(self, profiles: TaskProfiles, providers: ProviderRouteRegistry) -> None:
        if not isinstance(profiles, TaskProfiles):
            raise TypeError("task route profiles are invalid")
        if not isinstance(providers, ProviderRouteRegistry):
            raise TypeError("task route provider registry is invalid")
        self._profiles = profiles
        self._providers = providers

    def plan(
        self, task_id: object, *, default_model: str, default_provider_id: str,
        required_capability: str | None = None, base_options: Mapping[str, int | float] | None = None,
    ) -> TaskRouteDecision:
        requested_task_id = normalize_task_id(task_id)
        provider_fallback = normalize_provider_id(default_provider_id)
        if not isinstance(default_model, str) or not default_model.strip():
            raise TaskRoutePlanningError("default model is invalid")
        if required_capability is None:
            required_capability = task_required_capability(requested_task_id)
        if not isinstance(required_capability, str) or not _PROVIDER_ID_RE.fullmatch(required_capability):
            raise TaskRoutePlanningError("required provider capability is invalid")
        if base_options is not None and not isinstance(base_options, Mapping):
            raise TaskRoutePlanningError("base generation options are invalid")

        candidates: list[TaskRouteCandidate] = []
        visited: set[str] = set()
        current = requested_task_id
        while current is not None:
            if current in visited:
                raise TaskRoutePlanningError("task profile fallback loop is invalid")
            visited.add(current)
            profile = self._profiles.resolve(
                current, default_model=default_model.strip(), base_options=base_options,
            )
            provider_id = normalize_provider_id(profile.provider or provider_fallback)
            provider = self._providers.get(provider_id)
            if provider is None:
                eligible, status, reason = False, None, "provider_not_registered"
            elif required_capability not in provider.capabilities:
                eligible, status, reason = False, provider.status, "capability_unsupported"
            elif provider.status not in _ROUTABLE_STATUSES:
                eligible, status, reason = False, provider.status, "provider_unavailable"
            else:
                eligible, status, reason = True, provider.status, "routable"
            candidates.append(TaskRouteCandidate(
                task_id=current, profile=profile, provider_id=provider_id,
                provider_status=status, eligible=eligible, reason=reason,
            ))
            fallback = profile.fallback_task
            if fallback is not None and fallback not in self._profiles.profiles:
                raise TaskRoutePlanningError("task profile fallback target is not configured")
            current = fallback

        selected_index = next((index for index, item in enumerate(candidates) if item.eligible), None)
        return TaskRouteDecision(requested_task_id, required_capability, tuple(candidates), selected_index)


__all__ = [
    "ProviderRouteRegistry", "ProviderRouteStatus", "TaskRouteCandidate",
    "TaskRouteDecision", "TaskRoutePlanner", "TaskRoutePlanningError",
    "normalize_provider_id", "provider_route_status_from_runtime",
    "task_required_capability",
]
