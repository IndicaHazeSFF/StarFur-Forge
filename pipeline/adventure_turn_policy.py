"""Shared policy constants for generated adventure-turn proposals."""

from __future__ import annotations


# Ordinary generated candidates are deliberately narrower than every event Core
# can write. Structured state, relationship, knowledge, and resource changes
# each require their own typed proposal policy.
ORDINARY_ADVENTURE_EVENT_TYPES = frozenset({
    "choice", "discovery", "promise", "lie", "emotional_transition",
    "unresolved_hook", "inventory_change", "location_change",
})


__all__ = ["ORDINARY_ADVENTURE_EVENT_TYPES"]
