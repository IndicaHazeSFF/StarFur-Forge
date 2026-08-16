"""Deterministic structural prechunking for bounded external documents.

This module is deliberately model-free and side-effect free.  It identifies
stable Markdown/story sections before the existing paragraph-aware chunker is
used, allowing callers to retain semantic boundaries without treating document
text as instructions.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from pipeline.chunker import chunk_scene, extract_frontmatter


ASSISTANT_NOTE_PROFILE = "assistant_note"
TECHNICAL_DOCUMENT_PROFILE = "technical_document"
ADVENTURE_STATE_PROFILE = "adventure_state"
MANUSCRIPT_PROFILE = "manuscript"
AUTO_DOCUMENT_PROFILE = "auto"
DOCUMENT_PROFILES = frozenset({
    ASSISTANT_NOTE_PROFILE,
    TECHNICAL_DOCUMENT_PROFILE,
    ADVENTURE_STATE_PROFILE,
    MANUSCRIPT_PROFILE,
})

_PROFILE_DEFAULT_MAX_CHARS = {
    ASSISTANT_NOTE_PROFILE: 1200,
    TECHNICAL_DOCUMENT_PROFILE: 1800,
    ADVENTURE_STATE_PROFILE: 3000,
    MANUSCRIPT_PROFILE: 1200,
}
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_ADVENTURE_MARKER_RE = re.compile(
    r"^\s*(?:story\s+state|current\s+scene|characters?|relationships?|"
    r"unresolved\s+(?:threads?|hooks?)|inventory|world\s+state|story\s+is\s+here)\s*:?\s*$",
    re.IGNORECASE,
)


class DocumentPrechunkError(ValueError):
    """Raised when a requested structural prechunking profile is invalid."""


@dataclass(frozen=True)
class StructuralSection:
    """One stable heading/marker-delimited document section."""

    index: int
    heading: str | None
    text: str


def normalize_document_profile(value: object, *, allow_auto: bool = False) -> str:
    """Validate one public document profile without inferring permissions."""
    if not isinstance(value, str):
        raise DocumentPrechunkError("Document profile must be a string.")
    profile = value.strip().casefold().replace("-", "_")
    allowed = set(DOCUMENT_PROFILES)
    if allow_auto:
        allowed.add(AUTO_DOCUMENT_PROFILE)
    if profile not in allowed:
        choices = ", ".join(sorted(allowed))
        raise DocumentPrechunkError(f"Unknown document profile; expected one of: {choices}.")
    return profile


def infer_document_profile(text: str) -> str:
    """Conservatively identify adventure-state documents from explicit labels."""
    markers = [line.strip().rstrip(":").casefold() for line in text.splitlines()
               if _ADVENTURE_MARKER_RE.fullmatch(line)]
    # ``STORY IS HERE`` is an intentionally explicit continuation marker; one
    # occurrence is enough to opt into adventure structure. Other generic
    # labels need corroboration so a normal technical document is unchanged.
    if "story is here" in markers or len(markers) >= 2:
        return ADVENTURE_STATE_PROFILE
    return ASSISTANT_NOTE_PROFILE


def resolve_document_profile(value: object, text: str) -> str:
    """Resolve ``auto`` using only source text structure, never model output."""
    profile = normalize_document_profile(value, allow_auto=True)
    return infer_document_profile(text) if profile == AUTO_DOCUMENT_PROFILE else profile


def profile_default_max_chars(profile: str) -> int:
    """Return the bounded default chunk size for a validated profile."""
    return _PROFILE_DEFAULT_MAX_CHARS[normalize_document_profile(profile)]


def _structural_sections(text: str, *, include_adventure_markers: bool) -> tuple[StructuralSection, ...]:
    sections: list[StructuralSection] = []
    current: list[str] = []
    current_heading: str | None = None

    def flush() -> None:
        nonlocal current
        content = "\n".join(current).strip()
        if content:
            sections.append(StructuralSection(len(sections), current_heading, content))
        current = []

    for line in text.splitlines():
        heading = _HEADING_RE.fullmatch(line)
        marker = include_adventure_markers and _ADVENTURE_MARKER_RE.fullmatch(line)
        if heading or marker:
            flush()
            current_heading = (heading.group(2).strip() if heading else line.strip().rstrip(":"))
            current.append(line)
        else:
            current.append(line)
    flush()
    return tuple(sections)


def prechunk_document_text(
    text: str,
    *,
    profile: str = ASSISTANT_NOTE_PROFILE,
    max_chars: int | None = None,
    overlap_paragraphs: int = 1,
) -> tuple[Mapping[str, object], ...]:
    """Return existing-chunker-compatible chunks with profile-aware boundaries.

    ``assistant_note`` and ``manuscript`` preserve the legacy scene behavior.
    Technical and adventure profiles first partition headings (and, for
    adventures, explicit state markers), then use the existing paragraph and
    sentence safety logic within each partition.
    """
    selected_profile = normalize_document_profile(profile)
    if max_chars is None:
        max_chars = profile_default_max_chars(selected_profile)
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
        raise ValueError("max_chars must be a positive integer.")
    if isinstance(overlap_paragraphs, bool) or not isinstance(overlap_paragraphs, int) or overlap_paragraphs < 0:
        raise ValueError("overlap_paragraphs must be a non-negative integer.")

    frontmatter, body = extract_frontmatter(text)
    if selected_profile in {ASSISTANT_NOTE_PROFILE, MANUSCRIPT_PROFILE}:
        from pipeline.chunker import chunk_text
        return tuple(chunk_text(text, max_chars=max_chars, overlap_paragraphs=overlap_paragraphs))

    sections = _structural_sections(
        body,
        include_adventure_markers=selected_profile == ADVENTURE_STATE_PROFILE,
    )
    chunks: list[Mapping[str, object]] = []
    for section in sections:
        section_chunks = chunk_scene(
            section.text,
            section.index,
            max_chars=max_chars,
            overlap_paragraphs=overlap_paragraphs,
        )
        for chunk in section_chunks:
            # A marker-only section still receives a stable, useful heading.
            if not chunk.get("heading") and section.heading:
                chunk["heading"] = section.heading
            chunk["frontmatter"] = frontmatter
            chunks.append(chunk)
    return tuple(chunks)


__all__ = [
    "ADVENTURE_STATE_PROFILE",
    "ASSISTANT_NOTE_PROFILE",
    "AUTO_DOCUMENT_PROFILE",
    "DOCUMENT_PROFILES",
    "DocumentPrechunkError",
    "MANUSCRIPT_PROFILE",
    "StructuralSection",
    "TECHNICAL_DOCUMENT_PROFILE",
    "infer_document_profile",
    "normalize_document_profile",
    "prechunk_document_text",
    "profile_default_max_chars",
    "resolve_document_profile",
]
