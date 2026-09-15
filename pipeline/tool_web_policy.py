"""Pure destination policy for a future public-text web fetch tool.

This module parses no content and performs no DNS or network I/O.  A permitted
decision means only that an exact HTTPS destination and supplied short-lived
resolution evidence satisfy the initial egress policy.  A future connector must
still revalidate redirects and enforce the approved address at connect time.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import math
import re
from urllib.parse import urlsplit, urlunsplit


WEB_POLICY_SCHEMA_VERSION = 1
MAX_WEB_URL_CHARACTERS = 2048
MAX_WEB_PATH_CHARACTERS = 1024
MAX_WEB_QUERY_CHARACTERS = 1024
MAX_RESOLVED_ADDRESSES = 16
MAX_WEB_REDIRECT_HOPS = 5
MAX_RESOLUTION_LIFETIME_SECONDS = 300.0
_HOST_RE = re.compile(
    r"^(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_BAD_PERCENT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
WEB_DESTINATION_REASONS = frozenset({
    "permitted",
    "resolution_missing",
    "resolution_invalid",
    "resolution_stale",
    "resolution_mismatch",
    "destination_forbidden",
})
WEB_CONNECTION_REASONS = WEB_DESTINATION_REASONS | frozenset({
    "address_invalid",
    "address_not_approved",
})
WEB_REDIRECT_REASONS = WEB_DESTINATION_REASONS | frozenset({
    "redirect_hop_limit",
    "redirect_loop",
})


def _epoch(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0 <= normalized < 1e12:
        raise ValueError(f"{name} is invalid")
    return normalized


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global


@dataclass(frozen=True)
class WebDestination:
    """One exact canonical public HTTPS destination; never a network grant."""

    schema_version: int
    url: str

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_POLICY_SCHEMA_VERSION:
            raise ValueError("web destination schema version is unsupported")
        if (
            not isinstance(self.url, str)
            or not 1 <= len(self.url) <= MAX_WEB_URL_CHARACTERS
            or self.url != self.url.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in self.url)
            or "\\" in self.url
            or _BAD_PERCENT_RE.search(self.url)
        ):
            raise ValueError("web destination URL is invalid")
        try:
            parsed = urlsplit(self.url)
            port = parsed.port
        except ValueError as error:
            raise ValueError("web destination URL is invalid") from error
        host = parsed.hostname
        if (
            parsed.scheme != "https"
            or host is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or port not in {None, 443}
            or len(parsed.path) > MAX_WEB_PATH_CHARACTERS
            or len(parsed.query) > MAX_WEB_QUERY_CHARACTERS
        ):
            raise ValueError("web destination URL is unsupported")
        if host != host.casefold() or host.endswith("."):
            raise ValueError("web destination host must be canonical lowercase")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
            if not _HOST_RE.fullmatch(host):
                raise ValueError("web destination host is invalid")
        if host == "localhost" or host.endswith(".localhost"):
            raise ValueError("web destination host is forbidden")
        if literal is not None and not literal.is_global:
            raise ValueError("web destination address is forbidden")
        netloc = f"[{host}]" if literal is not None and literal.version == 6 else host
        if port == 443:
            netloc += ":443"
        canonical = urlunsplit(("https", netloc, parsed.path, parsed.query, ""))
        if canonical != self.url:
            raise ValueError("web destination URL must be canonical")

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""

    @property
    def port(self) -> int:
        return urlsplit(self.url).port or 443


@dataclass(frozen=True)
class WebResolutionEvidence:
    """Supplied resolver output; construction does not perform DNS."""

    schema_version: int
    host: str
    port: int
    addresses: tuple[str, ...]
    resolver_revision: str
    observed_at_epoch: float
    expires_at_epoch: float

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_POLICY_SCHEMA_VERSION:
            raise ValueError("web resolution schema version is unsupported")
        if not isinstance(self.host, str) or self.host != self.host.casefold() or not _HOST_RE.fullmatch(self.host):
            raise ValueError("web resolution host is invalid")
        if isinstance(self.port, bool) or self.port != 443:
            raise ValueError("web resolution port is unsupported")
        values = tuple(self.addresses)
        if not 1 <= len(values) <= MAX_RESOLVED_ADDRESSES:
            raise ValueError("web resolution address count is invalid")
        canonical: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise TypeError("web resolution address must be a string")
            try:
                normalized = str(ipaddress.ip_address(value))
            except ValueError as error:
                raise ValueError("web resolution address is invalid") from error
            if normalized != value:
                raise ValueError("web resolution address must be canonical")
            canonical.append(normalized)
        if tuple(sorted(canonical)) != values or len(set(values)) != len(values):
            raise ValueError("web resolution addresses must be unique and sorted")
        if not isinstance(self.resolver_revision, str) or not _REVISION_RE.fullmatch(self.resolver_revision):
            raise ValueError("web resolver revision is invalid")
        observed = _epoch("observed_at_epoch", self.observed_at_epoch)
        expires = _epoch("expires_at_epoch", self.expires_at_epoch)
        if expires <= observed or expires - observed > MAX_RESOLUTION_LIFETIME_SECONDS:
            raise ValueError("web resolution lifetime is invalid")
        object.__setattr__(self, "addresses", values)
        object.__setattr__(self, "observed_at_epoch", observed)
        object.__setattr__(self, "expires_at_epoch", expires)


@dataclass(frozen=True)
class WebDestinationDecision:
    """Policy result only; it is not authorization or proof of connection."""

    schema_version: int
    status: str
    reason: str
    approved_addresses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_POLICY_SCHEMA_VERSION:
            raise ValueError("web destination decision schema version is unsupported")
        if self.status not in {"permitted", "denied"} or self.reason not in WEB_DESTINATION_REASONS:
            raise ValueError("web destination decision is invalid")
        if (self.status == "permitted") != (self.reason == "permitted"):
            raise ValueError("web destination status and reason disagree")
        addresses = tuple(self.approved_addresses)
        if self.status == "denied" and addresses:
            raise ValueError("denied web destination cannot carry addresses")
        if self.status == "permitted" and (
            not addresses or any(not _is_public_address(item) for item in addresses)
        ):
            raise ValueError("permitted web destination addresses are invalid")
        object.__setattr__(self, "approved_addresses", addresses)

    @property
    def permitted(self) -> bool:
        return self.status == "permitted"


@dataclass(frozen=True)
class WebConnectionDecision:
    """Connect-time policy result; never proof that a connection was made."""

    schema_version: int
    status: str
    reason: str
    selected_address: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_POLICY_SCHEMA_VERSION:
            raise ValueError("web connection decision schema version is unsupported")
        if self.status not in {"permitted", "denied"} or self.reason not in WEB_CONNECTION_REASONS:
            raise ValueError("web connection decision is invalid")
        if (self.status == "permitted") != (self.reason == "permitted"):
            raise ValueError("web connection status and reason disagree")
        if self.status == "denied" and self.selected_address is not None:
            raise ValueError("denied web connection cannot carry an address")
        if self.status == "permitted" and not _is_public_address(self.selected_address or ""):
            raise ValueError("permitted web connection address is invalid")

    @property
    def permitted(self) -> bool:
        return self.status == "permitted"


@dataclass(frozen=True)
class WebRedirectDecision:
    """One independently evaluated redirect hop; never network authority."""

    schema_version: int
    status: str
    reason: str
    approved_addresses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != WEB_POLICY_SCHEMA_VERSION:
            raise ValueError("web redirect decision schema version is unsupported")
        if self.status not in {"permitted", "denied"} or self.reason not in WEB_REDIRECT_REASONS:
            raise ValueError("web redirect decision is invalid")
        if (self.status == "permitted") != (self.reason == "permitted"):
            raise ValueError("web redirect status and reason disagree")
        addresses = tuple(self.approved_addresses)
        if self.status == "denied" and addresses:
            raise ValueError("denied web redirect cannot carry addresses")
        if self.status == "permitted" and (
            not addresses or any(not _is_public_address(item) for item in addresses)
        ):
            raise ValueError("permitted web redirect addresses are invalid")
        object.__setattr__(self, "approved_addresses", addresses)

    @property
    def permitted(self) -> bool:
        return self.status == "permitted"


def evaluate_web_destination(
    destination: WebDestination,
    evidence: object,
    *,
    now_epoch: float,
) -> WebDestinationDecision:
    """Evaluate supplied DNS evidence without resolving or connecting."""
    if not isinstance(destination, WebDestination):
        raise TypeError("web destination is invalid")
    now = _epoch("now_epoch", now_epoch)

    def denied(reason: str) -> WebDestinationDecision:
        return WebDestinationDecision(1, "denied", reason)

    if evidence is None:
        return denied("resolution_missing")
    if not isinstance(evidence, WebResolutionEvidence):
        return denied("resolution_invalid")
    if now < evidence.observed_at_epoch or now >= evidence.expires_at_epoch:
        return denied("resolution_stale")
    if evidence.host != destination.host or evidence.port != destination.port:
        return denied("resolution_mismatch")
    if any(not _is_public_address(address) for address in evidence.addresses):
        return denied("destination_forbidden")
    return WebDestinationDecision(1, "permitted", "permitted", evidence.addresses)


def evaluate_web_connection(
    destination: WebDestination,
    evidence: object,
    *,
    connected_address: object,
    now_epoch: float,
) -> WebConnectionDecision:
    """Re-evaluate DNS evidence and pin one supplied connect-time address."""
    if not isinstance(destination, WebDestination):
        raise TypeError("web destination is invalid")

    def denied(reason: str) -> WebConnectionDecision:
        return WebConnectionDecision(1, "denied", reason)

    if not isinstance(connected_address, str):
        return denied("address_invalid")
    try:
        normalized = str(ipaddress.ip_address(connected_address))
    except ValueError:
        return denied("address_invalid")
    if normalized != connected_address:
        return denied("address_invalid")
    destination_decision = evaluate_web_destination(
        destination,
        evidence,
        now_epoch=now_epoch,
    )
    if not destination_decision.permitted:
        return denied(destination_decision.reason)
    if not _is_public_address(normalized):
        return denied("destination_forbidden")
    if normalized not in destination_decision.approved_addresses:
        return denied("address_not_approved")
    return WebConnectionDecision(1, "permitted", "permitted", normalized)


def evaluate_web_redirect(
    current_destination: WebDestination,
    redirect_destination: WebDestination,
    evidence: object,
    *,
    hop_number: int,
    now_epoch: float,
) -> WebRedirectDecision:
    """Evaluate one redirect target with fresh, target-bound DNS evidence."""
    if not isinstance(current_destination, WebDestination):
        raise TypeError("current web destination is invalid")
    if not isinstance(redirect_destination, WebDestination):
        raise TypeError("redirect web destination is invalid")
    if isinstance(hop_number, bool) or not isinstance(hop_number, int) or hop_number < 1:
        raise ValueError("web redirect hop number is invalid")

    def denied(reason: str) -> WebRedirectDecision:
        return WebRedirectDecision(1, "denied", reason)

    if hop_number > MAX_WEB_REDIRECT_HOPS:
        return denied("redirect_hop_limit")
    if current_destination.url == redirect_destination.url:
        return denied("redirect_loop")
    destination_decision = evaluate_web_destination(
        redirect_destination,
        evidence,
        now_epoch=now_epoch,
    )
    if not destination_decision.permitted:
        return denied(destination_decision.reason)
    return WebRedirectDecision(
        1,
        "permitted",
        "permitted",
        destination_decision.approved_addresses,
    )


__all__ = [
    "MAX_RESOLUTION_LIFETIME_SECONDS",
    "MAX_RESOLVED_ADDRESSES",
    "MAX_WEB_REDIRECT_HOPS",
    "WEB_CONNECTION_REASONS",
    "WEB_DESTINATION_REASONS",
    "WEB_REDIRECT_REASONS",
    "WEB_POLICY_SCHEMA_VERSION",
    "WebConnectionDecision",
    "WebDestination",
    "WebDestinationDecision",
    "WebRedirectDecision",
    "WebResolutionEvidence",
    "evaluate_web_connection",
    "evaluate_web_destination",
    "evaluate_web_redirect",
]
