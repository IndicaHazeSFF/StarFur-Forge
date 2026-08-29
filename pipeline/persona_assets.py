"""Pure declarative asset references for a persona package.

This is intentionally a contract only.  It validates stable presentation slot
names and safe package-relative asset references, but never opens files,
extracts archives, serves HTTP, or chooses a persona's activity.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Mapping


PERSONA_ASSET_MANIFEST_VERSION = 1
PRESENTATION_VISUAL_STATES = frozenset({
    "idle", "resting", "reading", "working", "waiting", "chatting",
    "adventuring", "thinking", "reviewing", "planning", "roleplaying",
    "provider_error", "offline",
})
_PERSONA_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ALLOWED_EXTENSIONS = frozenset({".png", ".webp"})


def _validate_persona_id(value: object) -> str:
    if not isinstance(value, str) or not _PERSONA_ID_PATTERN.fullmatch(value):
        raise ValueError("persona asset manifest persona_id is invalid")
    return value


def _validate_package_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or "\\" in value:
        raise ValueError("persona asset reference must be a bounded POSIX package-relative path")
    parts = value.split("/")
    if any(not _PATH_SEGMENT_PATTERN.fullmatch(part) for part in parts):
        raise ValueError("persona asset reference contains an unsafe path segment")
    extension = "." + parts[-1].rsplit(".", 1)[-1].casefold() if "." in parts[-1] else ""
    if extension not in _ALLOWED_EXTENSIONS:
        raise ValueError("persona asset reference must use a supported image extension")
    return value


@dataclass(frozen=True)
class PersonaAssetManifest:
    """Validated named visual assets for exactly one declarative persona.

    The mapping key is the generic visual state produced by
    ``ResidentPresentationPlan``.  A missing state is normal and callers must
    use their own generic fallback rather than guessing a path.
    """

    persona_id: str
    assets: Mapping[str, str]
    schema_version: int = PERSONA_ASSET_MANIFEST_VERSION

    def __post_init__(self) -> None:
        persona_id = _validate_persona_id(self.persona_id)
        if self.schema_version != PERSONA_ASSET_MANIFEST_VERSION:
            raise ValueError("persona asset manifest schema_version is unsupported")
        if not isinstance(self.assets, Mapping):
            raise TypeError("persona asset manifest assets must be a mapping")
        normalized: dict[str, str] = {}
        for visual_state, reference in self.assets.items():
            if not isinstance(visual_state, str) or visual_state not in PRESENTATION_VISUAL_STATES:
                raise ValueError("persona asset manifest visual state is invalid")
            if visual_state in normalized:
                raise ValueError("persona asset manifest repeats a visual state")
            normalized[visual_state] = _validate_package_relative_path(reference)
        object.__setattr__(self, "persona_id", persona_id)
        object.__setattr__(self, "assets", MappingProxyType(dict(sorted(normalized.items()))))

    def reference_for(self, visual_state: str) -> str | None:
        """Return only an already-validated package-relative reference."""
        if not isinstance(visual_state, str) or visual_state not in PRESENTATION_VISUAL_STATES:
            raise ValueError("persona asset visual state is invalid")
        return self.assets.get(visual_state)

    def public_dict(self) -> dict[str, object]:
        """Bounded metadata for later package inspection, never resolved paths."""
        return {
            "schema_version": self.schema_version,
            "persona_id": self.persona_id,
            "visual_states": list(self.assets),
            "storage": "package_declarative",
        }


# Compatibility declaration for the one pre-package human-authored resident
# sprite.  Core may use it only when an older stock configuration has not yet
# declared Murr's matching slot.  It is still a normal validated manifest,
# never a raw route-to-path fallback.
BUILTIN_MURR_ASSET_MANIFEST = PersonaAssetManifest(
    "murr", {"idle": "Assets/Murr/Murr_S_Idle.png"},
)


__all__ = [
    "PERSONA_ASSET_MANIFEST_VERSION", "PRESENTATION_VISUAL_STATES",
    "BUILTIN_MURR_ASSET_MANIFEST", "PersonaAssetManifest",
]
