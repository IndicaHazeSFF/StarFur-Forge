"""Shared validation for reviewable assistant-memory proposal records."""

from __future__ import annotations

from pipeline.db import normalize_memory_type, normalize_retention
from pipeline.domains import normalize_domain


PROPOSAL_FIELDS = {
    "store", "subject", "memory_type", "summary", "details",
    "importance", "confidence", "retention", "domain", "source",
}


def validate_memory_proposal(value, default_domain=None):
    """Validate a complete, engine-owned assistant-memory proposal record."""
    if not isinstance(value, dict) or set(value) - PROPOSAL_FIELDS:
        raise ValueError("Memory proposal must be an object with known fields.")
    required = {
        "store", "subject", "memory_type", "summary", "importance",
        "confidence", "retention", "domain", "source",
    }
    if not required.issubset(value):
        raise ValueError("Memory proposal is missing required fields.")
    if not isinstance(value["store"], bool) or not isinstance(value["subject"], str) or not value["subject"].strip():
        raise ValueError("Invalid memory proposal subject/store.")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ValueError("Invalid memory proposal summary.")
    if "details" in value and value["details"] is not None and not isinstance(value["details"], str):
        raise ValueError("Invalid memory proposal details.")
    normalize_memory_type(value["memory_type"])
    normalize_retention(value["retention"])
    domain = normalize_domain(value["domain"])
    if isinstance(value["importance"], bool) or isinstance(value["confidence"], bool):
        raise ValueError("Memory proposal scores must be JSON numbers.")
    if not isinstance(value["importance"], (int, float)) or not isinstance(value["confidence"], (int, float)):
        raise ValueError("Memory proposal scores must be JSON numbers.")
    if not 0 <= value["importance"] <= 1 or not 0 <= value["confidence"] <= 1:
        raise ValueError("Memory proposal scores must be between 0 and 1.")
    return {
        **value,
        "domain": domain,
        "details": value.get("details"),
        "source": str(value["source"]),
    }


__all__ = ["PROPOSAL_FIELDS", "validate_memory_proposal"]
