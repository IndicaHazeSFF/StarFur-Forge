"""Pure readiness projection for a future authenticated local supervisor.

All observations are caller-supplied evidence.  Evaluation performs no probe,
installation, connection, authentication, backend selection, or execution and
cannot convert evidence into authority or an OS-isolation claim.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


SUPERVISOR_READINESS_SCHEMA_VERSION = 1
MAX_SUPERVISOR_OBSERVATION_LIFETIME_SECONDS = 300.0
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SUPERVISOR_ENFORCEMENT_DIMENSIONS = frozenset({
    "endpoint_acl",
    "client_key_storage",
    "service_key_storage",
    "os_peer_identity",
    "request_authentication",
    "response_authentication",
    "request_framing",
    "response_framing",
    "restart_replay_protection",
})
SUPERVISOR_OBSERVATION_STATES = frozenset({
    "unprobed", "unsupported", "unavailable", "available",
})
SUPERVISOR_HOST_STATES = frozenset({
    "unprobed", "unsupported", "unavailable", "prerequisites_met",
})
SUPERVISOR_READINESS_REASONS = frozenset({
    "ready",
    "host_unprobed",
    "host_unsupported",
    "host_unavailable",
    "observation_missing",
    "supervisor_unprobed",
    "supervisor_unsupported",
    "supervisor_unavailable",
    "observation_stale",
    "binding_mismatch",
    "enforcement_missing",
})


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _time(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 <= float(value) < 10**12
    ):
        raise ValueError(f"{label} is invalid")
    return float(value)


def _dimensions(value: object, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise TypeError("supervisor enforcement dimensions must be a collection")
    items = tuple(sorted(value))
    if (not allow_empty and not items) or len(items) > len(SUPERVISOR_ENFORCEMENT_DIMENSIONS):
        raise ValueError("supervisor enforcement dimensions are invalid")
    if len(set(items)) != len(items) or not set(items).issubset(SUPERVISOR_ENFORCEMENT_DIMENSIONS):
        raise ValueError("supervisor enforcement dimensions are invalid")
    return items


@dataclass(frozen=True)
class SupervisorTransportProfile:
    """Core-owned expected binding; it supplies no implementation or authority."""

    schema_version: int
    profile_id: str
    backend_id: str
    service_id: str
    service_revision: str
    transport_kind: str
    transport_revision: str
    policy_revision: str
    required_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SUPERVISOR_READINESS_SCHEMA_VERSION:
            raise ValueError("supervisor transport profile schema version is unsupported")
        for label, value in (
            ("profile identifier", self.profile_id),
            ("backend identifier", self.backend_id),
            ("service identifier", self.service_id),
            ("service revision", self.service_revision),
            ("transport kind", self.transport_kind),
            ("transport revision", self.transport_revision),
            ("policy revision", self.policy_revision),
        ):
            _identifier(value, f"supervisor {label}")
        object.__setattr__(self, "required_dimensions", _dimensions(
            self.required_dimensions, allow_empty=False,
        ))


@dataclass(frozen=True)
class SupervisorTransportObservation:
    """Bounded supplied evidence; construction never discovers host state."""

    schema_version: int
    evidence_revision: str
    state: str
    observed_at: float
    expires_at: float
    profile_id: str
    backend_id: str
    service_id: str
    service_revision: str
    transport_kind: str
    transport_revision: str
    policy_revision: str
    verified_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SUPERVISOR_READINESS_SCHEMA_VERSION:
            raise ValueError("supervisor transport observation schema version is unsupported")
        if self.state not in SUPERVISOR_OBSERVATION_STATES:
            raise ValueError("supervisor transport observation state is invalid")
        for label, value in (
            ("evidence revision", self.evidence_revision),
            ("profile identifier", self.profile_id),
            ("backend identifier", self.backend_id),
            ("service identifier", self.service_id),
            ("service revision", self.service_revision),
            ("transport kind", self.transport_kind),
            ("transport revision", self.transport_revision),
            ("policy revision", self.policy_revision),
        ):
            _identifier(value, f"supervisor {label}")
        observed = _time(self.observed_at, "supervisor observation time")
        expires = _time(self.expires_at, "supervisor observation expiry")
        if (
            observed >= expires
            or expires - observed > MAX_SUPERVISOR_OBSERVATION_LIFETIME_SECONDS
        ):
            raise ValueError("supervisor observation lifetime is invalid")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "verified_dimensions", _dimensions(
            self.verified_dimensions, allow_empty=True,
        ))


@dataclass(frozen=True)
class SupervisorTransportReadiness:
    """Sanitized compatibility result; never authentication or authorization."""

    schema_version: int
    status: str
    reason: str
    evidence_revision: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SUPERVISOR_READINESS_SCHEMA_VERSION:
            raise ValueError("supervisor readiness schema version is unsupported")
        if self.status not in {"ready", "unavailable"}:
            raise ValueError("supervisor readiness status is invalid")
        if self.reason not in SUPERVISOR_READINESS_REASONS:
            raise ValueError("supervisor readiness reason is invalid")
        if (self.status == "ready") != (self.reason == "ready"):
            raise ValueError("supervisor readiness status and reason do not agree")
        if self.evidence_revision is not None:
            _identifier(self.evidence_revision, "supervisor evidence revision")

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "evidence_revision": self.evidence_revision,
        }


def evaluate_supervisor_transport_readiness(
    profile: SupervisorTransportProfile,
    observation: object,
    *,
    host_status: str,
    now: float,
) -> SupervisorTransportReadiness:
    """Evaluate exact supplied evidence without probing or selecting a fallback."""
    if not isinstance(profile, SupervisorTransportProfile):
        raise TypeError("supervisor transport profile is invalid")
    if host_status not in SUPERVISOR_HOST_STATES:
        raise ValueError("supervisor host status is invalid")
    current = _time(now, "supervisor readiness clock")

    def decision(reason: str, evidence: str | None = None):
        return SupervisorTransportReadiness(
            SUPERVISOR_READINESS_SCHEMA_VERSION,
            "ready" if reason == "ready" else "unavailable",
            reason,
            evidence,
        )

    if host_status == "unprobed":
        return decision("host_unprobed")
    if host_status == "unsupported":
        return decision("host_unsupported")
    if host_status == "unavailable":
        return decision("host_unavailable")
    if not isinstance(observation, SupervisorTransportObservation):
        return decision("observation_missing")
    evidence = observation.evidence_revision
    if observation.state == "unprobed":
        return decision("supervisor_unprobed", evidence)
    if observation.state == "unsupported":
        return decision("supervisor_unsupported", evidence)
    if observation.state == "unavailable":
        return decision("supervisor_unavailable", evidence)
    if current < observation.observed_at or current >= observation.expires_at:
        return decision("observation_stale", evidence)
    expected = (
        profile.profile_id,
        profile.backend_id,
        profile.service_id,
        profile.service_revision,
        profile.transport_kind,
        profile.transport_revision,
        profile.policy_revision,
    )
    actual = (
        observation.profile_id,
        observation.backend_id,
        observation.service_id,
        observation.service_revision,
        observation.transport_kind,
        observation.transport_revision,
        observation.policy_revision,
    )
    if actual != expected:
        return decision("binding_mismatch", evidence)
    if not set(profile.required_dimensions).issubset(observation.verified_dimensions):
        return decision("enforcement_missing", evidence)
    return decision("ready", evidence)


__all__ = [
    "MAX_SUPERVISOR_OBSERVATION_LIFETIME_SECONDS",
    "SUPERVISOR_ENFORCEMENT_DIMENSIONS",
    "SUPERVISOR_HOST_STATES",
    "SUPERVISOR_OBSERVATION_STATES",
    "SUPERVISOR_READINESS_REASONS",
    "SUPERVISOR_READINESS_SCHEMA_VERSION",
    "SupervisorTransportObservation",
    "SupervisorTransportProfile",
    "SupervisorTransportReadiness",
    "evaluate_supervisor_transport_readiness",
]
