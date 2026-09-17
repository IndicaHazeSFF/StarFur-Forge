"""Pure bounded selection of already-quarantined public research artifacts.

Selection canonicalizes explicit artifact references before source framing. It
does not fetch, inspect a session store, choose a provider, judge independence,
verify claims, or disclose any source data.
"""

from __future__ import annotations

from pipeline.research_sources import (
    MAX_RESEARCH_SOURCES,
    ResearchSource,
    research_source_from_web_artifact,
)
from pipeline.tool_contracts import ARTIFACT_REF_RE
from pipeline.tool_web_connector import WebFetchedArtifact


def select_research_sources(items: object) -> tuple[ResearchSource, ...]:
    """Frame up to eight explicit unique artifacts in canonical ref order."""
    if not isinstance(items, (tuple, list)):
        raise TypeError("research selection must be a sequence")
    pairs = tuple(items)
    if not pairs or len(pairs) > MAX_RESEARCH_SOURCES:
        raise ValueError("research selection source count is invalid")
    normalized: list[tuple[str, WebFetchedArtifact]] = []
    for item in pairs:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("research selection item is invalid")
        artifact_ref, artifact = item
        if not isinstance(artifact_ref, str) or not ARTIFACT_REF_RE.fullmatch(artifact_ref):
            raise ValueError("research selection artifact reference is invalid")
        if not isinstance(artifact, WebFetchedArtifact):
            raise TypeError("research selection artifact is invalid")
        normalized.append((artifact_ref, artifact))
    refs = [reference for reference, _ in normalized]
    if len(set(refs)) != len(refs):
        raise ValueError("research selection artifact references must be unique")
    sources = tuple(
        research_source_from_web_artifact(reference, artifact)
        for reference, artifact in sorted(normalized, key=lambda item: item[0])
    )
    if len({source.source_id for source in sources}) != len(sources):
        raise ValueError("research selection sources must remain distinct")
    return sources


__all__ = ["select_research_sources"]
