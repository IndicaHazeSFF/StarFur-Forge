"""Public, bounded resource metadata for a future generated-turn resource route.

This module is deliberately a read model, not a resource-operation parser or
provider prompt.  It gives a later Core-owned resource candidate contract one
safe source of declared public resource IDs, kinds, and permitted operations
without exposing hidden definitions or treating a scenario manifest as model
authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.adventure_mutation import AdventureMutation, MUTATION_RESOURCE_CHANGE
from pipeline.adventure_resources import AdventureResourceCatalog, RESOURCE_KINDS
from pipeline.adventure_session import AdventureSessionState


MAX_RESOURCE_CANDIDATE_POLICY_ENTRIES = 8
MAX_RESOURCE_CANDIDATE_POLICY_CHARACTERS = 4_000


class AdventureTurnResourcePolicyError(ValueError):
    """Raised when an untrusted resource candidate exceeds its public policy."""


@dataclass(frozen=True)
class AdventureTurnResourcePolicyEntry:
    """One declared public resource's compact candidate-policy metadata."""

    resource_id: str
    kind: str
    permitted_operations: tuple[str, ...]
    allowed_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.resource_id, str) or not self.resource_id:
            raise ValueError("resource candidate policy identifier is invalid")
        if not isinstance(self.kind, str) or self.kind not in RESOURCE_KINDS:
            raise ValueError("resource candidate policy kind is invalid")
        if (
            not isinstance(self.permitted_operations, tuple)
            or not self.permitted_operations
            or any(not isinstance(item, str) or not item for item in self.permitted_operations)
            or tuple(sorted(set(self.permitted_operations))) != self.permitted_operations
        ):
            raise ValueError("resource candidate policy operations are invalid")
        if not isinstance(self.allowed_values, tuple) or any(
            not isinstance(item, str) or not item for item in self.allowed_values
        ):
            raise ValueError("resource candidate policy allowed values are invalid")
        if self.kind == "enum":
            if not self.allowed_values:
                raise ValueError("enum resource candidate policy values are required")
        elif self.allowed_values:
            raise ValueError("only enum resource candidate policy values are allowed")


