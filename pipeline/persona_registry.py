"""Declarative, presentation-only persona package registry.

This is the first multi-persona boundary. A package contains static persona
presentation and its immutable initial state, while shared Core memory,
providers, tools, policy, and permissions remain outside the package. The
registry deliberately does not select a persona for a running session yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from pipeline.persona import Persona, load_persona, load_persona_state
from pipeline.persona_state import PersonaState
from pipeline.persona_visibility import SharedMemoryVisibilityPolicy
from pipeline.persona_assets import PersonaAssetManifest


@dataclass(frozen=True)
class PersonaPackage:
    """One validated declarative persona, without executable behavior code."""

    persona_id: str
    display_name: str
    persona: Persona
    initial_state: PersonaState
    shared_memory_visibility_policy: SharedMemoryVisibilityPolicy | None = None
    asset_manifest: PersonaAssetManifest | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.persona, Persona):
            raise TypeError("persona must be a Persona instance.")
        if not isinstance(self.initial_state, PersonaState):
            raise TypeError("initial_state must be a PersonaState instance.")
        if self.persona_id != self.initial_state.persona_id:
            raise ValueError("persona_id must match initial_state.persona_id.")
        if self.display_name != self.initial_state.display_name:
            raise ValueError("display_name must match initial_state.display_name.")
        if self.persona.render_prompt() != self.initial_state.static_identity:
            raise ValueError("persona prompt must match initial_state.static_identity.")
        policy = self.shared_memory_visibility_policy
        if policy is None:
            policy = SharedMemoryVisibilityPolicy(self.persona_id)
            object.__setattr__(self, "shared_memory_visibility_policy", policy)
        if not isinstance(policy, SharedMemoryVisibilityPolicy):
            raise TypeError("shared_memory_visibility_policy must be a SharedMemoryVisibilityPolicy instance.")
        if policy.persona_id != self.persona_id:
            raise ValueError("shared_memory_visibility_policy persona_id must match persona_id.")
        manifest = self.asset_manifest
        if manifest is not None and not isinstance(manifest, PersonaAssetManifest):
            raise TypeError("asset_manifest must be a PersonaAssetManifest instance or None.")
        if manifest is not None and manifest.persona_id != self.persona_id:
            raise ValueError("asset_manifest persona_id must match persona_id.")

    def public_dict(self) -> dict[str, object]:
        """Expose only declarative display metadata, never the full prompt."""
        public = {
            "persona_id": self.persona_id,
            "display_name": self.display_name,
        }
        if self.asset_manifest is not None:
            public["asset_visual_states"] = list(self.asset_manifest.assets)
        return public


def load_persona_package(
    path: Path | str | None,
    *,
    persona_id: str | None = None,
    display_name: str | None = None,
    minimum_shared_memory_confidence: float = 0.0,
    allowed_memory_scopes: tuple[str, ...] | list[str] | None = None,
    asset_slots: Mapping[str, str] | None = None,
) -> PersonaPackage:
    """Load one safe fallback-capable declarative package from a Markdown file."""
    state = load_persona_state(path, persona_id=persona_id, display_name=display_name)
    persona = load_persona(path)
    asset_manifest = None if asset_slots is None else PersonaAssetManifest(state.persona_id, asset_slots)
    return PersonaPackage(
        state.persona_id,
        state.display_name,
        persona,
        state,
        SharedMemoryVisibilityPolicy(
            state.persona_id,
            minimum_shared_memory_confidence,
            allowed_memory_scopes,
        ),
        asset_manifest,
    )


def load_persona_packages(
    default_path: Path | str | None,
    specs: Iterable[Mapping[str, object]] | None = None,
) -> "PersonaRegistry":
    """Build a registry from bounded Core-provided package specifications.

    Callers resolve relative paths before this boundary. Omitting specs preserves
    legacy behavior by registering exactly the configured default persona.
    """
    if specs is None:
        return PersonaRegistry((load_persona_package(default_path),))
    packages: list[PersonaPackage] = []
    for spec in specs:
        if not isinstance(spec, Mapping):
            raise TypeError("persona_packages entries must be mappings.")
        unknown = set(spec) - {
            "persona_id",
            "display_name",
            "persona_path",
            "minimum_shared_memory_confidence",
            "allowed_memory_scopes",
            "asset_slots",
        }
        if unknown:
            raise ValueError(f"Unknown persona package field(s): {sorted(unknown)}")
        path = spec.get("persona_path")
        if not isinstance(path, (str, Path)):
            raise TypeError("persona_path must be a string or Path.")
        persona_id = spec.get("persona_id")
        display_name = spec.get("display_name")
        minimum_shared_memory_confidence = spec.get("minimum_shared_memory_confidence", 0.0)
        allowed_memory_scopes = spec.get("allowed_memory_scopes")
        asset_slots = spec.get("asset_slots")
        if persona_id is not None and not isinstance(persona_id, str):
            raise TypeError("persona_id must be a string when provided.")
        if display_name is not None and not isinstance(display_name, str):
            raise TypeError("display_name must be a string when provided.")
        if asset_slots is not None and not isinstance(asset_slots, Mapping):
            raise TypeError("asset_slots must be a mapping when provided.")
        packages.append(
            load_persona_package(
                path,
                persona_id=persona_id,
                display_name=display_name,
                minimum_shared_memory_confidence=minimum_shared_memory_confidence,
                allowed_memory_scopes=allowed_memory_scopes,
                asset_slots=asset_slots,
            )
        )
    if not packages:
        raise ValueError("persona_packages must not be empty when configured.")
    return PersonaRegistry(packages)


class PersonaRegistry:
    """Immutable-package lookup; it owns no providers, Core memory, or tools."""

    def __init__(self, packages: Iterable[PersonaPackage] = ()):
        indexed: dict[str, PersonaPackage] = {}
        for package in packages:
            self._register(package, indexed)
        self._packages = indexed

    @staticmethod
    def _register(package: PersonaPackage, packages: dict[str, PersonaPackage]) -> None:
        if not isinstance(package, PersonaPackage):
            raise TypeError("package must be a PersonaPackage instance.")
        if package.persona_id in packages:
            raise ValueError(f"Persona package already registered: {package.persona_id}.")
        packages[package.persona_id] = package

    def get(self, persona_id: str) -> PersonaPackage | None:
        if not isinstance(persona_id, str):
            raise TypeError("persona_id must be a string.")
        return self._packages.get(persona_id.strip().casefold())

    def packages(self) -> tuple[PersonaPackage, ...]:
        """Return stable metadata/package order without mutating registry state."""
        return tuple(self._packages[key] for key in sorted(self._packages))

    def public_list(self) -> tuple[dict[str, object], ...]:
        return tuple(package.public_dict() for package in self.packages())


__all__ = ["PersonaPackage", "PersonaRegistry", "load_persona_package", "load_persona_packages"]
