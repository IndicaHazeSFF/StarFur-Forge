"""Pure scenario-declared resource definitions for isolated adventures.

Resource names such as ``ammo`` and ``credits`` remain scenario data. Core
only validates a small generic vocabulary; it does not yet store values, infer
operations from prose, add commands, or let a provider mutate any resource.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Iterable


RESOURCE_KINDS = frozenset({
    "flag", "enum", "integer", "decimal", "inventory", "equipment",
    "objective", "location", "clock",
})
RESOURCE_VISIBILITIES = frozenset({"public", "hidden"})
_RESOURCE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_OPERATION_SETS = {
    "flag": frozenset({"set", "activate", "deactivate"}),
    "enum": frozenset({"set"}),
    "integer": frozenset({"set", "increment", "decrement"}),
    "decimal": frozenset({"set", "increment", "decrement"}),
    "inventory": frozenset({"add", "remove"}),
    "equipment": frozenset({"equip", "unequip"}),
    "objective": frozenset({"activate", "complete", "fail"}),
    "location": frozenset({"set"}),
    "clock": frozenset({"set", "increment"}),
}
_BOUNDED_KINDS = frozenset({"integer", "decimal"})


class AdventureResourceError(ValueError):
    """Raised when a resource declaration exceeds the closed Core schema."""


def _text(value: object, *, field: str, maximum: int, collapse: bool = False) -> str:
    if not isinstance(value, str):
        raise AdventureResourceError(f"{field} must be text")
    result = " ".join(value.split()) if collapse else value.strip()
    if not result:
        raise AdventureResourceError(f"{field} cannot be empty")
    if len(result) > maximum:
        raise AdventureResourceError(f"{field} must be at most {maximum} characters")
    return result


def _bound(value: object, *, field: str, kind: str) -> int | Decimal:
    if isinstance(value, bool):
        raise AdventureResourceError(f"{field} must be numeric")
    if kind == "integer":
        if not isinstance(value, int):
            raise AdventureResourceError(f"{field} must be an integer")
        return value
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, float, str)):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise AdventureResourceError(f"{field} must be decimal-compatible") from error
    else:
        raise AdventureResourceError(f"{field} must be decimal-compatible")
    if not result.is_finite():
        raise AdventureResourceError(f"{field} must be finite")
    return result


@dataclass(frozen=True)
class AdventureResourceDefinition:
    """One declarative generic resource; values/operations remain future work."""

    resource_id: str
    label: str
    kind: str
    visibility: str = "public"
    minimum: int | Decimal | None = None
    maximum: int | Decimal | None = None
    allowed_values: tuple[str, ...] | None = None
    permitted_operations: frozenset[str] | None = None

    def __post_init__(self) -> None:
        resource_id = _text(self.resource_id, field="resource identifier", maximum=64).casefold()
        if not _RESOURCE_ID_RE.fullmatch(resource_id):
            raise AdventureResourceError("resource identifier is invalid")
        object.__setattr__(self, "resource_id", resource_id)
        object.__setattr__(self, "label", _text(self.label, field="resource label", maximum=96, collapse=True))
        kind = _text(self.kind, field="resource kind", maximum=32).casefold()
        if kind not in RESOURCE_KINDS:
            raise AdventureResourceError("resource kind is unsupported")
        object.__setattr__(self, "kind", kind)
        visibility = _text(self.visibility, field="resource visibility", maximum=16).casefold()
        if visibility not in RESOURCE_VISIBILITIES:
            raise AdventureResourceError("resource visibility is unsupported")
        object.__setattr__(self, "visibility", visibility)

        if kind in _BOUNDED_KINDS:
            if self.minimum is None or self.maximum is None:
                raise AdventureResourceError("bounded resources require minimum and maximum")
            minimum = _bound(self.minimum, field="resource minimum", kind=kind)
            maximum = _bound(self.maximum, field="resource maximum", kind=kind)
            if minimum > maximum:
                raise AdventureResourceError("resource minimum cannot exceed maximum")
            object.__setattr__(self, "minimum", minimum)
            object.__setattr__(self, "maximum", maximum)
        elif self.minimum is not None or self.maximum is not None:
            raise AdventureResourceError("resource bounds are allowed only for integer or decimal resources")

        if kind == "enum":
            if not isinstance(self.allowed_values, tuple) or not self.allowed_values or len(self.allowed_values) > 64:
                raise AdventureResourceError("enum resources require 1-64 allowed values")
            values = tuple(_text(value, field="enum value", maximum=96, collapse=True) for value in self.allowed_values)
            if len({value.casefold() for value in values}) != len(values):
                raise AdventureResourceError("enum values must be unique")
            object.__setattr__(self, "allowed_values", values)
        elif self.allowed_values is not None:
            raise AdventureResourceError("allowed values are permitted only for enum resources")

        allowed_operations = _OPERATION_SETS[kind]
        if self.permitted_operations is None:
            object.__setattr__(self, "permitted_operations", allowed_operations)
        else:
            if not isinstance(self.permitted_operations, frozenset) or not self.permitted_operations:
                raise AdventureResourceError("permitted operations must be a non-empty frozenset")
            operations = frozenset(
                _text(value, field="resource operation", maximum=32).casefold()
                for value in self.permitted_operations
            )
            if not operations.issubset(allowed_operations):
                raise AdventureResourceError("resource operation is not permitted for its kind")
            object.__setattr__(self, "permitted_operations", operations)

    def public_definition(self) -> dict[str, object]:
        """Return metadata suitable for a future package/UI read model."""
        return {
            "id": self.resource_id,
            "label": self.label,
            "kind": self.kind,
            "visibility": self.visibility,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "allowed_values": self.allowed_values,
            "permitted_operations": tuple(sorted(self.permitted_operations)),
        }

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe declaration for an isolated workspace manifest."""
        def serializable(value: object) -> object:
            return str(value) if isinstance(value, Decimal) else value

        return {
            "id": self.resource_id,
            "label": self.label,
            "kind": self.kind,
            "visibility": self.visibility,
            "minimum": serializable(self.minimum),
            "maximum": serializable(self.maximum),
            "allowed_values": None if self.allowed_values is None else list(self.allowed_values),
            "permitted_operations": sorted(self.permitted_operations),
        }

    @classmethod
    def from_dict(cls, value: object) -> "AdventureResourceDefinition":
        """Validate one JSON-compatible scenario declaration."""
        if not isinstance(value, dict):
            raise AdventureResourceError("resource declaration must be an object")
        try:
            allowed_values = value.get("allowed_values")
            operations = value.get("permitted_operations")
            return cls(
                resource_id=value["id"], label=value["label"], kind=value["kind"],
                visibility=value.get("visibility", "public"),
                minimum=value.get("minimum"), maximum=value.get("maximum"),
                allowed_values=None if allowed_values is None else tuple(allowed_values),
                permitted_operations=None if operations is None else frozenset(operations),
            )
        except KeyError as error:
            raise AdventureResourceError("resource declaration is incomplete") from error


