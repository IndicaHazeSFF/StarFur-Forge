"""Pure, catalog-validated current values for generic adventure resources.

This is deliberately an in-memory reducer. It does not read manifests, append
events, expose commands, or accept model-authored operations. A later Core
adapter must persist only already-validated operations as authoritative events.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Iterable, Mapping

from pipeline.adventure_correction import resolve_active_adventure_events
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition, AdventureResourceError


_ITEM_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_OBJECTIVE_VALUES = frozenset({"inactive", "active", "completed", "failed"})


class AdventureResourceStateError(ValueError):
    """Raised when a resource value or operation is invalid for its catalog."""


MAX_CONTEXT_RESOURCE_FACTS = 12


@dataclass(frozen=True)
class AdventureResourceFact:
    """One complete current resource value with its latest event provenance."""

    resource_id: str
    label: str
    kind: str
    value: object
    visibility: str
    source_event_id: str | None = None


def _text(value: object, *, field: str, maximum: int = 96) -> str:
    if not isinstance(value, str):
        raise AdventureResourceStateError(f"{field} must be text")
    result = " ".join(value.split())
    if not result:
        raise AdventureResourceStateError(f"{field} cannot be empty")
    if len(result) > maximum:
        raise AdventureResourceStateError(f"{field} must be at most {maximum} characters")
    return result


def _decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool):
        raise AdventureResourceStateError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise AdventureResourceStateError(f"{field} must be numeric") from error
    if not result.is_finite():
        raise AdventureResourceStateError(f"{field} must be finite")
    return result


def _item_count(value: object, *, field: str) -> tuple[str, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise AdventureResourceStateError(f"{field} must be an item identifier and positive count")
    item = _text(value[0], field="inventory item", maximum=64).casefold()
    if not _ITEM_ID.fullmatch(item):
        raise AdventureResourceStateError("inventory item identifier is invalid")
    count = value[1]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise AdventureResourceStateError("inventory count must be a positive integer")
    return item, count


def _default_value(definition: AdventureResourceDefinition) -> object:
    if definition.kind == "flag":
        return False
    if definition.kind == "enum":
        return definition.allowed_values[0]
    if definition.kind in {"integer", "decimal"}:
        return definition.minimum
    if definition.kind == "inventory":
        return ()
    if definition.kind in {"equipment", "location"}:
        return None
    if definition.kind == "objective":
        return "inactive"
    if definition.kind == "clock":
        return Decimal("0")
    raise AdventureResourceStateError("resource kind is unsupported")


def _normalize_value(definition: AdventureResourceDefinition, value: object) -> object:
    kind = definition.kind
    if kind == "flag":
        if not isinstance(value, bool):
            raise AdventureResourceStateError("flag value must be boolean")
        return value
    if kind == "enum":
        selected = _text(value, field="enum value")
        for allowed in definition.allowed_values or ():
            if selected.casefold() == allowed.casefold():
                return allowed
        raise AdventureResourceStateError("enum value is not declared")
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise AdventureResourceStateError("integer resource value must be an integer")
        if value < definition.minimum or value > definition.maximum:
            raise AdventureResourceStateError("integer resource value is outside declared bounds")
        return value
    if kind == "decimal":
        result = _decimal(value, field="decimal resource value")
        if result < definition.minimum or result > definition.maximum:
            raise AdventureResourceStateError("decimal resource value is outside declared bounds")
        return result
    if kind == "inventory":
        if not isinstance(value, (tuple, list)):
            raise AdventureResourceStateError("inventory value must be item/count entries")
        normalized: dict[str, int] = {}
        for entry in value:
            item, count = _item_count(entry, field="inventory entry")
            if item in normalized:
                raise AdventureResourceStateError("inventory items must be unique")
            normalized[item] = count
        return tuple(sorted(normalized.items()))
    if kind == "equipment":
        if value is None:
            return None
        return _text(value, field="equipped item", maximum=96)
    if kind == "objective":
        result = _text(value, field="objective status", maximum=16).casefold()
        if result not in _OBJECTIVE_VALUES:
            raise AdventureResourceStateError("objective status is unsupported")
        return result
    if kind == "location":
        return None if value is None else _text(value, field="location", maximum=160)
    if kind == "clock":
        result = _decimal(value, field="clock value")
        if result < 0:
            raise AdventureResourceStateError("clock value cannot be negative")
        return result
    raise AdventureResourceStateError("resource kind is unsupported")


@dataclass(frozen=True)
class AdventureResourceOperation:
    """One Core-supplied operation, not yet an event-log record."""

    resource_id: str
    operation: str
    value: object = None

    def __post_init__(self) -> None:
        if not isinstance(self.resource_id, str):
            raise AdventureResourceStateError("resource identifier is invalid")
        normalized = self.resource_id.strip().casefold()
        if not _ITEM_ID.fullmatch(normalized):
            raise AdventureResourceStateError("resource identifier is invalid")
        object.__setattr__(self, "resource_id", normalized)
        object.__setattr__(self, "operation", _text(self.operation, field="resource operation", maximum=32).casefold())


@dataclass(frozen=True)
class AdventureResourceState:
    """Complete in-memory value projection for one declared resource catalog."""

    catalog: AdventureResourceCatalog
    values: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.catalog, AdventureResourceCatalog):
            raise TypeError("resource state catalog must be an AdventureResourceCatalog")
        if not isinstance(self.values, tuple):
            raise TypeError("resource state values must be a tuple")
        raw = dict(self.values)
        if len(raw) != len(self.values):
            raise AdventureResourceStateError("resource state contains duplicate identifiers")
        expected = {definition.resource_id for definition in self.catalog.definitions}
        if set(raw) != expected:
            raise AdventureResourceStateError("resource state must contain exactly the declared identifiers")
        normalized = tuple(
            (definition.resource_id, _normalize_value(definition, raw[definition.resource_id]))
            for definition in self.catalog.definitions
        )
        object.__setattr__(self, "values", normalized)

    @classmethod
    def initial(cls, catalog: AdventureResourceCatalog) -> "AdventureResourceState":
        if not isinstance(catalog, AdventureResourceCatalog):
            raise TypeError("resource state catalog must be an AdventureResourceCatalog")
        return cls(catalog, tuple((item.resource_id, _default_value(item)) for item in catalog.definitions))

    @classmethod
    def from_values(
        cls, catalog: AdventureResourceCatalog, values: Mapping[str, object],
    ) -> "AdventureResourceState":
        if not isinstance(values, Mapping):
            raise TypeError("resource state values must be a mapping")
        return cls(catalog, tuple(values.items()))

    def value_for(self, resource_id: object) -> object:
        try:
            definition = self.catalog.resolve(resource_id)
        except AdventureResourceError as error:
            raise AdventureResourceStateError(str(error)) from error
        return dict(self.values)[definition.resource_id]

    def apply(self, operation: AdventureResourceOperation) -> "AdventureResourceState":
        if not isinstance(operation, AdventureResourceOperation):
            raise TypeError("resource operation must be an AdventureResourceOperation")
        try:
            definition = self.catalog.resolve(operation.resource_id)
        except AdventureResourceError as error:
            raise AdventureResourceStateError(str(error)) from error
        if operation.operation not in definition.permitted_operations:
            raise AdventureResourceStateError("resource operation is not permitted for this resource")
        current = self.value_for(definition.resource_id)
        next_value = _apply(definition, current, operation)
        values = dict(self.values)
        values[definition.resource_id] = next_value
        return type(self).from_values(self.catalog, values)

    def public_values(self) -> dict[str, object]:
        """Expose only public values for a future prompt/UI projection."""
        values = dict(self.values)
        return {
            definition.resource_id: values[definition.resource_id]
            for definition in self.catalog.definitions
            if definition.visibility == "public"
        }


def derive_adventure_resource_state(
    catalog: AdventureResourceCatalog, events: Iterable[object],
) -> AdventureResourceState:
    """Rebuild complete resource values from already-validated resource events.

    The adapter intentionally needs only the three resource attributes, which
    keeps this pure reducer independent from event-log storage and schemas.
    """
    values = tuple(events)
    active_values = _active_resource_inputs(values)
    state = AdventureResourceState.initial(catalog)
    for event in active_values:
        if getattr(event, "event_type", None) != "resource_change":
            continue
        state = state.apply(AdventureResourceOperation(
            getattr(event, "resource_id", None),
            getattr(event, "resource_operation", None),
            getattr(event, "resource_value", None),
        ))
    return state


def derive_adventure_resource_facts(
    catalog: AdventureResourceCatalog, events: Iterable[object],
) -> tuple[AdventureResourceFact, ...]:
    """Rebuild complete declared resource facts without applying a prompt limit."""
    values = tuple(events)
    state = derive_adventure_resource_state(catalog, values)
    source_ids: dict[str, str] = {}
    for event in _active_resource_inputs(values):
        if getattr(event, "event_type", None) == "resource_change":
            resource_id = getattr(event, "resource_id", None)
            event_id = getattr(event, "event_id", None)
            if isinstance(resource_id, str) and isinstance(event_id, str):
                source_ids[resource_id] = event_id
    current = dict(state.values)
    return tuple(
        AdventureResourceFact(
            resource_id=definition.resource_id,
            label=definition.label,
            kind=definition.kind,
            value=current[definition.resource_id],
            visibility=definition.visibility,
            source_event_id=source_ids.get(definition.resource_id),
        )
        for definition in catalog.definitions
    )


def select_adventure_resource_context(
    facts: Iterable[AdventureResourceFact], *, limit: int = MAX_CONTEXT_RESOURCE_FACTS,
) -> tuple[AdventureResourceFact, ...]:
    """Expose only public declared values in a bounded deterministic prompt view."""
    if not isinstance(limit, int) or not 1 <= limit <= MAX_CONTEXT_RESOURCE_FACTS:
        raise ValueError(f"resource fact limit must be between 1 and {MAX_CONTEXT_RESOURCE_FACTS}")
    values = tuple(facts)
    if not all(isinstance(fact, AdventureResourceFact) for fact in values):
        raise TypeError("resource facts must be AdventureResourceFacts")
    return tuple(fact for fact in values if fact.visibility == "public")[:limit]


def _active_resource_inputs(events: tuple[object, ...]) -> tuple[object, ...]:
    """Resolve persisted corrections without assigning history to staged drafts.

    Event-log validation passes existing authoritative events followed by
    sequence-free drafts.  Only persisted event-shaped records may participate
    in supersession; the drafts still apply afterward so catalog validation
    remains atomic before a batch receives its final sequence identifiers.
    """
    authoritative: list[object] = []
    drafts: list[object] = []
    for event in events:
        if all(hasattr(event, attribute) for attribute in ("sequence", "event_id", "supersedes_event_id")):
            authoritative.append(event)
        else:
            drafts.append(event)
    return (*resolve_active_adventure_events(tuple(authoritative)).active_events, *drafts)


def _apply(
    definition: AdventureResourceDefinition, current: object, operation: AdventureResourceOperation,
) -> object:
    kind, action, value = definition.kind, operation.operation, operation.value
    if kind == "flag":
        if action == "set":
            return _normalize_value(definition, value)
        if action == "activate":
            if value is not None:
                raise AdventureResourceStateError("activate does not accept a value")
            return True
        if action == "deactivate":
            if value is not None:
                raise AdventureResourceStateError("deactivate does not accept a value")
            return False
    if kind in {"enum", "integer", "decimal", "location", "clock"} and action == "set":
        return _normalize_value(definition, value)
    if kind in {"integer", "decimal", "clock"} and action in {"increment", "decrement"}:
        delta = _decimal(value, field="resource delta")
        if delta < 0:
            raise AdventureResourceStateError("resource delta cannot be negative")
        if kind == "integer":
            if delta != delta.to_integral_value():
                raise AdventureResourceStateError("integer resource delta must be an integer")
            result: object = current + int(delta) if action == "increment" else current - int(delta)
        else:
            result = current + delta if action == "increment" else current - delta
        return _normalize_value(definition, result)
    if kind == "inventory" and action in {"add", "remove"}:
        item, count = _item_count(value, field="inventory operation")
        inventory = dict(current)
        prior = inventory.get(item, 0)
        if action == "add":
            inventory[item] = prior + count
        else:
            if prior < count:
                raise AdventureResourceStateError("inventory removal exceeds available count")
            if prior == count:
                del inventory[item]
            else:
                inventory[item] = prior - count
        return _normalize_value(definition, tuple(inventory.items()))
    if kind == "equipment":
        if action == "equip":
            if value is None:
                raise AdventureResourceStateError("equip requires an item")
            return _normalize_value(definition, value)
        if action == "unequip":
            if value is not None:
                raise AdventureResourceStateError("unequip does not accept a value")
            return None
    if kind == "objective":
        transitions = {"activate": "active", "complete": "completed", "fail": "failed"}
        if action in transitions:
            if value is not None:
                raise AdventureResourceStateError(f"{action} does not accept a value")
            return transitions[action]
    raise AdventureResourceStateError("resource operation is invalid for this resource")


__all__ = [
    "AdventureResourceOperation", "AdventureResourceState", "AdventureResourceStateError",
    "AdventureResourceFact", "MAX_CONTEXT_RESOURCE_FACTS", "derive_adventure_resource_facts",
    "derive_adventure_resource_state", "select_adventure_resource_context",
]
