"""Pure presentation safeguards for explicit fictional roleplay.

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
    r")(?:\s+level)?\s*:\s*\d{1,3}\s*/\s*100\b",
    re.IGNORECASE,
)
_DIAGNOSTIC_TERMS = ("meter", "score", "numeric", "numerical", "diagnostic", "internal value")


def requests_roleplay_meter_diagnostics(user_text: object) -> bool:
    """Return true only for an explicit request to reveal internal meter data."""
    if not isinstance(user_text, str):
        return False
    normalized = " ".join(user_text.casefold().split())
    return any(term in normalized for term in _DIAGNOSTIC_TERMS)


def sanitize_roleplay_memories(
    memories: Iterable[Mapping[str, object]], *, user_text: object,
) -> list[dict[str, object]]:
    """Copy memory records while hiding relationship-meter scores by default.

    Only ``relationship_context`` records are eligible for redaction.  The
    selected record IDs and all non-prompt consumers retain the originals.
    """
    if requests_roleplay_meter_diagnostics(user_text):
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


__all__ = ["requests_roleplay_meter_diagnostics", "sanitize_roleplay_memories"]
