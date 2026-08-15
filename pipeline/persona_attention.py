"""Deterministic, presentation-only selection of persona interests.

This is deliberately narrower than a learning system.  Callers supply an
already-reviewed ``PersonaDevelopmentState``; this module performs no I/O,
does not change that state, and never selects a skill as evidence of expertise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from pipeline.persona_development import PersonaDevelopmentState


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#-]*", re.IGNORECASE)
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "about", "can", "do", "for", "how", "i",
    "in", "is", "it", "me", "my", "of", "on", "or", "the", "to", "what",
    "when", "where", "why", "with", "you", "your",
})
DEFAULT_ATTENTION_LIMIT = 2


def _tokens(value: str) -> frozenset[str]:
    return frozenset(
        token.casefold() for token in _TOKEN_RE.findall(value)
        if token.casefold() not in _STOPWORDS
    )


@dataclass(frozen=True)
class PersonaAttentionItem:
    """One relevant interest, safe to present as a style-only cue."""

    concept: str
    effective_confidence: float
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PersonaAttention:
    """A bounded, query-specific attention snapshot for one persona."""

    persona_id: str
    items: tuple[PersonaAttentionItem, ...] = ()


def select_persona_attention(
    query: str,
    state: PersonaDevelopmentState,
    *,
    as_of: datetime,
    limit: int = DEFAULT_ATTENTION_LIMIT,
) -> PersonaAttention:
    """Return only interests with direct, deterministic query overlap.

    Matching an interest allows optional examples or follow-up questions.  It
    never grants knowledge, tool access, or permission to redirect the user.
    """
    if not isinstance(query, str):
        raise TypeError("query must be a string.")
    if not isinstance(state, PersonaDevelopmentState):
        raise TypeError("state must be a PersonaDevelopmentState instance.")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer.")

    query_tokens = _tokens(query)
    if not query_tokens:
        return PersonaAttention(state.persona_id)

    selected: list[PersonaAttentionItem] = []
    for interest in state.interests:
        concept_tokens = _tokens(interest.concept)
        overlap = tuple(sorted(query_tokens.intersection(concept_tokens)))
        if not overlap or not concept_tokens:
            continue
        effective = interest.confidence_at(as_of)
        if effective <= 0.0:
            continue
        coverage = len(overlap) / len(concept_tokens)
        selected.append(PersonaAttentionItem(
            concept=interest.concept,
            effective_confidence=effective,
            score=effective * coverage,
            reasons=(
                "matched interest token(s): " + ", ".join(overlap),
                f"effective interest confidence: {effective:.3f}",
            ),
        ))

    selected.sort(key=lambda item: (-item.score, item.concept.casefold()))
    return PersonaAttention(state.persona_id, tuple(selected[:limit]))


__all__ = [
    "DEFAULT_ATTENTION_LIMIT",
    "PersonaAttention",
    "PersonaAttentionItem",
    "select_persona_attention",
]