@dataclass(frozen=True)
class AdventureTurnResourcePolicyView:
    """Safe future resource-candidate reference for one mounted workspace."""

    entries: tuple[AdventureTurnResourcePolicyEntry, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.entries, tuple)
            or len(self.entries) > MAX_RESOURCE_CANDIDATE_POLICY_ENTRIES
            or not all(isinstance(item, AdventureTurnResourcePolicyEntry) for item in self.entries)
        ):
            raise ValueError("resource candidate policy entries are invalid")
        identifiers = tuple(item.resource_id for item in self.entries)
        if len(set(identifiers)) != len(identifiers) or tuple(sorted(identifiers)) != identifiers:
            raise ValueError("resource candidate policy identifiers are invalid")
        if len(self.render()) > MAX_RESOURCE_CANDIDATE_POLICY_CHARACTERS:
            raise ValueError("resource candidate policy exceeds its bounded limit")

    @classmethod
    def from_catalog(cls, catalog: AdventureResourceCatalog) -> "AdventureTurnResourcePolicyView":
        """Project only the first bounded set of declared public resources."""
        if not isinstance(catalog, AdventureResourceCatalog):
            raise TypeError("resource candidate policy catalog is invalid")
        entries = []
        for definition in catalog.definitions:
            if definition.visibility != "public":
                continue
            entries.append(AdventureTurnResourcePolicyEntry(
                resource_id=definition.resource_id,
                kind=definition.kind,
                permitted_operations=tuple(sorted(definition.permitted_operations)),
                allowed_values=definition.allowed_values or (),
            ))
            if len(entries) == MAX_RESOURCE_CANDIDATE_POLICY_ENTRIES:
                break
        return cls(tuple(entries))

    @classmethod
    def from_session(cls, session: AdventureSessionState) -> "AdventureTurnResourcePolicyView":
        """Use only the mounted session's immutable catalog, never its values."""
        if not isinstance(session, AdventureSessionState):
            raise TypeError("resource candidate policy session is invalid")
        if session.record is None:
            raise ValueError("resource candidate policy requires a mounted workspace")
        return cls.from_catalog(session.resource_catalog)

    def render(self) -> str:
        """Render bounded public declaration metadata without current values."""
        lines = [
            "RESOURCE CANDIDATE POLICY (bounded public declarations; not authority):",
            "Do not propose omitted or hidden resources. Core validates any later operation again.",
        ]
        if not self.entries:
            lines.append("- No public resources are declared.")
        for entry in self.entries:
            line = (
                f"- {entry.resource_id} [{entry.kind}]; operations: "
                f"{', '.join(entry.permitted_operations)}"
            )
            if entry.allowed_values:
                line += f"; allowed values: {', '.join(entry.allowed_values)}"
            lines.append(line)
        lines.append("END RESOURCE CANDIDATE POLICY")
        return "\n".join(lines)

    def validate_candidate(self, mutation: AdventureMutation) -> AdventureMutation:
        """Allow only a declared public resource operation through this view.

        This establishes provider-review eligibility from bounded public
        declarations only. The authoritative staging path must still validate
        operation values, bounds, and current-state consequences against the
        complete immutable catalog. No mutation is transformed or authorized.
        """
        if not isinstance(mutation, AdventureMutation):
            raise TypeError("resource candidate mutation is invalid")
        if mutation.kind != MUTATION_RESOURCE_CHANGE:
            raise AdventureTurnResourcePolicyError("resource candidate mutation kind is invalid")
        entry = next((item for item in self.entries if item.resource_id == mutation.resource_id), None)
        if entry is None:
            raise AdventureTurnResourcePolicyError("resource candidate is not a declared public resource")
        if mutation.resource_operation not in entry.permitted_operations:
            raise AdventureTurnResourcePolicyError("resource candidate operation is not permitted")
        if entry.kind == "enum" and mutation.resource_value not in entry.allowed_values:
            raise AdventureTurnResourcePolicyError("resource candidate enum value is not permitted")
        return mutation

    def portable_enum_candidate_schema(self) -> dict[str, object]:
        """Return narrow structured-output guidance for public enum resources.

        Version one intentionally covers only enum ``set`` operations.  Those
        values have an explicit finite vocabulary, so a portable grammar can
        constrain them without exposing current values or accepting an
        unconstrained JSON value. Numeric, flag, inventory, equipment, and
        clock resources keep their manual/Core-reviewed path until each has a
        separate value contract and smoke evidence.
        """
        entries = tuple(item for item in self.entries if item.kind == "enum")
        if not entries:
            raise AdventureTurnResourcePolicyError("no portable public enum resources are declared")
        values = tuple(sorted({value for entry in entries for value in entry.allowed_values}))
        return {
            "type": "object",
            "required": ["schema_version", "candidates"],
            "properties": {
                "schema_version": {"type": "integer"},
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["mutation", "confidence"],
                        "properties": {
                            "mutation": {
                                "type": "object",
                                "required": ["kind", "id", "operation", "value"],
                                "properties": {
                                    "kind": {"type": "string", "enum": ["resource_change"]},
                                    "id": {"type": "string", "enum": [item.resource_id for item in entries]},
                                    "operation": {"type": "string", "enum": ["set"]},
                                    "value": {"type": "string", "enum": list(values)},
                                },
                            },
                            "confidence": {"type": "number"},
                        },
                    },
                },
            },
        }

    def validate_portable_enum_candidate(self, mutation: AdventureMutation) -> AdventureMutation:
        """Apply the narrow portable enum route policy after generic parsing."""
        mutation = self.validate_candidate(mutation)
        entry = next(item for item in self.entries if item.resource_id == mutation.resource_id)
        if entry.kind != "enum" or mutation.resource_operation != "set":
            raise AdventureTurnResourcePolicyError("resource candidate is outside the portable enum route")
        return mutation


__all__ = [
    "AdventureTurnResourcePolicyEntry", "AdventureTurnResourcePolicyError", "AdventureTurnResourcePolicyView",
    "MAX_RESOURCE_CANDIDATE_POLICY_ENTRIES", "MAX_RESOURCE_CANDIDATE_POLICY_CHARACTERS",
]
