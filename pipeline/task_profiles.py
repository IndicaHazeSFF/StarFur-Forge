"""Declarative task/model profiles; routing remains an explicit future layer."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from pipeline.provider_resource_policy import RESOURCE_PROFILE_IDS


TASK_ASSISTANT_CHAT = "assistant_chat"
TASK_ASSISTANT_PROPOSAL = "assistant_proposal"
TASK_ADVENTURE_TURN_GENERATION = "adventure_turn_generation"
TASK_ADVENTURE_TURN_MUTATION_GENERATION = "adventure_turn_mutation_generation"
TASK_ADVENTURE_TURN_RESOURCE_GENERATION = "adventure_turn_resource_generation"
TASK_ADVENTURE_PARTICIPANT_ACTION_GENERATION = "adventure_participant_action_generation"
TASK_DOCUMENT_ANNOTATION = "document_annotation"
TASK_DOCUMENT_ANNOTATION_FALLBACK = "document_annotation_fallback"
TASK_RESEARCH_CLAIM_GENERATION = "research_claim_generation"
TASK_RESEARCH_RELATIONSHIP_GENERATION = "research_relationship_generation"
TASK_RETRIEVAL_EVALUATION = "retrieval_evaluation"
TASK_CODING = "coding"
TASK_VISION = "vision"
TASK_IMAGE_GENERATION = "image_generation"

KNOWN_TASKS = (
    TASK_ASSISTANT_CHAT,
    TASK_ASSISTANT_PROPOSAL,
    TASK_ADVENTURE_TURN_GENERATION,
    TASK_ADVENTURE_TURN_MUTATION_GENERATION,
    TASK_ADVENTURE_TURN_RESOURCE_GENERATION,
    TASK_ADVENTURE_PARTICIPANT_ACTION_GENERATION,
    TASK_DOCUMENT_ANNOTATION,
    TASK_DOCUMENT_ANNOTATION_FALLBACK,
    TASK_RESEARCH_CLAIM_GENERATION,
    TASK_RESEARCH_RELATIONSHIP_GENERATION,
    TASK_RETRIEVAL_EVALUATION,
    TASK_CODING,
    TASK_VISION,
    TASK_IMAGE_GENERATION,
)

_TASK_ID_RE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_OPTION_VALIDATORS = {
    "temperature": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0,
    "top_k": lambda value: isinstance(value, int) and not isinstance(value, bool) and value >= 0,
    "top_p": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1,
    "seed": lambda value: isinstance(value, int) and not isinstance(value, bool) and value >= -1,
}


def normalize_task_id(value: Any) -> str:
    if not isinstance(value, str) or not _TASK_ID_RE.fullmatch(value):
        raise ValueError("Task profile IDs must use lowercase letters, numbers, and underscores.")
    return value


def validate_generation_options(value: Any) -> dict[str, int | float]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Task profile options must be a JSON object.")
    unknown = set(value) - set(_OPTION_VALIDATORS)
    if unknown:
        raise ValueError(f"Unknown task profile generation option(s): {sorted(unknown)}")
    result = dict(value)
    for name, option_value in result.items():
        if not _OPTION_VALIDATORS[name](option_value):
            raise ValueError(f"Invalid task profile generation option {name!r}: {option_value!r}")
    return result


@dataclass(frozen=True)
class TaskProfile:
    """Configuration for one workload, not a provider-selection instruction."""

    task_id: str
    provider: str | None = None
    model: str | None = None
    generation_options: Mapping[str, int | float] = field(default_factory=dict)
    context_size: int | None = None
    max_output_tokens: int | None = None
    fallback_task: str | None = None
    resource_profile: str | None = None
    max_concurrent_requests: int | None = None
    model_keep_alive_seconds: int | None = None
    model_thinking: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", normalize_task_id(self.task_id))
        for field_name in ("provider", "model"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"Task profile {field_name} must be non-empty text when supplied.")
            if isinstance(value, str):
                object.__setattr__(self, field_name, value.strip())
        if self.context_size is not None and (isinstance(self.context_size, bool) or not isinstance(self.context_size, int) or self.context_size <= 0):
            raise ValueError("Task profile context_size must be a positive integer.")
        if self.max_output_tokens is not None and (isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int) or self.max_output_tokens <= 0):
            raise ValueError("Task profile max_output_tokens must be a positive integer.")
        if self.fallback_task is not None:
            object.__setattr__(self, "fallback_task", normalize_task_id(self.fallback_task))
            if self.fallback_task == self.task_id:
                raise ValueError("Task profile cannot fall back to itself.")
        if self.resource_profile is not None and self.resource_profile not in RESOURCE_PROFILE_IDS:
            raise ValueError("Task profile resource_profile is invalid.")
        if self.max_concurrent_requests is not None:
            if (
                isinstance(self.max_concurrent_requests, bool)
                or not isinstance(self.max_concurrent_requests, int)
                or not 1 <= self.max_concurrent_requests <= 64
            ):
                raise ValueError("Task profile max_concurrent_requests must be an integer from 1 through 64.")
        if self.model_keep_alive_seconds is not None:
            if (
                isinstance(self.model_keep_alive_seconds, bool)
                or not isinstance(self.model_keep_alive_seconds, int)
                or not 0 <= self.model_keep_alive_seconds <= 86_400
            ):
                raise ValueError("Task profile model_keep_alive_seconds must be an integer from 0 through 86400.")
        if self.model_thinking is not None and not isinstance(self.model_thinking, bool):
            raise ValueError("Task profile model_thinking must be a boolean when supplied.")
        object.__setattr__(self, "generation_options", validate_generation_options(self.generation_options))

    def resolved(self, *, default_model: str, base_options: Mapping[str, int | float] | None = None) -> "ResolvedTaskProfile":
        options = dict(base_options or {})
        options.update(self.generation_options)
        if self.context_size is not None:
            options["num_ctx"] = self.context_size
        if self.max_output_tokens is not None:
            options["num_predict"] = self.max_output_tokens
        return ResolvedTaskProfile(
            task_id=self.task_id,
            provider=self.provider,
            model=self.model or default_model,
            options=options,
            fallback_task=self.fallback_task,
            resource_profile=self.resource_profile,
            max_concurrent_requests=self.max_concurrent_requests,
            model_keep_alive_seconds=self.model_keep_alive_seconds,
            model_thinking=self.model_thinking,
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "provider": self.provider,
            "model": self.model,
            "generation_options": dict(self.generation_options),
            "context_size": self.context_size,
            "max_output_tokens": self.max_output_tokens,
            "fallback_task": self.fallback_task,
            "resource_profile": self.resource_profile,
            "max_concurrent_requests": self.max_concurrent_requests,
            "model_keep_alive_seconds": self.model_keep_alive_seconds,
            "model_thinking": self.model_thinking,
        }


@dataclass(frozen=True)
class ResolvedTaskProfile:
    task_id: str
    provider: str | None
    model: str
    options: Mapping[str, int | float]
    fallback_task: str | None = None
    resource_profile: str | None = None
    max_concurrent_requests: int | None = None
    model_keep_alive_seconds: int | None = None
    model_thinking: bool | None = None


@dataclass(frozen=True)
class TaskProfiles:
    """Immutable task profile collection loaded once with assistant configuration."""

    profiles: Mapping[str, TaskProfile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized: dict[str, TaskProfile] = {}
        for task_id, profile in dict(self.profiles).items():
            task_id = normalize_task_id(task_id)
            if not isinstance(profile, TaskProfile):
                raise TypeError("TaskProfiles values must be TaskProfile instances.")
            if task_id != profile.task_id:
                raise ValueError("Task profile mapping key must match profile.task_id.")
            normalized[task_id] = profile
        object.__setattr__(self, "profiles", normalized)

    def get(self, task_id: str) -> TaskProfile | None:
        return self.profiles.get(normalize_task_id(task_id))

    def resolve(self, task_id: str, *, default_model: str, base_options: Mapping[str, int | float] | None = None) -> ResolvedTaskProfile:
        task_id = normalize_task_id(task_id)
        profile = self.profiles.get(task_id)
        if profile is None:
            return ResolvedTaskProfile(
                task_id, None, default_model, dict(base_options or {}), None, None, None, None,
            )
        return profile.resolved(default_model=default_model, base_options=base_options)

    def public_dict(self) -> dict[str, dict[str, Any]]:
        return {task_id: profile.public_dict() for task_id, profile in sorted(self.profiles.items())}


def load_task_profiles(value: Any) -> TaskProfiles:
    """Parse optional JSON configuration while retaining an empty legacy default."""
    if value is None:
        return TaskProfiles()
    if not isinstance(value, Mapping):
        raise ValueError("task_profiles must be a JSON object.")
    profiles: dict[str, TaskProfile] = {}
    allowed = {"provider", "model", "generation_options", "context_size", "max_output_tokens", "fallback_task", "resource_profile", "max_concurrent_requests", "model_keep_alive_seconds", "model_thinking"}
    for raw_task_id, raw_profile in value.items():
        task_id = normalize_task_id(raw_task_id)
        if not isinstance(raw_profile, Mapping):
            raise ValueError(f"Task profile {task_id!r} must be a JSON object.")
        unknown = set(raw_profile) - allowed
        if unknown:
            raise ValueError(f"Unknown field(s) in task profile {task_id!r}: {sorted(unknown)}")
        profiles[task_id] = TaskProfile(task_id=task_id, **dict(raw_profile))
    return TaskProfiles(profiles)


def provider_matches(profile_provider: str | None, runtime_provider_name: str | None) -> bool:
    """Profiles may label a provider, but cannot silently select another one."""
    if profile_provider is None:
        return True
    return profile_provider.strip().casefold() == (runtime_provider_name or "").strip().casefold()


__all__ = [
    "KNOWN_TASKS", "TASK_ASSISTANT_CHAT", "TASK_ASSISTANT_PROPOSAL", "TASK_ADVENTURE_TURN_GENERATION", "TASK_ADVENTURE_TURN_MUTATION_GENERATION", "TASK_ADVENTURE_TURN_RESOURCE_GENERATION", "TASK_ADVENTURE_PARTICIPANT_ACTION_GENERATION", "TASK_DOCUMENT_ANNOTATION", "TASK_DOCUMENT_ANNOTATION_FALLBACK", "TASK_RESEARCH_CLAIM_GENERATION", "TASK_RESEARCH_RELATIONSHIP_GENERATION",
    "TASK_RETRIEVAL_EVALUATION", "TASK_CODING", "TASK_VISION", "TASK_IMAGE_GENERATION",
    "ResolvedTaskProfile", "TaskProfile", "TaskProfiles", "load_task_profiles", "provider_matches",
    "validate_generation_options",
]
