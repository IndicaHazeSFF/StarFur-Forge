"""Provider-free classification for factual requests that need research.

This module deliberately does not decide whether an answer is true or whether
retrieved memory supports it. It identifies a small set of requests that Core
must not send through ordinary, unconstrained chat: explicit research requests,
freshness-sensitive questions, and high-stakes factual questions. The result is
a policy signal only; it grants no tool, network, provider, or publication
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


FACTUAL_RESEARCH_POLICY_SCHEMA_VERSION = 1
MAX_FACTUAL_REQUEST_CHARACTERS = 4096

_DISPOSITIONS = {
    "ordinary_chat_unclassified",
    "fictional_generation_allowed",
    "research_required",
}
_REASONS = {
    "no_mandatory_research_signal",
    "fictional_context",
    "explicit_research_request",
    "freshness_sensitive_request",
    "high_stakes_request",
}

_EXPLICIT_RESEARCH_RE = re.compile(
    r"(?:^|\b)(?:"
    r"(?:please\s+)?(?:research|verify|fact[ -]?check)\b|"
    r"(?:look|check)\s+(?:this\s+|that\s+|it\s+)?up\b|"
    r"(?:search|browse)\s+(?:the\s+)?(?:web|internet|online)\b|"
    r"(?:find|give|show)\s+(?:me\s+)?(?:reliable\s+|current\s+)?sources\b"
    r")",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(
    r"(?:\?|^(?:who|what|when|where|why|how|which|is|are|was|were|do|does|did|"
    r"can|could|should|would|will|tell\s+me|explain)\b)",
    re.IGNORECASE,
)
_FRESHNESS_RE = re.compile(
    r"\b(?:latest|today|right\s+now|currently|up[ -]?to[ -]?date|recent\s+news|"
    r"current\s+(?:price|rate|law|regulation|rule|version|release|schedule|score|"
    r"weather|forecast|officeholder|president|prime\s+minister|ceo|status))\b",
    re.IGNORECASE,
)
_HIGH_STAKES_RE = re.compile(
    r"\b(?:dose|dosage|drug\s+interaction|medication|medical\s+advice|diagnos(?:e|is)|"
    r"symptom|is\s+it\s+legal|legal\s+advice|lawsuit|regulation|tax\s+advice|"
    r"investment\s+advice|should\s+i\s+(?:buy|sell|invest)|mortgage|retirement\s+fund)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FactualResearchContext:
    """Non-authority context labels supplied by Core."""

    roleplay_active: bool = False
    adventure_active: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.roleplay_active, bool) or not isinstance(self.adventure_active, bool):
            raise TypeError("factual research context flags must be boolean")

    @property
    def fictional(self) -> bool:
        return self.roleplay_active or self.adventure_active


@dataclass(frozen=True)
class FactualResearchDecision:
    schema_version: int
    disposition: str
    reason: str

    def __post_init__(self) -> None:
        if self.schema_version != FACTUAL_RESEARCH_POLICY_SCHEMA_VERSION:
            raise ValueError("factual research policy schema version is unsupported")
        if self.disposition not in _DISPOSITIONS:
            raise ValueError("factual research disposition is invalid")
        if self.reason not in _REASONS:
            raise ValueError("factual research reason is invalid")
        expected = {
            "ordinary_chat_unclassified": {"no_mandatory_research_signal"},
            "fictional_generation_allowed": {"fictional_context"},
            "research_required": {
                "explicit_research_request",
                "freshness_sensitive_request",
                "high_stakes_request",
            },
        }
        if self.reason not in expected[self.disposition]:
            raise ValueError("factual research decision is inconsistent")


def classify_factual_research_request(
    user_text: object,
    *,
    context: FactualResearchContext | None = None,
) -> FactualResearchDecision:
    """Classify a narrow mandatory-research boundary without calling anything."""
    if not isinstance(user_text, str):
        raise TypeError("factual research request must be text")
    text = user_text.strip()
    if not text or len(text) > MAX_FACTUAL_REQUEST_CHARACTERS or "\x00" in text:
        raise ValueError("factual research request is invalid")
    use_context = context or FactualResearchContext()
    if not isinstance(use_context, FactualResearchContext):
        raise TypeError("factual research context is invalid")

    # Explicit evidence requests always win, including during a fictional
    # session. Fictional mode permits story invention; it does not permit Core
    # to ignore a direct request to verify something.
    if _EXPLICIT_RESEARCH_RE.search(text):
        return FactualResearchDecision(
            FACTUAL_RESEARCH_POLICY_SCHEMA_VERSION,
            "research_required",
            "explicit_research_request",
        )
    if use_context.fictional:
        return FactualResearchDecision(
            FACTUAL_RESEARCH_POLICY_SCHEMA_VERSION,
            "fictional_generation_allowed",
            "fictional_context",
        )
    if _QUESTION_RE.search(text) and _HIGH_STAKES_RE.search(text):
        return FactualResearchDecision(
            FACTUAL_RESEARCH_POLICY_SCHEMA_VERSION,
            "research_required",
            "high_stakes_request",
        )
    if _QUESTION_RE.search(text) and _FRESHNESS_RE.search(text):
        return FactualResearchDecision(
            FACTUAL_RESEARCH_POLICY_SCHEMA_VERSION,
            "research_required",
            "freshness_sensitive_request",
        )
    return FactualResearchDecision(
        FACTUAL_RESEARCH_POLICY_SCHEMA_VERSION,
        "ordinary_chat_unclassified",
        "no_mandatory_research_signal",
    )


__all__ = [
    "FACTUAL_RESEARCH_POLICY_SCHEMA_VERSION",
    "MAX_FACTUAL_REQUEST_CHARACTERS",
    "FactualResearchContext",
    "FactualResearchDecision",
    "classify_factual_research_request",
]