@dataclass(frozen=True)
class AdventureResourceCatalog:
    """A bounded scenario declaration with stable, unique resource identifiers."""

    definitions: tuple[AdventureResourceDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.definitions, tuple) or len(self.definitions) > 128:
            raise AdventureResourceError("resource catalog must contain at most 128 definitions")
        if not all(isinstance(definition, AdventureResourceDefinition) for definition in self.definitions):
            raise TypeError("resource catalog definitions must be AdventureResourceDefinitions")
        identifiers = [definition.resource_id for definition in self.definitions]
        if len(set(identifiers)) != len(identifiers):
            raise AdventureResourceError("resource identifiers must be unique")
        object.__setattr__(self, "definitions", tuple(sorted(self.definitions, key=lambda item: item.resource_id)))

    @classmethod
    def from_definitions(cls, definitions: Iterable[AdventureResourceDefinition]) -> "AdventureResourceCatalog":
        return cls(tuple(definitions))

    def resolve(self, resource_id: object) -> AdventureResourceDefinition:
        normalized = _text(resource_id, field="resource identifier", maximum=64).casefold()
        for definition in self.definitions:
            if definition.resource_id == normalized:
                return definition
        raise AdventureResourceError("resource identifier is not declared")

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": 1, "definitions": [item.to_dict() for item in self.definitions]}

    @classmethod
    def from_dict(cls, value: object) -> "AdventureResourceCatalog":
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise AdventureResourceError("resource catalog schema is unsupported")
        definitions = value.get("definitions")
        if not isinstance(definitions, list):
            raise AdventureResourceError("resource catalog definitions are invalid")
        return cls.from_definitions(AdventureResourceDefinition.from_dict(item) for item in definitions)


__all__ = [
    "AdventureResourceCatalog", "AdventureResourceDefinition", "AdventureResourceError",
    "RESOURCE_KINDS", "RESOURCE_VISIBILITIES",
]
