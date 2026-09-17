"""Provider-free quarantine contract for future public web-search results.

The future trusted search connector must translate provider-specific output into
this narrow form.  Candidates are discovery hints only: their titles remain
untrusted, their URLs are not fetched or approved, and neither rank nor presence
is evidence that a claim is true.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import secrets
from threading import RLock
from typing import Callable
import unicodedata

from pipeline.tool_contracts import ARTIFACT_REF_RE
from pipeline.tool_web_policy import WebDestination


WEB_SEARCH_ARTIFACT_SCHEMA_VERSION = 1
MAX_WEB_SEARCH_RESULTS = 8
MAX_WEB_SEARCH_TITLE_CHARACTERS = 240
MAX_SESSION_WEB_SEARCH_ARTIFACTS = 32
MAX_SESSION_WEB_SEARCH_ARTIFACT_BYTES = 256 * 1024
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")


def _title(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("web search result title must be text")
    normalized = unicodedata.normalize("NFC", " ".join(value.strip().split()))
    if (
        not normalized
        or len(normalized) > MAX_WEB_SEARCH_TITLE_CHARACTERS
        or any(unicodedata.category(character) in {"Cc", "Cf"} for character in normalized)
    ):
        raise ValueError("web search result title is invalid")
    return normalized


def _artifact_digest(query_sha256: str, service_id: str, results: tuple["WebSearchCandidate", ...]) -> str:
    encoded = json.dumps(
        {
            "query_sha256": query_sha256,
            "results": [item.public_dict() for item in results],
            "service_id": service_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class WebSearchCandidate:
    rank: int
    url: str
    title: str

    def __post_init__(self) -> None:
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or not 1 <= self.rank <= MAX_WEB_SEARCH_RESULTS:
            raise ValueError("web search result rank is invalid")
        destination = WebDestination(1, self.url)
        object.__setattr__(self, "url", destination.url)
        object.__setattr__(self, "title", _title(self.title))

    def public_dict(self) -> dict[str, object]:
        return {"rank": self.rank, "url": self.url, "title": self.title}


@dataclass(frozen=True)
class WebSearchArtifact:
    schema_version: int
    query_sha256: str
    service_id: str
    results: tuple[WebSearchCandidate, ...]
    trust_label: str
    artifact_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != WEB_SEARCH_ARTIFACT_SCHEMA_VERSION:
            raise ValueError("web search artifact schema version is unsupported")
        if not isinstance(self.query_sha256, str) or not _DIGEST_RE.fullmatch(self.query_sha256):
            raise ValueError("web search artifact query digest is invalid")
        if not isinstance(self.service_id, str) or not _SERVICE_RE.fullmatch(self.service_id):
            raise ValueError("web search artifact service ID is invalid")
        results = tuple(self.results)
        if not results or len(results) > MAX_WEB_SEARCH_RESULTS or not all(
            isinstance(item, WebSearchCandidate) for item in results
        ):
            raise ValueError("web search artifact results are invalid")
        ranks = tuple(item.rank for item in results)
        if ranks != tuple(range(1, len(results) + 1)):
            raise ValueError("web search artifact ranks must be contiguous")
        urls = tuple(item.url for item in results)
        if len(set(urls)) != len(urls):
            raise ValueError("web search artifact URLs must be unique")
        if self.trust_label != "untrusted_discovery":
            raise ValueError("web search artifact trust label is invalid")
        expected = _artifact_digest(self.query_sha256, self.service_id, results)
        if not isinstance(self.artifact_sha256, str) or self.artifact_sha256 != expected:
            raise ValueError("web search artifact digest is inconsistent")
        object.__setattr__(self, "results", results)

    @classmethod
    def create(
        cls,
        query_sha256: object,
        service_id: object,
        results: object,
    ) -> "WebSearchArtifact":
        if not isinstance(query_sha256, str) or not _DIGEST_RE.fullmatch(query_sha256):
            raise ValueError("web search artifact query digest is invalid")
        if not isinstance(service_id, str) or not _SERVICE_RE.fullmatch(service_id):
            raise ValueError("web search artifact service ID is invalid")
        if not isinstance(results, (tuple, list)):
            raise TypeError("web search artifact results must be a sequence")
        checked = tuple(results)
        return cls(
            WEB_SEARCH_ARTIFACT_SCHEMA_VERSION,
            query_sha256,
            service_id,
            checked,
            "untrusted_discovery",
            _artifact_digest(query_sha256, service_id, checked),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "query_sha256": self.query_sha256,
            "service_id": self.service_id,
            "results": [item.public_dict() for item in self.results],
            "trust_label": self.trust_label,
            "artifact_sha256": self.artifact_sha256,
        }


class SessionWebSearchArtifactStore:
    """Bounded exact-reference quarantine for one application session."""

    def __init__(
        self,
        *,
        ref_factory: Callable[[], str] | None = None,
        maximum_artifacts: int = MAX_SESSION_WEB_SEARCH_ARTIFACTS,
        maximum_total_bytes: int = MAX_SESSION_WEB_SEARCH_ARTIFACT_BYTES,
    ) -> None:
        if ref_factory is not None and not callable(ref_factory):
            raise TypeError("web search artifact reference factory is invalid")
        if (
            isinstance(maximum_artifacts, bool)
            or not isinstance(maximum_artifacts, int)
            or not 1 <= maximum_artifacts <= 1024
            or isinstance(maximum_total_bytes, bool)
            or not isinstance(maximum_total_bytes, int)
            or not 1 <= maximum_total_bytes <= 8 * 1024 * 1024
        ):
            raise ValueError("web search artifact store limit is invalid")
        self._ref_factory = ref_factory or (lambda: f"TF-search_{secrets.token_hex(12)}")
        self._maximum_artifacts = maximum_artifacts
        self._maximum_total_bytes = maximum_total_bytes
        self._records: dict[str, WebSearchArtifact] = {}
        self._record_bytes: dict[str, int] = {}
        self._total_bytes = 0
        self._lock = RLock()

    @staticmethod
    def _size(artifact: WebSearchArtifact) -> int:
        return len(json.dumps(
            artifact.public_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8"))

    def store(self, artifact: object) -> str:
        if not isinstance(artifact, WebSearchArtifact):
            raise TypeError("web search artifact is invalid")
        reference = self._ref_factory()
        if not isinstance(reference, str) or not ARTIFACT_REF_RE.fullmatch(reference):
            raise ValueError("web search artifact reference is invalid")
        size = self._size(artifact)
        with self._lock:
            if (
                len(self._records) >= self._maximum_artifacts
                or self._total_bytes + size > self._maximum_total_bytes
                or reference in self._records
            ):
                raise ValueError("web search artifact store capacity is exhausted")
            self._records[reference] = artifact
            self._record_bytes[reference] = size
            self._total_bytes += size
        return reference

    def get(self, reference: object) -> WebSearchArtifact | None:
        if not isinstance(reference, str) or not ARTIFACT_REF_RE.fullmatch(reference):
            return None
        with self._lock:
            return self._records.get(reference)


__all__ = [
    "MAX_WEB_SEARCH_RESULTS",
    "MAX_WEB_SEARCH_TITLE_CHARACTERS",
    "MAX_SESSION_WEB_SEARCH_ARTIFACTS",
    "MAX_SESSION_WEB_SEARCH_ARTIFACT_BYTES",
    "SessionWebSearchArtifactStore",
    "WEB_SEARCH_ARTIFACT_SCHEMA_VERSION",
    "WebSearchArtifact",
    "WebSearchCandidate",
]
