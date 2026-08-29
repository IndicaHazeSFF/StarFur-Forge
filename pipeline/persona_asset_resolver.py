"""Core-owned resolution of declared built-in persona presentation assets.

This is deliberately narrower than a package installer or static-file server.
It resolves a previously validated manifest slot below one explicitly trusted
installed package root. Callers still decide which fixed public route, if any,
may serve the resulting file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pipeline.persona_assets import PersonaAssetManifest


@dataclass(frozen=True)
class InstalledPersonaAssetPackage:
    """One trusted Core-installed package root and its immutable manifest."""

    manifest: PersonaAssetManifest
    root: Path

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, PersonaAssetManifest):
            raise TypeError("manifest must be a PersonaAssetManifest instance.")
        if not isinstance(self.root, Path):
            raise TypeError("root must be a Path instance.")
        object.__setattr__(self, "root", self.root.resolve())

    @property
    def persona_id(self) -> str:
        return self.manifest.persona_id

    def resolve(self, visual_state: str) -> Path | None:
        """Resolve one declared slot only when it remains inside this root."""
        reference = self.manifest.reference_for(visual_state)
        if reference is None:
            return None
        candidate = (self.root / Path(*reference.split("/"))).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("persona asset reference escaped its installed package root.")
        return candidate if candidate.is_file() else None


class PersonaAssetResolver:
    """Exact persona/visual-slot lookup for trusted installed packages only."""

    def __init__(self, packages: Iterable[InstalledPersonaAssetPackage] = ()) -> None:
        indexed: dict[str, InstalledPersonaAssetPackage] = {}
        for package in packages:
            if not isinstance(package, InstalledPersonaAssetPackage):
                raise TypeError("packages must contain InstalledPersonaAssetPackage values.")
            if package.persona_id in indexed:
                raise ValueError(f"persona asset package already registered: {package.persona_id}.")
            indexed[package.persona_id] = package
        self._packages = indexed

    def resolve(self, persona_id: str, visual_state: str) -> Path | None:
        if not isinstance(persona_id, str):
            raise TypeError("persona_id must be a string.")
        package = self._packages.get(persona_id.strip().casefold())
        return None if package is None else package.resolve(visual_state)

    def resolve_with_fallback(
        self,
        persona_id: str,
        visual_state: str,
        *,
        fallback_visual_state: str = "idle",
    ) -> Path | None:
        """Resolve an exact slot, then one Core-selected declared fallback.

        A package need not ship art for every presentation state.  Missing or
        unavailable state art may therefore use its declared ``idle`` slot.
        This returns no package metadata and does not make fallback selection
        a public routing or asset-discovery surface.
        """
        exact = self.resolve(persona_id, visual_state)
        if exact is not None or visual_state == fallback_visual_state:
            return exact
        return self.resolve(persona_id, fallback_visual_state)


__all__ = ["InstalledPersonaAssetPackage", "PersonaAssetResolver"]
