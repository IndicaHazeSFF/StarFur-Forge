"""Pure, provider-free contracts for future sandbox execution backends.

This module describes backend identity, requested limits, supplied capability
observations, and deterministic readiness decisions.  It performs no host
discovery or I/O and grants no authority.  A ``ready`` decision only means the
supplied, still-current evidence matches the requested Core policy; it is not
proof that an operating-system isolation boundary is correctly implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


SANDBOX_BACKEND_SCHEMA_VERSION = 1
MAX_BACKEND_CONTRACT_VERSION = 999
MAX_BACKEND_TASK_KINDS = 32
MAX_ENFORCEMENT_DIMENSIONS = 32
MAX_BACKEND_FAMILIES = 8
MAX_OBSERVATION_LIFETIME_SECONDS = 3600.0

BACKEND_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
PROFILE_ID_RE = BACKEND_ID_RE
REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TASK_KIND_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")

ISOLATION_CLASSES = frozenset({
    "disabled",
    "application_only",
    "container",
    "disposable_vm",
    "hardware_vm",
})
BACKEND_OBSERVATION_STATES = frozenset({
    "unprobed", "unsupported", "unavailable", "available",
})
NETWORK_MODES = frozenset({"disabled"})
ENFORCEMENT_DIMENSIONS = frozenset({
    "wall_time",
    "cpu",
    "memory",
    "process_count",
    "disk",
    "input",
    "stdout",
    "stderr",
    "artifacts",
    "concurrency",
    "filesystem_isolation",
    "process_isolation",
    "network_isolation",
    "cleanup",
})
READINESS_STATUSES = frozenset({"ready", "denied"})
READINESS_REASONS = frozenset({
    "ready",
    "backend_disabled",
    "task_unsupported",
    "profile_unsupported",
    "observation_missing",
    "observation_invalid",
    "backend_unprobed",
    "backend_unsupported",
    "backend_unavailable",
    "observation_stale",
    "binding_mismatch",
    "enforcement_missing",
    "limits_unsupported",
})


def _strict_int(name: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _finite_number(name: str, value: object, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    if not minimum <= normalized <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return normalized


def _identifier(name: str, value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _bounded_identifiers(
    name: str,
    values: object,
    *,
    pattern: re.Pattern[str],
    maximum: int,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list, frozenset, set)):
        raise TypeError(f"{name} must be a collection")
    normalized = tuple(sorted(values))
    if not allow_empty and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(normalized) > maximum:
        raise ValueError(f"{name} exceeds its item limit")
    if any(not isinstance(item, str) or not pattern.fullmatch(item) for item in normalized):
        raise ValueError(f"{name} contains an invalid identifier")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return normalized


@dataclass(frozen=True)
class ExecutionLimits:
    """Explicit finite ceilings requested from and enforced by a backend."""

    wall_time_seconds: float
    cpu_cores: int
    memory_bytes: int
    process_count: int
    disk_bytes: int
    input_bytes: int
    stdout_bytes: int
    stderr_bytes: int
    artifact_count: int
    artifact_bytes: int
    concurrency: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "wall_time_seconds", _finite_number(
            "wall_time_seconds", self.wall_time_seconds, minimum=0.1, maximum=86_400.0,
        ))
        for name, value, maximum in (
            ("cpu_cores", self.cpu_cores, 1024),
            ("memory_bytes", self.memory_bytes, 1 << 60),
            ("process_count", self.process_count, 1_000_000),
            ("disk_bytes", self.disk_bytes, 1 << 60),
            ("input_bytes", self.input_bytes, 1 << 50),
            ("stdout_bytes", self.stdout_bytes, 1 << 50),
            ("stderr_bytes", self.stderr_bytes, 1 << 50),
            ("artifact_count", self.artifact_count, 1_000_000),
            ("artifact_bytes", self.artifact_bytes, 1 << 50),
            ("concurrency", self.concurrency, 1024),
        ):
            _strict_int(name, value, minimum=1, maximum=maximum)

    def supports(self, requested: "ExecutionLimits") -> bool:
        """Return whether these enforceable maxima cover every requested limit."""
        if not isinstance(requested, ExecutionLimits):
            return False
        return all(
            getattr(requested, field) <= getattr(self, field)
            for field in self.__dataclass_fields__
        )

    def public_dict(self) -> dict[str, int | float]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True)
class EnforcementProfile:
    """One exact Core policy profile; it is a requirement, not authority."""

    schema_version: int
    profile_id: str
    policy_revision: str
    required_isolation_class: str
    task_kinds: tuple[str, ...]
    network_mode: str
    required_dimensions: tuple[str, ...]
    maximum_limits: ExecutionLimits

    def __post_init__(self) -> None:
        _strict_int(
            "enforcement profile schema_version", self.schema_version,
            minimum=SANDBOX_BACKEND_SCHEMA_VERSION, maximum=SANDBOX_BACKEND_SCHEMA_VERSION,
        )
        _identifier("profile_id", self.profile_id, PROFILE_ID_RE)
        _identifier("policy_revision", self.policy_revision, REVISION_RE)
        if self.required_isolation_class not in ISOLATION_CLASSES:
            raise ValueError("required_isolation_class is invalid")
        object.__setattr__(self, "task_kinds", _bounded_identifiers(
            "task_kinds", self.task_kinds, pattern=TASK_KIND_RE, maximum=MAX_BACKEND_TASK_KINDS,
        ))
        if self.network_mode not in NETWORK_MODES:
            raise ValueError("network_mode is invalid")
        dimensions = _bounded_identifiers(
            "required_dimensions", self.required_dimensions,
            pattern=BACKEND_ID_RE, maximum=MAX_ENFORCEMENT_DIMENSIONS,
        )
        if not set(dimensions).issubset(ENFORCEMENT_DIMENSIONS):
            raise ValueError("required_dimensions contains an unsupported dimension")
        object.__setattr__(self, "required_dimensions", dimensions)
        if not isinstance(self.maximum_limits, ExecutionLimits):
            raise TypeError("maximum_limits must be ExecutionLimits")


@dataclass(frozen=True)
class BackendDescriptor:
    """Immutable Core-owned backend metadata with no adapter or probe hooks."""

    schema_version: int
    backend_id: str
    backend_version: int
    isolation_class: str
    host_families: tuple[str, ...]
    guest_families: tuple[str, ...]
    supported_task_kinds: tuple[str, ...]
    supported_profile_ids: tuple[str, ...]
    image_revision: str
    supervisor_revision: str

    def __post_init__(self) -> None:
        _strict_int(
            "backend descriptor schema_version", self.schema_version,
            minimum=SANDBOX_BACKEND_SCHEMA_VERSION, maximum=SANDBOX_BACKEND_SCHEMA_VERSION,
        )
        _identifier("backend_id", self.backend_id, BACKEND_ID_RE)
        _strict_int(
            "backend_version", self.backend_version,
            minimum=1, maximum=MAX_BACKEND_CONTRACT_VERSION,
        )
        if self.isolation_class not in ISOLATION_CLASSES:
            raise ValueError("isolation_class is invalid")
        object.__setattr__(self, "host_families", _bounded_identifiers(
            "host_families", self.host_families, pattern=BACKEND_ID_RE,
            maximum=MAX_BACKEND_FAMILIES,
        ))
        object.__setattr__(self, "guest_families", _bounded_identifiers(
            "guest_families", self.guest_families, pattern=BACKEND_ID_RE,
            maximum=MAX_BACKEND_FAMILIES, allow_empty=self.isolation_class == "disabled",
        ))
        object.__setattr__(self, "supported_task_kinds", _bounded_identifiers(
            "supported_task_kinds", self.supported_task_kinds, pattern=TASK_KIND_RE,
            maximum=MAX_BACKEND_TASK_KINDS, allow_empty=self.isolation_class == "disabled",
        ))
        object.__setattr__(self, "supported_profile_ids", _bounded_identifiers(
            "supported_profile_ids", self.supported_profile_ids, pattern=PROFILE_ID_RE,
            maximum=MAX_BACKEND_TASK_KINDS, allow_empty=self.isolation_class == "disabled",
        ))
        _identifier("image_revision", self.image_revision, REVISION_RE)
        _identifier("supervisor_revision", self.supervisor_revision, REVISION_RE)


@dataclass(frozen=True)
class BackendObservation:
    """Caller-supplied bounded evidence; construction does not perform a probe."""

    schema_version: int
    backend_id: str
    backend_version: int
    state: str
    evidence_revision: str
    observed_at_epoch: float
    expires_at_epoch: float
    isolation_class: str
    profile_id: str
    policy_revision: str
    image_revision: str
    supervisor_revision: str
    enforced_dimensions: tuple[str, ...]
    enforced_limits: ExecutionLimits

    def __post_init__(self) -> None:
        _strict_int(
            "backend observation schema_version", self.schema_version,
            minimum=SANDBOX_BACKEND_SCHEMA_VERSION, maximum=SANDBOX_BACKEND_SCHEMA_VERSION,
        )
        _identifier("backend_id", self.backend_id, BACKEND_ID_RE)
        _strict_int(
            "backend_version", self.backend_version,
            minimum=1, maximum=MAX_BACKEND_CONTRACT_VERSION,
        )
        if self.state not in BACKEND_OBSERVATION_STATES:
            raise ValueError("backend observation state is invalid")
        _identifier("evidence_revision", self.evidence_revision, REVISION_RE)
        observed = _finite_number(
            "observed_at_epoch", self.observed_at_epoch, minimum=0.0, maximum=1e12,
        )
        expires = _finite_number(
            "expires_at_epoch", self.expires_at_epoch, minimum=0.0, maximum=1e12,
        )
        if expires <= observed or expires - observed > MAX_OBSERVATION_LIFETIME_SECONDS:
            raise ValueError("backend observation lifetime is invalid")
        object.__setattr__(self, "observed_at_epoch", observed)
        object.__setattr__(self, "expires_at_epoch", expires)
        if self.isolation_class not in ISOLATION_CLASSES:
            raise ValueError("backend observation isolation_class is invalid")
        for name, value, pattern in (
            ("profile_id", self.profile_id, PROFILE_ID_RE),
            ("policy_revision", self.policy_revision, REVISION_RE),
            ("image_revision", self.image_revision, REVISION_RE),
            ("supervisor_revision", self.supervisor_revision, REVISION_RE),
        ):
            _identifier(name, value, pattern)
        dimensions = _bounded_identifiers(
            "enforced_dimensions", self.enforced_dimensions,
            pattern=BACKEND_ID_RE, maximum=MAX_ENFORCEMENT_DIMENSIONS, allow_empty=True,
        )
        if not set(dimensions).issubset(ENFORCEMENT_DIMENSIONS):
            raise ValueError("enforced_dimensions contains an unsupported dimension")
        object.__setattr__(self, "enforced_dimensions", dimensions)
        if not isinstance(self.enforced_limits, ExecutionLimits):
            raise TypeError("enforced_limits must be ExecutionLimits")


@dataclass(frozen=True)
class BackendReadiness:
    """A pure compatibility decision; never a grant, approval, or execution token."""

    schema_version: int
    backend_id: str
    profile_id: str
    task_kind: str
    status: str
    reason: str
    evidence_revision: str | None = None

    def __post_init__(self) -> None:
        _strict_int(
            "backend readiness schema_version", self.schema_version,
            minimum=SANDBOX_BACKEND_SCHEMA_VERSION, maximum=SANDBOX_BACKEND_SCHEMA_VERSION,
        )
        _identifier("backend_id", self.backend_id, BACKEND_ID_RE)
        _identifier("profile_id", self.profile_id, PROFILE_ID_RE)
        _identifier("task_kind", self.task_kind, TASK_KIND_RE)
        if self.status not in READINESS_STATUSES or self.reason not in READINESS_REASONS:
            raise ValueError("backend readiness outcome is invalid")
        if (self.status == "ready") != (self.reason == "ready"):
            raise ValueError("ready status and reason must agree")
        if self.evidence_revision is not None:
            _identifier("evidence_revision", self.evidence_revision, REVISION_RE)

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "backend_id": self.backend_id,
            "profile_id": self.profile_id,
            "task_kind": self.task_kind,
            "status": self.status,
            "reason": self.reason,
            "evidence_revision": self.evidence_revision,
        }


def evaluate_backend_readiness(
    descriptor: BackendDescriptor,
    profile: EnforcementProfile,
    observation: object,
    *,
    task_kind: str,
    requested_limits: ExecutionLimits,
    now_epoch: float,
) -> BackendReadiness:
    """Compare one explicitly selected backend with one exact policy profile."""
    if not isinstance(descriptor, BackendDescriptor):
        raise TypeError("descriptor must be BackendDescriptor")
    if not isinstance(profile, EnforcementProfile):
        raise TypeError("profile must be EnforcementProfile")
    task = _identifier("task_kind", task_kind, TASK_KIND_RE)
    if not isinstance(requested_limits, ExecutionLimits):
        raise TypeError("requested_limits must be ExecutionLimits")
    now = _finite_number("now_epoch", now_epoch, minimum=0.0, maximum=1e12)

    def decision(reason: str, evidence_revision: str | None = None) -> BackendReadiness:
        return BackendReadiness(
            SANDBOX_BACKEND_SCHEMA_VERSION,
            descriptor.backend_id,
            profile.profile_id,
            task,
            "ready" if reason == "ready" else "denied",
            reason,
            evidence_revision,
        )

    if descriptor.isolation_class == "disabled":
        return decision("backend_disabled")
    if task not in descriptor.supported_task_kinds or task not in profile.task_kinds:
        return decision("task_unsupported")
    if profile.profile_id not in descriptor.supported_profile_ids:
        return decision("profile_unsupported")
    if not isinstance(observation, BackendObservation):
        return decision("observation_missing" if observation is None else "observation_invalid")
    if observation.state == "unprobed":
        return decision("backend_unprobed", observation.evidence_revision)
    if observation.state == "unsupported":
        return decision("backend_unsupported", observation.evidence_revision)
    if observation.state == "unavailable":
        return decision("backend_unavailable", observation.evidence_revision)
    if now < observation.observed_at_epoch or now >= observation.expires_at_epoch:
        return decision("observation_stale", observation.evidence_revision)
    if (
        observation.backend_id != descriptor.backend_id
        or observation.backend_version != descriptor.backend_version
        or observation.isolation_class != descriptor.isolation_class
        or profile.required_isolation_class != descriptor.isolation_class
        or observation.profile_id != profile.profile_id
        or observation.policy_revision != profile.policy_revision
        or observation.image_revision != descriptor.image_revision
        or observation.supervisor_revision != descriptor.supervisor_revision
    ):
        return decision("binding_mismatch", observation.evidence_revision)
    if not set(profile.required_dimensions).issubset(observation.enforced_dimensions):
        return decision("enforcement_missing", observation.evidence_revision)
    if not profile.maximum_limits.supports(requested_limits):
        return decision("limits_unsupported", observation.evidence_revision)
    if not observation.enforced_limits.supports(requested_limits):
        return decision("limits_unsupported", observation.evidence_revision)
    return decision("ready", observation.evidence_revision)


__all__ = [
    "BACKEND_OBSERVATION_STATES",
    "BackendDescriptor",
    "BackendObservation",
    "BackendReadiness",
    "ENFORCEMENT_DIMENSIONS",
    "EnforcementProfile",
    "ExecutionLimits",
    "ISOLATION_CLASSES",
    "MAX_OBSERVATION_LIFETIME_SECONDS",
    "NETWORK_MODES",
    "READINESS_REASONS",
    "READINESS_STATUSES",
    "SANDBOX_BACKEND_SCHEMA_VERSION",
    "evaluate_backend_readiness",
]
