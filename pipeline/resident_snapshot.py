"""Presentation-neutral, read-only resident-runtime snapshot contract.

This module is deliberately independent of sessions, providers, databases, and
HTTP.  Application code supplies already-public, bounded inputs; this module
normalizes them into the small stable payload that a dashboard or apartment may
display.  It is not a command, configuration, or mutation surface.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


RESIDENT_SNAPSHOT_SCHEMA_VERSION = 1
_ACTIVITIES = frozenset({
    "idle", "generating", "streaming", "reviewing_candidates",
    "staging_adventure_turn", "roleplaying", "adventure_ready",
    "provider_error", "provider_unavailable",
})
_PROVIDER_BUSY_STATES = frozenset({"connecting", "loading", "generating", "streaming", "cooling", "unloading"})
_ROUTE_TRACE_OUTCOMES = frozenset({
    "submitted", "completed", "route_unavailable", "provider_adapter_unavailable",
    "provider_capability_unavailable", "provider_request_failed",
    "provider_stream_failed", "provider_stream_cancelled", "provider_concurrency_busy",
})


def _bounded_mapping(value: object, *, allowed: frozenset[str]) -> dict[str, Any]:
    """Copy a known public mapping without carrying arbitrary nested payloads."""
    if not isinstance(value, Mapping):
        return {}
    return {key: value[key] for key in allowed if key in value}


def _bounded_route_trace(value: object) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value[:8]:
        if not isinstance(item, Mapping):
            continue
        fields = {key: item.get(key) for key in (
            "requested_task_id", "selected_task_id", "provider", "model", "fallback_used", "outcome",
        )}
        if not all(isinstance(fields[key], str) and fields[key] for key in ("requested_task_id", "selected_task_id", "provider", "model")):
            continue
        if len(fields["model"]) > 256 or not isinstance(fields["fallback_used"], bool) or fields["outcome"] not in _ROUTE_TRACE_OUTCOMES:
            continue
        resource_profile = item.get("resource_profile")
        if isinstance(resource_profile, str) and resource_profile in {"interactive", "balanced", "background"}:
            fields["resource_profile"] = resource_profile
        result.append(fields)
    return result


def _resident_turn_public(value: object) -> dict[str, object]:
    """Render the turn read model without adding an empty compatibility field."""
    turn = _bounded_mapping(value, allowed=frozenset({"active", "staged_count"}))
    routes = _bounded_route_trace(value.get("last_task_routes") if isinstance(value, Mapping) else None)
    if routes:
        turn["last_task_routes"] = routes
    return turn


def _resident_routing_public(value: object) -> dict[str, object]:
    """Render aggregate route readiness without exposing route configuration."""
    if not isinstance(value, Mapping):
        return {"configured_task_count": 0, "routable_task_count": 0,
                "unavailable_task_count": 0, "storage": "session_ephemeral"}

    def count(name: str) -> int:
        candidate = value.get(name)
        return candidate if isinstance(candidate, int) and not isinstance(candidate, bool) and 0 <= candidate <= 64 else 0

    return {
        "configured_task_count": count("configured_task_count"),
        "routable_task_count": count("routable_task_count"),
        "unavailable_task_count": count("unavailable_task_count"),
        "storage": "session_ephemeral",
    }


def _resident_focus_mode_public(value: object) -> dict[str, object]:
    """Render only a session-local manual resource-cooperation indicator."""
    return {
        "enabled": isinstance(value, Mapping) and value.get("enabled") is True,
        "storage": "session_ephemeral",
    }


def _resident_sandbox_public(value: object) -> dict[str, object]:
    """Render only passive optional-execution status, never backend detail."""
    default = {
        "schema_version": 1,
        "configured": False,
        "host_status": "unprobed",
        "supervisor_status": "unprobed",
        "execution_status": "disabled",
        "reason": "not_configured",
        "storage": "presentation_ephemeral",
    }
    if not isinstance(value, Mapping):
        return default
    configured = value.get("configured")
    schema_version = value.get("schema_version")
    host = value.get("host_status")
    supervisor = value.get("supervisor_status")
    execution = value.get("execution_status")
    reason = value.get("reason")
    if (
        isinstance(schema_version, bool)
        or schema_version != 1
        or not isinstance(configured, bool)
        or host not in {"unprobed", "unsupported", "unavailable", "prerequisites_met"}
        or supervisor not in {"unprobed", "unavailable", "ready"}
        or execution not in {"disabled", "unavailable"}
        or reason not in {
            "not_configured", "host_unprobed", "host_unsupported", "host_unavailable",
            "supervisor_unprobed", "supervisor_unsupported", "supervisor_unavailable",
            "observation_missing", "observation_stale", "binding_mismatch",
            "enforcement_missing", "execution_not_enabled", "observation_failed",
        }
    ):
        return default
    return {
        "schema_version": 1,
        "configured": configured,
        "host_status": host,
        "supervisor_status": supervisor,
        "execution_status": execution,
        "reason": reason,
        "storage": "presentation_ephemeral",
    }


def _resident_tool_status_public(value: object) -> dict[str, object]:
    """Render aggregate broker counts without request or authority metadata."""
    default = {
        "schema_version": 1,
        "total_count": 0,
        "pending_review_count": 0,
        "approved_count": 0,
        "queued_count": 0,
        "running_count": 0,
        "terminal_count": 0,
        "storage": "session_ephemeral",
    }
    if not isinstance(value, Mapping) or value.get("schema_version") != 1:
        return default
    names = (
        "total_count", "pending_review_count", "approved_count", "queued_count",
        "running_count", "terminal_count",
    )
    counts = {name: value.get(name) for name in names}
    if any(
        isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 128
        for item in counts.values()
    ):
        return default
    if sum(counts[name] for name in names[1:]) != counts["total_count"]:
        return default
    return {"schema_version": 1, **counts, "storage": "session_ephemeral"}


def derive_resident_activity(
    *,
    provider_lifecycle: Mapping[str, object] | None = None,
    provider_configured: bool,
    adventure_turn_active: bool,
    ordinary_candidate_count: int,
    mutation_candidate_count: int,
    roleplay_active: bool,
    adventure_mounted: bool,
    explicit_resident_action: bool = False,
) -> str:
    """Return one deterministic current activity from summary-only state.

    The order deliberately favors an actual provider lifecycle state over
    presentation workflow labels.  Candidate review is next because it is an
    explicit user decision point; staged writes remain below it. An explicit
    non-idle ResidentAction is presentation state, so it keeps a zero-provider
    resident visually available without claiming that a provider is healthy.
    This is descriptive only and never drives a session transition.
    """
    lifecycle_state = ""
    if isinstance(provider_lifecycle, Mapping):
        raw = provider_lifecycle.get("state")
        lifecycle_state = raw if isinstance(raw, str) else ""
    if lifecycle_state == "error":
        return "provider_error"
    if lifecycle_state in _PROVIDER_BUSY_STATES:
        return "streaming" if lifecycle_state == "streaming" else "generating"
    if ordinary_candidate_count or mutation_candidate_count:
        return "reviewing_candidates"
    if adventure_turn_active:
        return "staging_adventure_turn"
    if roleplay_active:
        return "roleplaying"
    if adventure_mounted:
        return "adventure_ready"
    if not provider_configured and not explicit_resident_action:
        return "provider_unavailable"
    return "idle"


@dataclass(frozen=True)
class ResidentSnapshot:
    """Stable, summary-only public view of one selected resident session."""

    conversation_id: str
    persona: Mapping[str, object] | None
    provider: Mapping[str, object]
    lifecycle: Mapping[str, object] | None
    system_metrics: Mapping[str, object]
    capability_ids: tuple[str, ...]
    adventure: Mapping[str, object]
    roleplay: Mapping[str, object]
    turn: Mapping[str, object]
    candidates: Mapping[str, object]
    routing: Mapping[str, object] = field(default_factory=dict)
    focus_mode: Mapping[str, object] = field(default_factory=dict)
    sandbox_execution: Mapping[str, object] = field(default_factory=dict)
    tool_activity: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.conversation_id, str) or not self.conversation_id:
            raise ValueError("resident snapshot conversation identifier is invalid")
        if not isinstance(self.capability_ids, tuple) or not all(
            isinstance(item, str) and item for item in self.capability_ids
        ):
            raise TypeError("resident snapshot capability identifiers are invalid")

    @property
    def activity(self) -> str:
        provider_configured = self.provider.get("configured") is True
        resident_action = self.persona.get("resident_action") if isinstance(self.persona, Mapping) else None
        action_kind = resident_action.get("kind") if isinstance(resident_action, Mapping) else None
        return derive_resident_activity(
            provider_lifecycle=self.lifecycle,
            provider_configured=provider_configured,
            adventure_turn_active=self.turn.get("active") is True,
            ordinary_candidate_count=int(self.candidates.get("ordinary_count", 0)),
            mutation_candidate_count=int(self.candidates.get("mutation_count", 0)),
            roleplay_active=self.roleplay.get("active") is True,
            adventure_mounted=self.adventure.get("mounted") is True,
            explicit_resident_action=isinstance(action_kind, str) and action_kind != "idle",
        )

    def public_dict(self) -> dict[str, object]:
        """Return the versioned wire payload, with an intentional key allowlist."""
        persona = None
        if isinstance(self.persona, Mapping):
            persona = _bounded_mapping(self.persona, allowed=frozenset({
                "persona_id", "display_name", "dynamic_traits", "momentary_state",
                "development", "real_world_relationship_count", "resident_action", "storage",
            }))
        return {
            "object": "starfur.resident_snapshot",
            "schema_version": RESIDENT_SNAPSHOT_SCHEMA_VERSION,
            "conversation": {"id": self.conversation_id, "storage": "session_ephemeral"},
            "activity": self.activity,
            "persona": persona,
            "provider": _bounded_mapping(self.provider, allowed=frozenset({
                "name", "configured", "health", "model",
            })),
            "lifecycle": _bounded_mapping(self.lifecycle, allowed=frozenset({
                "provider", "model", "state", "previous_state", "transition_count",
            })) if isinstance(self.lifecycle, Mapping) else None,
            "system_metrics": {
                **_bounded_mapping(self.system_metrics, allowed=frozenset({"status", "platform", "reason"})),
                "cpu": _bounded_mapping(self.system_metrics.get("cpu"), allowed=frozenset({"logical_cores", "usage_percent"})),
                "memory": _bounded_mapping(self.system_metrics.get("memory"), allowed=frozenset({"total_bytes", "available_bytes"})),
                "storage": _bounded_mapping(self.system_metrics.get("storage"), allowed=frozenset({"total_bytes", "free_bytes"})),
                "gpu": _bounded_mapping(self.system_metrics.get("gpu"), allowed=frozenset({"status", "name", "vram_total_bytes", "vram_available_bytes"})),
            },
            "capabilities": {"ids": list(self.capability_ids)},
            "adventure": _bounded_mapping(self.adventure, allowed=frozenset({
                "mounted", "adventure_id", "title", "status", "event_count",
                "context_event_count", "state_fact_count", "context_state_fact_count",
                "relationship_fact_count", "context_relationship_fact_count",
                "knowledge_fact_count", "context_knowledge_fact_count",
                "resource_fact_count", "context_resource_fact_count", "participant_count", "storage",
            })),
            "roleplay": _bounded_mapping(self.roleplay, allowed=frozenset({
                "active", "title", "storage",
            })),
            "adventure_turn": _resident_turn_public(self.turn),
            "candidate_inbox": _bounded_mapping(self.candidates, allowed=frozenset({
                "ordinary_count", "mutation_count", "storage",
            })),
            "routing": _resident_routing_public(self.routing),
            "focus_mode": _resident_focus_mode_public(self.focus_mode),
            "sandbox_execution": _resident_sandbox_public(self.sandbox_execution),
            "tool_activity": _resident_tool_status_public(self.tool_activity),
        }


__all__ = [
    "RESIDENT_SNAPSHOT_SCHEMA_VERSION", "ResidentSnapshot", "derive_resident_activity",
]
