"""Pure, provider-free inference resource admission contracts.

This module describes limits that a later runtime may request and controls an
execution backend can truthfully claim to enforce.  It performs no monitoring,
provider call, process-priority change, model load/unload, routing, or wait.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


PROFILE_INTERACTIVE = "interactive"
PROFILE_BALANCED = "balanced"
PROFILE_BACKGROUND = "background"
RESOURCE_PROFILE_IDS = frozenset({
    PROFILE_INTERACTIVE,
    PROFILE_BALANCED,
    PROFILE_BACKGROUND,
})

CONTROL_WALL_TIME = "wall_time"
CONTROL_OUTPUT_TOKENS = "output_tokens"
CONTROL_CONCURRENCY = "concurrency"
CONTROL_CPU_THREADS = "cpu_threads"
CONTROL_RAM_BYTES = "ram_bytes"
CONTROL_VRAM_BYTES = "vram_bytes"
CONTROL_VERIFIED_CANCELLATION = "verified_cancellation"
CONTROL_MODEL_RESIDENCY = "model_residency"
RESOURCE_CONTROL_IDS = frozenset({
    CONTROL_WALL_TIME,
    CONTROL_OUTPUT_TOKENS,
    CONTROL_CONCURRENCY,
    CONTROL_CPU_THREADS,
    CONTROL_RAM_BYTES,
    CONTROL_VRAM_BYTES,
    CONTROL_VERIFIED_CANCELLATION,
    CONTROL_MODEL_RESIDENCY,
})

_BACKEND_ID_RE = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_REASON_RE = re.compile(r"[a-z][a-z0-9_:.-]{0,95}\Z")


def _bounded_positive_int(name: str, value: object, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} is outside its supported bounds")
    return value


def _normalize_controls(values: Iterable[str]) -> frozenset[str]:
    try:
        controls = frozenset(values)
    except TypeError as error:
        raise TypeError("resource controls must be an iterable of strings") from error
    if not all(isinstance(value, str) for value in controls):
        raise TypeError("resource control IDs must be strings")
    unknown = controls - RESOURCE_CONTROL_IDS
    if unknown:
        raise ValueError(f"unknown resource control(s): {sorted(unknown)}")
    return controls


@dataclass(frozen=True)
class InferenceResourceProfile:
    """One exact requested execution envelope, never backend authority."""

    profile_id: str
    max_wall_time_seconds: int
    max_output_tokens: int
    max_concurrent_requests: int = 1
    max_cpu_threads: int | None = None
    max_ram_bytes: int | None = None
    max_vram_bytes: int | None = None
    require_verified_cancellation: bool = True
    require_model_residency_control: bool = False

    def __post_init__(self) -> None:
        if self.profile_id not in RESOURCE_PROFILE_IDS:
            raise ValueError("inference resource profile ID is invalid")
        _bounded_positive_int("max_wall_time_seconds", self.max_wall_time_seconds, 3600)
        _bounded_positive_int("max_output_tokens", self.max_output_tokens, 131072)
        _bounded_positive_int("max_concurrent_requests", self.max_concurrent_requests, 64)
        for name, value, maximum in (
            ("max_cpu_threads", self.max_cpu_threads, 4096),
            ("max_ram_bytes", self.max_ram_bytes, 1 << 60),
            ("max_vram_bytes", self.max_vram_bytes, 1 << 60),
        ):
            if value is not None:
                _bounded_positive_int(name, value, maximum)
        if not isinstance(self.require_verified_cancellation, bool):
            raise TypeError("require_verified_cancellation must be boolean")
        if not isinstance(self.require_model_residency_control, bool):
            raise TypeError("require_model_residency_control must be boolean")

    @property
    def required_controls(self) -> frozenset[str]:
        controls = {
            CONTROL_WALL_TIME,
            CONTROL_OUTPUT_TOKENS,
            CONTROL_CONCURRENCY,
        }
        if self.max_cpu_threads is not None:
            controls.add(CONTROL_CPU_THREADS)
        if self.max_ram_bytes is not None:
            controls.add(CONTROL_RAM_BYTES)
        if self.max_vram_bytes is not None:
            controls.add(CONTROL_VRAM_BYTES)
        if self.require_verified_cancellation:
            controls.add(CONTROL_VERIFIED_CANCELLATION)
        if self.require_model_residency_control:
            controls.add(CONTROL_MODEL_RESIDENCY)
        return frozenset(controls)


@dataclass(frozen=True)
class InferenceBackendResourceCapabilities:
    """Core-supplied claims about controls one exact backend can enforce."""

    backend_id: str
    enforceable_controls: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.backend_id, str) or not _BACKEND_ID_RE.fullmatch(self.backend_id):
            raise ValueError("inference backend ID is invalid")
        object.__setattr__(self, "enforceable_controls", _normalize_controls(self.enforceable_controls))


@dataclass(frozen=True)
class InferenceResourceAdmission:
    """Pure admission result; it never reserves or starts provider work."""

    status: str
    profile_id: str
    backend_id: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in {"admitted", "deferred"}:
            raise ValueError("resource admission status is invalid")
        if self.profile_id not in RESOURCE_PROFILE_IDS:
            raise ValueError("resource admission profile ID is invalid")
        if not isinstance(self.backend_id, str) or not _BACKEND_ID_RE.fullmatch(self.backend_id):
            raise ValueError("resource admission backend ID is invalid")
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(reason, str) and _REASON_RE.fullmatch(reason)
            for reason in self.reasons
        ):
            raise ValueError("resource admission reasons are invalid")
        if self.status == "admitted" and self.reasons:
            raise ValueError("admitted resource work cannot retain denial reasons")
        if self.status == "deferred" and not self.reasons:
            raise ValueError("deferred resource work requires a bounded reason")

    @property
    def admitted(self) -> bool:
        return self.status == "admitted"

    def public_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "profile_id": self.profile_id,
            "backend_id": self.backend_id,
            "reasons": list(self.reasons),
        }


def evaluate_inference_resource_admission(
    profile: InferenceResourceProfile,
    capabilities: InferenceBackendResourceCapabilities,
    *,
    foreground_busy: bool = False,
) -> InferenceResourceAdmission:
    """Fail closed when exact controls are absent or foreground work must yield."""
    if not isinstance(profile, InferenceResourceProfile):
        raise TypeError("inference resource profile is invalid")
    if not isinstance(capabilities, InferenceBackendResourceCapabilities):
        raise TypeError("inference backend resource capabilities are invalid")
    if not isinstance(foreground_busy, bool):
        raise TypeError("foreground_busy must be boolean")
    reasons = [
        f"control_unavailable:{control}"
        for control in sorted(profile.required_controls - capabilities.enforceable_controls)
    ]
    if foreground_busy and profile.profile_id != PROFILE_INTERACTIVE:
        reasons.append("foreground_busy")
    return InferenceResourceAdmission(
        "deferred" if reasons else "admitted",
        profile.profile_id,
        capabilities.backend_id,
        tuple(reasons),
    )


__all__ = [
    "CONTROL_CONCURRENCY", "CONTROL_CPU_THREADS", "CONTROL_MODEL_RESIDENCY",
    "CONTROL_OUTPUT_TOKENS", "CONTROL_RAM_BYTES", "CONTROL_VERIFIED_CANCELLATION",
    "CONTROL_VRAM_BYTES", "CONTROL_WALL_TIME", "InferenceBackendResourceCapabilities",
    "InferenceResourceAdmission", "InferenceResourceProfile", "PROFILE_BACKGROUND",
    "PROFILE_BALANCED", "PROFILE_INTERACTIVE", "RESOURCE_CONTROL_IDS",
    "RESOURCE_PROFILE_IDS", "evaluate_inference_resource_admission",
]
