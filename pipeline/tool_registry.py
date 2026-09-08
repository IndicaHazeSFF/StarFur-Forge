"""Core-owned declarative tool metadata with no execution authority.

This is the first Stage F boundary.  It intentionally describes tools without
constructing adapters, checking permissions, calling providers, or touching
the filesystem/network/process layer.  A later permission controller and
separate executor must both approve a descriptor before a tool can run.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable


TOOL_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
TOOL_ACCESS_MODES = frozenset({"read_only", "mutating"})
MAX_REGISTERED_TOOLS = 64
MAX_TOOL_ID_CHARACTERS = 80
MAX_TOOL_TITLE_CHARACTERS = 120
MAX_TOOL_SUMMARY_CHARACTERS = 600


@dataclass(frozen=True)
class ToolDescriptor:
    """One immutable Core-defined tool contract, not a callable tool."""

    tool_id: str
    title: str
    summary: str
    access_mode: str
    permission_scope: str
    requires_confirmation: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.tool_id, str)
            or len(self.tool_id) > MAX_TOOL_ID_CHARACTERS
            or not TOOL_ID_RE.fullmatch(self.tool_id)
        ):
            raise ValueError("tool identifier is invalid")
        if (
            not isinstance(self.title, str)
            or not self.title.strip()
            or len(self.title) > MAX_TOOL_TITLE_CHARACTERS
        ):
            raise ValueError("tool title is invalid")
        if (
            not isinstance(self.summary, str)
            or not self.summary.strip()
            or len(self.summary) > MAX_TOOL_SUMMARY_CHARACTERS
        ):
            raise ValueError("tool summary is invalid")
        if self.access_mode not in TOOL_ACCESS_MODES:
            raise ValueError("tool access mode is invalid")
        if not isinstance(self.permission_scope, str) or not TOOL_ID_RE.fullmatch(self.permission_scope):
            raise ValueError("tool permission scope is invalid")
        if not isinstance(self.requires_confirmation, bool):
            raise TypeError("tool confirmation requirement is invalid")
        if self.access_mode == "mutating" and not self.requires_confirmation:
            raise ValueError("mutating tools require confirmation")

    def public_dict(self) -> dict[str, object]:
        """Return bounded description metadata, never an executor or grant."""
        return asdict(self)


@dataclass(frozen=True)
class ToolRegistry:
    """Immutable stable lookup for Core-owned tool descriptions only."""

    descriptors: tuple[ToolDescriptor, ...] = ()

    def __init__(self, descriptors: Iterable[ToolDescriptor] = ()) -> None:
        ordered = tuple(descriptors)
        if not all(isinstance(item, ToolDescriptor) for item in ordered):
            raise TypeError("tool registry entries are invalid")
        if len(ordered) > MAX_REGISTERED_TOOLS:
            raise ValueError("tool registry limit exceeded")
        tool_ids = tuple(item.tool_id for item in ordered)
        if len(set(tool_ids)) != len(tool_ids):
            raise ValueError("tool registry identifiers must be unique")
        object.__setattr__(self, "descriptors", tuple(sorted(ordered, key=lambda item: item.tool_id)))

    def get(self, tool_id: object) -> ToolDescriptor | None:
        if not isinstance(tool_id, str):
            return None
        return next((item for item in self.descriptors if item.tool_id == tool_id), None)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "tools": [item.public_dict() for item in self.descriptors],
        }


def build_core_tool_registry() -> ToolRegistry:
    """Describe the first future tool without enabling or executing it."""
    return ToolRegistry((ToolDescriptor(
        "sandbox.run",
        "Run isolated learning exercise",
        "Submit bounded files and declarative task metadata to an isolated sandbox backend.",
        "mutating",
        "sandbox.execute",
        requires_confirmation=True,
    ),))


__all__ = [
    "MAX_REGISTERED_TOOLS", "MAX_TOOL_ID_CHARACTERS", "MAX_TOOL_SUMMARY_CHARACTERS",
    "MAX_TOOL_TITLE_CHARACTERS", "TOOL_ACCESS_MODES", "TOOL_ID_RE", "ToolDescriptor",
    "ToolRegistry", "build_core_tool_registry",
]
