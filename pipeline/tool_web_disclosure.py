"""Pure deny-by-default disclosure policy for future web tools.

The caller must supply Core-classified metadata, never raw content.  Initial
policy permits only no-data and explicitly public-data classifications.  It has
no mechanism for private or secret disclosure: adding one later requires an
exact broker-bound authorization record rather than a boolean or model claim.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


WEB_DISCLOSURE_SCHEMA_VERSION = 1
WEB_DATA_CLASSIFICATIONS = frozenset({"none", "public", "private", "secret"})
WEB_DISCLOSURE_SOURCE_KINDS = frozenset({
    "none",
    "core_public",
    "user_supplied",
    "private_resource",
    "secret_store",
})
MAX_WEB_DISCLOSURE_BYTES = 16 * 1024
WEB_DISCLOSURE_REASONS = frozenset({
    "no_disclosure",
    "public_disclosure",
    "private_disclosure_unsupported",
    "secret_disclosure_forbidden",
})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class WebDisclosureIntent:
    """Content-free metadata classified by trusted Core policy."""

    schema_version: int
    classification: str
    source_kind: str
    byte_count: int
    content_sha256: str | None

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_DISCLOSURE_SCHEMA_VERSION:
            raise ValueError("web disclosure schema version is unsupported")
        if self.classification not in WEB_DATA_CLASSIFICATIONS:
            raise ValueError("web disclosure classification is invalid")
        if self.source_kind not in WEB_DISCLOSURE_SOURCE_KINDS:
            raise ValueError("web disclosure source kind is invalid")
        if (
            isinstance(self.byte_count, bool)
            or not isinstance(self.byte_count, int)
            or not 0 <= self.byte_count <= MAX_WEB_DISCLOSURE_BYTES
        ):
            raise ValueError("web disclosure byte count is invalid")
        if self.classification == "none":
            if self.source_kind != "none" or self.byte_count != 0 or self.content_sha256 is not None:
                raise ValueError("empty web disclosure metadata is inconsistent")
            return
        if self.source_kind == "none" or self.byte_count == 0:
            raise ValueError("web disclosure content metadata is incomplete")
        if not isinstance(self.content_sha256, str) or not _DIGEST_RE.fullmatch(self.content_sha256):
            raise ValueError("web disclosure content digest is invalid")
        if self.source_kind == "secret_store" and self.classification != "secret":
            raise ValueError("secret-store disclosure must remain secret-classified")
        if self.source_kind == "private_resource" and self.classification == "public":
            raise ValueError("private-resource disclosure cannot be public-classified")


@dataclass(frozen=True)
class WebDisclosureDecision:
    """Classification decision only; never network or tool authorization."""

    schema_version: int
    status: str
    reason: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_DISCLOSURE_SCHEMA_VERSION:
            raise ValueError("web disclosure decision schema version is unsupported")
        if self.status not in {"permitted", "denied"} or self.reason not in WEB_DISCLOSURE_REASONS:
            raise ValueError("web disclosure decision is invalid")
        permitted_reason = self.reason in {"no_disclosure", "public_disclosure"}
        if (self.status == "permitted") != permitted_reason:
            raise ValueError("web disclosure decision status and reason disagree")

    @property
    def permitted(self) -> bool:
        return self.status == "permitted"


def evaluate_web_disclosure(intent: WebDisclosureIntent) -> WebDisclosureDecision:
    """Apply initial fixed policy without consulting a model or grant store."""
    if not isinstance(intent, WebDisclosureIntent):
        raise TypeError("web disclosure intent is invalid")
    if intent.classification == "none":
        return WebDisclosureDecision(1, "permitted", "no_disclosure")
    if intent.classification == "public":
        return WebDisclosureDecision(1, "permitted", "public_disclosure")
    if intent.classification == "private":
        return WebDisclosureDecision(1, "denied", "private_disclosure_unsupported")
    return WebDisclosureDecision(1, "denied", "secret_disclosure_forbidden")


__all__ = [
    "MAX_WEB_DISCLOSURE_BYTES",
    "WEB_DATA_CLASSIFICATIONS",
    "WEB_DISCLOSURE_REASONS",
    "WEB_DISCLOSURE_SCHEMA_VERSION",
    "WEB_DISCLOSURE_SOURCE_KINDS",
    "WebDisclosureDecision",
    "WebDisclosureIntent",
    "evaluate_web_disclosure",
]
