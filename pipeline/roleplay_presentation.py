"""Pure presentation safeguards for fictional roleplay and adventures.

This boundary intentionally changes only what reaches a narrator.  It never
changes stored memories, retrieval order, diagnostics, or whether a user may
explicitly ask to see internal story meters.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping


_METER_VALUE = re.compile(
    r"\b("
    r"trust|comfort|attraction|affection|familiarity|suspicion|resentment|"
    r"concern|loyalty|rapport"
    r")(?:\s+level)?\s*(?::|is|at)?\s*\d{1,3}\s*/\s*100\b",
    re.IGNORECASE,
)
_DIAGNOSTIC_TERMS = ("meter", "score", "numeric", "numerical", "diagnostic", "internal value")


def requests_fictional_meter_diagnostics(user_text: object) -> bool:
    """Return true only for an explicit request to reveal fictional meter data."""
    if not isinstance(user_text, str):
        return False
    normalized = " ".join(user_text.casefold().split())
    return any(term in normalized for term in _DIAGNOSTIC_TERMS)


def sanitize_fictional_relationship_memories(
    memories: Iterable[Mapping[str, object]], *, user_text: object,
) -> list[dict[str, object]]:
    """Copy memory records while hiding fictional relationship-meter scores.

    Only ``relationship_context`` records are eligible for redaction.  The
    selected record IDs and all non-prompt consumers retain the originals.
    """
    if requests_fictional_meter_diagnostics(user_text):
        return [dict(memory) for memory in memories]
    sanitized: list[dict[str, object]] = []
    for memory in memories:
        copied = dict(memory)
        if str(copied.get("memory_type") or "") == "relationship_context":
            for field in ("summary", "details"):
                value = copied.get(field)
                if isinstance(value, str):
                    copied[field] = _METER_VALUE.sub(r"\1: qualitative internal state", value)
        sanitized.append(copied)
    return sanitized


# Compatibility aliases retain the pre-adventure public helper surface.
requests_roleplay_meter_diagnostics = requests_fictional_meter_diagnostics
sanitize_roleplay_memories = sanitize_fictional_relationship_memories


__all__ = [
    "requests_fictional_meter_diagnostics", "requests_roleplay_meter_diagnostics",
    "sanitize_fictional_relationship_memories", "sanitize_roleplay_memories",
]
