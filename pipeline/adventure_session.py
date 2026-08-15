"""Session-ephemeral mounted-adventure boundary for future CYOA workspaces.

This state deliberately knows only public registry metadata. It is not an
adventure database, narration history, event log, or replay engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_registry import AdventureRecord


@dataclass(frozen=True)
class AdventureSessionState:
    """One conversation's optional read-only mounted workspace metadata."""

    record: AdventureRecord | None = None

    def __post_init__(self) -> None:
        if self.record is not None and not isinstance(self.record, AdventureRecord):
            raise TypeError("mounted adventure record must be an AdventureRecord or None")

    @classmethod
    def unmounted(cls) -> "AdventureSessionState":
        return cls()

    @property
    def active(self) -> bool:
        return self.record is not None

    def mount(self, record: AdventureRecord) -> "AdventureSessionState":
        return type(self)(record=record)

    def unmount(self) -> "AdventureSessionState":
        return type(self).unmounted()

    def public_dict(self) -> dict[str, object]:
        if self.record is None:
            return {"mounted": False, "storage": "session_ephemeral"}
        return {
            "mounted": True,
            "adventure_id": self.record.adventure_id,
            "title": self.record.title,
            "status": self.record.status,
            "storage": "session_ephemeral",
        }

    def context_text(self) -> str:
        """Render only Core-owned workspace metadata, never invented story state."""
        if self.record is None:
            return ""
        return (
            "MOUNTED ADVENTURE WORKSPACE (core-provided):\n"
            f"Title: {self.record.title}\n"
            f"ID: {self.record.adventure_id}\n"
            "This workspace currently has manifest metadata only. It has no authoritative story events, "
            "characters, relationships, replay spine, database, semantic index, or hidden narrative history. "
            "Do not invent prior adventure events or claim that a story has resumed. Keep ordinary assistant "
            "memory and real-world claims separate. Follow explicit Core commands and engine policy normally.\n"
            "END MOUNTED ADVENTURE WORKSPACE"
        )


__all__ = ["AdventureSessionState"]
