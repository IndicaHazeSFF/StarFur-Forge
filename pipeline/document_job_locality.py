"""Pure deny-by-default locality policy for future private-job processing.

No DNS, network, provider construction, discovery, environment reads, grants,
consent or execution. Trusted Core adapters must independently validate supplied
evidence. An eligible decision is not authorization or OS-level egress isolation.
"""

from dataclasses import dataclass, field
from hashlib import sha256
import re
from urllib.parse import urlsplit


ANNOTATION_LOCALITY_POLICY = "annotation-loopback-no-relay-v1"


class AnnotationLocalityError(ValueError):
    """Content-free invalid private-processing target/evidence."""


@dataclass(frozen=True, repr=False)
class LocalAnnotationTarget:
    endpoint: str = field(repr=False)

    def __post_init__(self):
        try:
            value = self.endpoint
            if not isinstance(value, str) or len(value) > 96 or not value.isascii():
                raise ValueError
            parsed = urlsplit(value)
            if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
                    or parsed.username is not None or parsed.password is not None
                    or parsed.path or parsed.query or parsed.fragment
                    or parsed.port is None or not 1 <= parsed.port <= 65535):
                raise ValueError
            host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
            if value != f"http://{host}:{parsed.port}":
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise AnnotationLocalityError("private annotation endpoint is not supported") from None

    @property
    def fingerprint(self):
        return sha256((ANNOTATION_LOCALITY_POLICY + "\n" + self.endpoint).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class AnnotationLocalityEvidence:
    """Declarative evidence from trusted Core verification, never chat input.

    Server cloud-disabled status must describe the actual server, not the
    client's environment. Model digest binds inspected local artifact identity;
    it is not independently verified by this pure contract. No runtime adapter
    currently produces this evidence and no default caller marks it verified.
    """
    target_fingerprint: str = field(repr=False)
    model: str = field(repr=False)
    model_digest: str | None = field(default=None, repr=False)
    local_execution_verified: bool = False
    server_cloud_disabled: bool = False
    direct_transport_verified: bool = False
    policy_revision: str = ANNOTATION_LOCALITY_POLICY

    def __post_init__(self):
        if (not isinstance(self.target_fingerprint, str)
                or re.fullmatch(r"[0-9a-f]{64}", self.target_fingerprint) is None
                or not isinstance(self.model, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}", self.model) is None
                or (self.model_digest is not None and (not isinstance(self.model_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}", self.model_digest) is None))
                or any(type(value) is not bool for value in (
                    self.local_execution_verified, self.server_cloud_disabled, self.direct_transport_verified))
                or self.policy_revision != ANNOTATION_LOCALITY_POLICY):
            raise AnnotationLocalityError("private annotation locality evidence is invalid")


@dataclass(frozen=True)
class AnnotationLocalityDecision:
    status: str
    reason: str

    def __post_init__(self):
        outcomes = {"eligible": {"locality_evidence_satisfied"}, "denied": {
            "locality_unverified", "target_mismatch", "model_mismatch", "cloud_model_forbidden",
            "local_artifact_unverified", "local_execution_unverified", "cloud_relay_not_disabled",
            "direct_transport_unverified",
        }}
        if (not isinstance(self.status, str) or self.status not in outcomes
                or not isinstance(self.reason, str) or self.reason not in outcomes[self.status]):
            raise AnnotationLocalityError("private annotation locality decision is invalid")


def evaluate_annotation_locality(target, model, evidence=None):
    """Compare declared verified evidence only; never turn labels into proof.

    Ordinary provider name, loopback endpoint, local-looking model name and
    source/job/persona identifiers cannot satisfy absent evidence. Future LAN or
    cloud support needs a separate policy revision, not an override boolean.
    """
    if type(target) is not LocalAnnotationTarget or not isinstance(model, str):
        raise AnnotationLocalityError("validated private annotation target/model is required")
    # This negative label guard is additional defense, not proof that an alias
    # without 'cloud' is local. Artifact/server evidence is still mandatory.
    if "cloud" in re.split(r"[:/@._+-]", model.casefold()):
        return AnnotationLocalityDecision("denied", "cloud_model_forbidden")
    if evidence is None:
        return AnnotationLocalityDecision("denied", "locality_unverified")
    if type(evidence) is not AnnotationLocalityEvidence:
        raise AnnotationLocalityError("validated private annotation locality evidence is required")
    for denied, reason in (
        (evidence.target_fingerprint != target.fingerprint, "target_mismatch"),
        (evidence.model != model, "model_mismatch"),
        (evidence.model_digest is None, "local_artifact_unverified"),
        (not evidence.local_execution_verified, "local_execution_unverified"),
        (not evidence.server_cloud_disabled, "cloud_relay_not_disabled"),
        (not evidence.direct_transport_verified, "direct_transport_unverified"),
    ):
        if denied:
            return AnnotationLocalityDecision("denied", reason)
    return AnnotationLocalityDecision("eligible", "locality_evidence_satisfied")
