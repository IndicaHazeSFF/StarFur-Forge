"""Provider-free contracts for one future sandbox guest image.

The values here bind a Core-owned expectation to caller-supplied verification
evidence.  Evaluation is pure and cannot download, open, hash, sign, install, or
launch an image.  A compatible decision is not backend readiness or authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


SANDBOX_IMAGE_SCHEMA_VERSION = 1
MAX_IMAGE_EVIDENCE_LIFETIME_SECONDS = 3600.0
_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
IMAGE_COMPATIBILITY_REASONS = frozenset({
    "compatible",
    "image_unconfigured",
    "evidence_missing",
    "evidence_invalid",
    "evidence_stale",
    "binding_mismatch",
    "integrity_unverified",
    "signature_unverified",
    "license_unapproved",
    "patch_status_unacceptable",
})


def _identifier(name: str, value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{name} is invalid")
    return value


def _epoch(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized < 1e12:
        raise ValueError(f"{name} is invalid")
    return normalized


@dataclass(frozen=True)
class SandboxImageRequirement:
    """Exact Core-owned image expectation; never an installer instruction."""

    schema_version: int
    image_id: str
    image_revision: str
    guest_family: str
    guest_generation: int
    architecture: str
    image_format: str
    content_sha256: str
    toolchain_revision: str
    signature_policy: str
    signer_id: str
    license_policy_revision: str
    patch_policy_revision: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SANDBOX_IMAGE_SCHEMA_VERSION:
            raise ValueError("sandbox image schema version is unsupported")
        _identifier("image_id", self.image_id, _ID_RE)
        for name in (
            "image_revision", "toolchain_revision", "signer_id",
            "license_policy_revision", "patch_policy_revision",
        ):
            _identifier(name, getattr(self, name), _REVISION_RE)
        if self.guest_family != "linux" or self.guest_generation != 2:
            raise ValueError("sandbox image guest profile is unsupported")
        if self.architecture != "x86_64" or self.image_format != "vhdx":
            raise ValueError("sandbox image platform profile is unsupported")
        _identifier("content_sha256", self.content_sha256, _SHA256_RE)
        if self.signature_policy != "required":
            raise ValueError("sandbox image signature policy must be required")

    def binding_tuple(self) -> tuple[object, ...]:
        return tuple(getattr(self, name) for name in self.__dataclass_fields__)


@dataclass(frozen=True)
class SandboxImageEvidence:
    """Short-lived supplied evidence; construction performs no verification."""

    schema_version: int
    image_id: str
    image_revision: str
    guest_family: str
    guest_generation: int
    architecture: str
    image_format: str
    observed_content_sha256: str
    toolchain_revision: str
    signer_id: str
    license_policy_revision: str
    patch_policy_revision: str
    integrity_status: str
    signature_status: str
    license_status: str
    patch_status: str
    verifier_revision: str
    observed_at_epoch: float
    expires_at_epoch: float

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SANDBOX_IMAGE_SCHEMA_VERSION:
            raise ValueError("sandbox image evidence schema version is unsupported")
        _identifier("image_id", self.image_id, _ID_RE)
        for name in (
            "image_revision", "toolchain_revision", "signer_id", "license_policy_revision",
            "patch_policy_revision", "verifier_revision",
        ):
            _identifier(name, getattr(self, name), _REVISION_RE)
        if self.guest_family != "linux" or self.guest_generation != 2:
            raise ValueError("sandbox image evidence guest profile is unsupported")
        if self.architecture != "x86_64" or self.image_format != "vhdx":
            raise ValueError("sandbox image evidence platform profile is unsupported")
        _identifier("observed_content_sha256", self.observed_content_sha256, _SHA256_RE)
        if self.integrity_status not in {"verified", "failed"}:
            raise ValueError("sandbox image integrity status is invalid")
        if self.signature_status not in {"verified", "unverified", "failed"}:
            raise ValueError("sandbox image signature status is invalid")
        if self.license_status not in {"approved", "unapproved"}:
            raise ValueError("sandbox image license status is invalid")
        if self.patch_status not in {"current", "stale", "unknown"}:
            raise ValueError("sandbox image patch status is invalid")
        observed = _epoch("observed_at_epoch", self.observed_at_epoch)
        expires = _epoch("expires_at_epoch", self.expires_at_epoch)
        if expires <= observed or expires - observed > MAX_IMAGE_EVIDENCE_LIFETIME_SECONDS:
            raise ValueError("sandbox image evidence lifetime is invalid")
        object.__setattr__(self, "observed_at_epoch", observed)
        object.__setattr__(self, "expires_at_epoch", expires)


@dataclass(frozen=True)
class SandboxImageCompatibility:
    """Pure compatibility result; never readiness, trust, or permission."""

    schema_version: int
    status: str
    reason: str
    verifier_revision: str | None

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SANDBOX_IMAGE_SCHEMA_VERSION:
            raise ValueError("sandbox image compatibility schema version is unsupported")
        if self.status not in {"compatible", "denied"}:
            raise ValueError("sandbox image compatibility status is invalid")
        if self.reason not in IMAGE_COMPATIBILITY_REASONS:
            raise ValueError("sandbox image compatibility reason is invalid")
        if (self.status == "compatible") != (self.reason == "compatible"):
            raise ValueError("sandbox image compatibility status and reason disagree")
        if self.verifier_revision is not None:
            _identifier("verifier_revision", self.verifier_revision, _REVISION_RE)

    @property
    def compatible(self) -> bool:
        return self.status == "compatible"

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reason": self.reason,
            "verifier_revision": self.verifier_revision,
        }


def evaluate_image_compatibility(
    requirement: SandboxImageRequirement | None,
    evidence: object,
    *,
    now_epoch: float,
) -> SandboxImageCompatibility:
    """Compare supplied evidence with one exact expected image binding."""
    now = _epoch("now_epoch", now_epoch)

    def denied(reason: str, verifier: str | None = None) -> SandboxImageCompatibility:
        return SandboxImageCompatibility(1, "denied", reason, verifier)

    if requirement is None:
        return denied("image_unconfigured")
    if not isinstance(requirement, SandboxImageRequirement):
        raise TypeError("sandbox image requirement is invalid")
    if evidence is None:
        return denied("evidence_missing")
    if not isinstance(evidence, SandboxImageEvidence):
        return denied("evidence_invalid")
    verifier = evidence.verifier_revision
    if now < evidence.observed_at_epoch or now >= evidence.expires_at_epoch:
        return denied("evidence_stale", verifier)
    expected_binding = (
        requirement.schema_version, requirement.image_id, requirement.image_revision,
        requirement.guest_family, requirement.guest_generation, requirement.architecture,
        requirement.image_format, requirement.content_sha256, requirement.toolchain_revision,
        requirement.signer_id, requirement.license_policy_revision,
        requirement.patch_policy_revision,
    )
    observed_binding = (
        evidence.schema_version, evidence.image_id, evidence.image_revision,
        evidence.guest_family, evidence.guest_generation, evidence.architecture,
        evidence.image_format, evidence.observed_content_sha256, evidence.toolchain_revision,
        evidence.signer_id, evidence.license_policy_revision,
        evidence.patch_policy_revision,
    )
    if observed_binding != expected_binding:
        return denied("binding_mismatch", verifier)
    if evidence.integrity_status != "verified":
        return denied("integrity_unverified", verifier)
    if evidence.signature_status != "verified":
        return denied("signature_unverified", verifier)
    if evidence.license_status != "approved":
        return denied("license_unapproved", verifier)
    if evidence.patch_status != "current":
        return denied("patch_status_unacceptable", verifier)
    return SandboxImageCompatibility(1, "compatible", "compatible", verifier)


__all__ = [
    "IMAGE_COMPATIBILITY_REASONS",
    "MAX_IMAGE_EVIDENCE_LIFETIME_SECONDS",
    "SANDBOX_IMAGE_SCHEMA_VERSION",
    "SandboxImageCompatibility",
    "SandboxImageEvidence",
    "SandboxImageRequirement",
    "evaluate_image_compatibility",
]
