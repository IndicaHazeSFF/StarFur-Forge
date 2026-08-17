"""Small, session-local roleplay-mode state and explicit entry detection.

This is not an adventure engine or persistence layer. It creates a Core-owned,
inspectable boundary for an explicitly requested fictional conversation.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


_TITLE_MAXIMUM = 120
_ADDRESS_PREFIX = re.compile(r"^(?:[a-z][a-z0-9_-]{0,63}\s*,\s*)", re.IGNORECASE)
_CASUAL_STARTS = (
    "let's roleplay", "lets roleplay", "start roleplay", "begin roleplay",
    "let's go on an adventure", "lets go on an adventure",
    "start an adventure", "begin an adventure",
)


def normalize_roleplay_title(value: object) -> str | None:
    """Normalize an optional label without using it as a path or identifier."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("roleplay title must be a string or None")
    title = " ".join(value.strip().split())
    if not title:
        return None
    if len(title) > _TITLE_MAXIMUM:
        raise ValueError(f"roleplay title must be at most {_TITLE_MAXIMUM} characters")
    return title


def detect_casual_roleplay_start(text: object) -> bool:
    """Recognize only a deliberately small set of explicit start phrases."""
    if not isinstance(text, str):
        return False
    normalized = " ".join(text.casefold().strip().split())
    normalized = _ADDRESS_PREFIX.sub("", normalized).rstrip(".!?")
    return normalized in _CASUAL_STARTS


@dataclass(frozen=True)
class RoleplaySessionState:
    """Bounded, non-persistent state for one assistant conversation session."""

    active: bool = False
    title: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.active, bool):
            raise TypeError("roleplay active must be boolean")
        title = normalize_roleplay_title(self.title)
        if not self.active and title is not None:
            raise ValueError("inactive roleplay state cannot have a title")
        object.__setattr__(self, "title", title)

    @classmethod
    def inactive(cls) -> "RoleplaySessionState":
        return cls()

    def begin(self, title: object = None) -> "RoleplaySessionState":
        return type(self)(active=True, title=normalize_roleplay_title(title))

    def end(self) -> "RoleplaySessionState":
        return type(self).inactive()

    def public_dict(self) -> dict[str, object]:
        return {"active": self.active, "title": self.title, "storage": "session_ephemeral"}

    def context_text(self) -> str:
        if not self.active:
            return ""
        label = self.title or "(unnamed roleplay)"
        return (
            "ACTIVE ROLEPLAY SESSION (core-provided):\n"
            "Treat the current exchange as fictional roleplay. Do not present story events as real-world user facts "
            "or prior shared reality. This early session mode has no adventure database, replay history, or hidden "
            "story state; do not invent earlier events. Keep relationship, affinity, trust, and similar meter values "
            "qualitative in normal in-character narration; never expose numeric scores unless the user explicitly "
            "asks for diagnostic or internal meter values. Follow engine policy and explicit commands normally. Core may "
            "label an explicitly eligible user-memory proposal as roleplay-scoped while this mode is active.\n"
            f"Session label: {label}\n"
            "END ACTIVE ROLEPLAY SESSION"
        )


__all__ = ["RoleplaySessionState", "detect_casual_roleplay_start", "normalize_roleplay_title"]
