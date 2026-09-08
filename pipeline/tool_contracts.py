"""Strict inert contracts for future model-reachable tool proposals.

Validation in this module is application-level input validation only.  It does
not authenticate a caller, grant permission, record confirmation, issue an
invocation identity, select an executor, materialize files, or execute work.
The sole initial contract describes bounded ``sandbox.run`` exercise data.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Callable, Iterable, Mapping

from .tool_registry import MAX_REGISTERED_TOOLS, TOOL_ID_RE, ToolDescriptor, build_core_tool_registry


TOOL_PROPOSAL_SCHEMA_VERSION = 1
TOOL_RESULT_SCHEMA_VERSION = 1
MAX_TOOL_PROPOSAL_BYTES = 64 * 1024
MAX_TOOL_RESULT_BYTES = 32 * 1024
MAX_TOOL_JSON_DEPTH = 8
MAX_TOOL_CONTRACT_VERSION = 999
MAX_SANDBOX_ARGUMENT_FILES = 8
MAX_SANDBOX_INLINE_FILE_BYTES = 16 * 1024
MAX_SANDBOX_INLINE_TOTAL_BYTES = 48 * 1024
MAX_SANDBOX_PATH_CHARACTERS = 240
MAX_SANDBOX_TASK_KIND_CHARACTERS = 80
MAX_SANDBOX_OBJECTIVE_CHARACTERS = 1200
MAX_TOOL_RESULT_TEXT_CHARACTERS = 8192
MAX_TOOL_RESULT_ARTIFACTS = 16

TOOL_RETRY_CLASSES = frozenset({"never", "proposal_only"})
TOOL_RESULT_OUTCOMES = frozenset({
    "completed", "failed", "denied", "cancelled", "timed_out", "outcome_unknown",
})
TOOL_RESULT_ERROR_CATEGORIES = frozenset({
    "validation_failed", "permission_denied", "confirmation_required", "backend_unavailable",
    "execution_failed", "timed_out", "cancelled", "outcome_unknown",
})
CORRELATION_ID_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}-[A-Za-z0-9_-]{1,64}$")
ARTIFACT_REF_RE = re.compile(r"^TF-[A-Za-z0-9_-]{1,64}$")

FrozenJSON = object
ArgumentValidator = Callable[[Mapping[str, object]], Mapping[str, object]]
ResultValidator = Callable[["ToolResult"], "ToolResult"]


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_exact_fields(value: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise ValueError(f"{label} fields are invalid")


def _freeze_json(value: object) -> FrozenJSON:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _json_depth(value: object) -> int:
    if isinstance(value, Mapping):
        return 1 + max((_json_depth(item) for item in value.values()), default=0)
    if isinstance(value, (list, tuple)):
        return 1 + max((_json_depth(item) for item in value), default=0)
    return 0


def _reject_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains duplicate fields")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise ValueError(f"non-finite JSON number is invalid: {value}")


def _decode_json_object(payload: object, *, max_bytes: int, label: str) -> Mapping[str, object]:
    if not isinstance(payload, str):
        raise TypeError(f"{label} JSON must be text")
    try:
        encoded = payload.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{label} JSON is not valid UTF-8 text") from error
    if len(encoded) > max_bytes:
        raise ValueError(f"{label} JSON size limit exceeded")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_object,
            parse_constant=_reject_nonfinite,
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} JSON is malformed") from error
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    if _json_depth(value) > MAX_TOOL_JSON_DEPTH:
        raise ValueError(f"{label} JSON depth limit exceeded")
    return value


@dataclass(frozen=True)
class ToolProposal:
    """An immutable untrusted proposal; validity confers no authority."""

    schema_version: int
    tool_id: str
    tool_version: int
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.schema_version != TOOL_PROPOSAL_SCHEMA_VERSION or isinstance(self.schema_version, bool):
            raise ValueError("tool proposal schema version is unsupported")
        if not isinstance(self.tool_id, str) or not TOOL_ID_RE.fullmatch(self.tool_id):
            raise ValueError("tool proposal identifier is invalid")
        if (
            not _is_int(self.tool_version)
            or self.tool_version < 1
            or self.tool_version > MAX_TOOL_CONTRACT_VERSION
        ):
            raise ValueError("tool proposal version is invalid")
        if not isinstance(self.arguments, Mapping):
            raise TypeError("tool proposal arguments must be an object")
        object.__setattr__(self, "arguments", _freeze_json(self.arguments))

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ToolProposal":
        if not isinstance(value, Mapping):
            raise TypeError("tool proposal must be an object")
        _require_exact_fields(
            value, frozenset({"schema_version", "tool_id", "tool_version", "arguments"}), "tool proposal",
        )
        return cls(value["schema_version"], value["tool_id"], value["tool_version"], value["arguments"])

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "arguments": _thaw_json(self.arguments),
        }


@dataclass(frozen=True)
class ToolResult:
    """Bounded inert result data; ``invocation_id`` is correlation, not authority."""

    schema_version: int
    invocation_id: str
    tool_id: str
    tool_version: int
    outcome: str
    exit_code: int | None
    stdout: str
    stderr: str
    error_category: str | None
    artifact_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != TOOL_RESULT_SCHEMA_VERSION or isinstance(self.schema_version, bool):
            raise ValueError("tool result schema version is unsupported")
        if not isinstance(self.invocation_id, str) or not CORRELATION_ID_RE.fullmatch(self.invocation_id):
            raise ValueError("tool result invocation identifier is invalid")
        if not isinstance(self.tool_id, str) or not TOOL_ID_RE.fullmatch(self.tool_id):
            raise ValueError("tool result identifier is invalid")
        if (
            not _is_int(self.tool_version)
            or self.tool_version < 1
            or self.tool_version > MAX_TOOL_CONTRACT_VERSION
        ):
            raise ValueError("tool result version is invalid")
        if self.outcome not in TOOL_RESULT_OUTCOMES:
            raise ValueError("tool result outcome is invalid")
        if self.exit_code is not None and (not _is_int(self.exit_code) or not -255 <= self.exit_code <= 255):
            raise ValueError("tool result exit code is invalid")
        for label, text in (("stdout", self.stdout), ("stderr", self.stderr)):
            if not isinstance(text, str) or len(text) > MAX_TOOL_RESULT_TEXT_CHARACTERS:
                raise ValueError(f"tool result {label} is invalid")
        if self.error_category is not None and self.error_category not in TOOL_RESULT_ERROR_CATEGORIES:
            raise ValueError("tool result error category is invalid")
        refs = tuple(self.artifact_refs)
        if len(refs) > MAX_TOOL_RESULT_ARTIFACTS or any(
            not isinstance(item, str) or not ARTIFACT_REF_RE.fullmatch(item) for item in refs
        ):
            raise ValueError("tool result artifact references are invalid")
        if len(set(refs)) != len(refs):
            raise ValueError("tool result artifact references must be unique")
        if self.outcome == "completed" and self.error_category is not None:
            raise ValueError("completed tool result cannot include an error category")
        if self.outcome != "completed" and self.error_category is None:
            raise ValueError("non-completed tool result requires an error category")
        object.__setattr__(self, "artifact_refs", refs)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ToolResult":
        if not isinstance(value, Mapping):
            raise TypeError("tool result must be an object")
        _require_exact_fields(value, frozenset({
            "schema_version", "invocation_id", "tool_id", "tool_version", "outcome", "exit_code",
            "stdout", "stderr", "error_category", "artifact_refs",
        }), "tool result")
        refs = value["artifact_refs"]
        if not isinstance(refs, (list, tuple)):
            raise TypeError("tool result artifact references must be an array")
        return cls(
            value["schema_version"], value["invocation_id"], value["tool_id"], value["tool_version"],
            value["outcome"], value["exit_code"], value["stdout"], value["stderr"],
            value["error_category"], tuple(refs),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "invocation_id": self.invocation_id,
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error_category": self.error_category,
            "artifact_refs": list(self.artifact_refs),
        }


@dataclass(frozen=True)
class ToolContract:
    """Core-owned versioned validators bound to one immutable descriptor."""

    descriptor: ToolDescriptor
    tool_version: int
    retry_class: str
    argument_validator: ArgumentValidator
    result_validator: ResultValidator
    resource_requirements: tuple[str, ...] = ()
    limits: Mapping[str, int] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, ToolDescriptor):
            raise TypeError("tool contract descriptor is invalid")
        if (
            not _is_int(self.tool_version)
            or self.tool_version < 1
            or self.tool_version > MAX_TOOL_CONTRACT_VERSION
        ):
            raise ValueError("tool contract version is invalid")
        if self.retry_class not in TOOL_RETRY_CLASSES:
            raise ValueError("tool contract retry class is invalid")
        if not callable(self.argument_validator):
            raise TypeError("tool contract argument validator is invalid")
        if not callable(self.result_validator):
            raise TypeError("tool contract result validator is invalid")
        requirements = tuple(self.resource_requirements)
        if len(requirements) > 16 or any(
            not isinstance(item, str) or not TOOL_ID_RE.fullmatch(item) for item in requirements
        ):
            raise ValueError("tool contract resource requirements are invalid")
        if len(set(requirements)) != len(requirements):
            raise ValueError("tool contract resource requirements must be unique")
        if not isinstance(self.limits, Mapping) or len(self.limits) > 16 or any(
            not isinstance(key, str)
            or not TOOL_ID_RE.fullmatch(key)
            or not _is_int(value)
            or value < 0
            for key, value in self.limits.items()
        ):
            raise ValueError("tool contract limits are invalid")
        object.__setattr__(self, "resource_requirements", requirements)
        object.__setattr__(self, "limits", MappingProxyType(dict(self.limits)))

    @property
    def tool_id(self) -> str:
        return self.descriptor.tool_id

    def validate_proposal(self, proposal: ToolProposal) -> ToolProposal:
        if not isinstance(proposal, ToolProposal):
            raise TypeError("tool proposal is invalid")
        if proposal.tool_id != self.tool_id or proposal.tool_version != self.tool_version:
            raise ValueError("tool proposal does not match contract")
        validated = self.argument_validator(proposal.arguments)
        return ToolProposal(
            proposal.schema_version, proposal.tool_id, proposal.tool_version, validated,
        )

    def validate_result(self, result: ToolResult) -> ToolResult:
        if not isinstance(result, ToolResult):
            raise TypeError("tool result is invalid")
        if result.tool_id != self.tool_id or result.tool_version != self.tool_version:
            raise ValueError("tool result does not match contract")
        return self.result_validator(result)

    def public_dict(self) -> dict[str, object]:
        return {
            "tool_id": self.tool_id,
            "tool_version": self.tool_version,
            "retry_class": self.retry_class,
            "resource_requirements": list(self.resource_requirements),
            "limits": dict(self.limits),
        }


@dataclass(frozen=True)
class ToolContractRegistry:
    """Bounded immutable lookup; it cannot issue or execute an invocation."""

    contracts: tuple[ToolContract, ...] = ()

    def __init__(self, contracts: Iterable[ToolContract] = ()) -> None:
        ordered = tuple(contracts)
        if not all(isinstance(item, ToolContract) for item in ordered):
            raise TypeError("tool contract registry entries are invalid")
        if len(ordered) > MAX_REGISTERED_TOOLS:
            raise ValueError("tool contract registry limit exceeded")
        keys = tuple((item.tool_id, item.tool_version) for item in ordered)
        if len(set(keys)) != len(keys):
            raise ValueError("tool contract registry keys must be unique")
        object.__setattr__(self, "contracts", tuple(sorted(
            ordered, key=lambda item: (item.tool_id, item.tool_version),
        )))

    def get(self, tool_id: object, tool_version: object) -> ToolContract | None:
        if not isinstance(tool_id, str) or not _is_int(tool_version):
            return None
        return next((
            item for item in self.contracts
            if item.tool_id == tool_id and item.tool_version == tool_version
        ), None)

    def validate_proposal(self, proposal: ToolProposal) -> ToolProposal:
        if not isinstance(proposal, ToolProposal):
            raise TypeError("tool proposal is invalid")
        contract = self.get(proposal.tool_id, proposal.tool_version)
        if contract is None:
            raise ValueError("tool proposal contract is unknown")
        return contract.validate_proposal(proposal)

    def validate_result(self, result: ToolResult) -> ToolResult:
        if not isinstance(result, ToolResult):
            raise TypeError("tool result is invalid")
        contract = self.get(result.tool_id, result.tool_version)
        if contract is None:
            raise ValueError("tool result contract is unknown")
        return contract.validate_result(result)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "contracts": [item.public_dict() for item in self.contracts],
        }


def validate_sandbox_run_arguments(arguments: Mapping[str, object]) -> Mapping[str, object]:
    """Validate inert inline exercise data without materializing it."""
    if not isinstance(arguments, Mapping):
        raise TypeError("sandbox.run arguments must be an object")
    _require_exact_fields(arguments, frozenset({"task_kind", "objective", "files"}), "sandbox.run arguments")
    task_kind = arguments["task_kind"]
    objective = arguments["objective"]
    files = arguments["files"]
    if (
        not isinstance(task_kind, str)
        or not task_kind.strip()
        or len(task_kind) > MAX_SANDBOX_TASK_KIND_CHARACTERS
        or not TOOL_ID_RE.fullmatch(task_kind)
    ):
        raise ValueError("sandbox.run task kind is invalid")
    if (
        not isinstance(objective, str)
        or not objective.strip()
        or len(objective) > MAX_SANDBOX_OBJECTIVE_CHARACTERS
    ):
        raise ValueError("sandbox.run objective is invalid")
    if not isinstance(files, (list, tuple)) or not 1 <= len(files) <= MAX_SANDBOX_ARGUMENT_FILES:
        raise ValueError("sandbox.run file count is invalid")
    validated_files: list[Mapping[str, object]] = []
    seen_paths: set[str] = set()
    total_bytes = 0
    for item in files:
        if not isinstance(item, Mapping):
            raise TypeError("sandbox.run file entry must be an object")
        _require_exact_fields(item, frozenset({"path", "content"}), "sandbox.run file")
        path = item["path"]
        content = item["content"]
        if (
            not isinstance(path, str)
            or not path
            or len(path) > MAX_SANDBOX_PATH_CHARACTERS
            or "\\" in path
        ):
            raise ValueError("sandbox.run file path is invalid")
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
            raise ValueError("sandbox.run file path is invalid")
        if path in seen_paths:
            raise ValueError("sandbox.run file paths must be unique")
        if not isinstance(content, str):
            raise TypeError("sandbox.run file content must be text")
        try:
            content_bytes = len(content.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise ValueError("sandbox.run file content is not valid UTF-8 text") from error
        if content_bytes > MAX_SANDBOX_INLINE_FILE_BYTES:
            raise ValueError("sandbox.run inline file size limit exceeded")
        total_bytes += content_bytes
        if total_bytes > MAX_SANDBOX_INLINE_TOTAL_BYTES:
            raise ValueError("sandbox.run inline input size limit exceeded")
        seen_paths.add(path)
        validated_files.append({"path": path, "content": content})
    return MappingProxyType({
        "task_kind": task_kind,
        "objective": objective,
        "files": tuple(MappingProxyType(dict(item)) for item in validated_files),
    })


def decode_tool_proposal_json(payload: object) -> ToolProposal:
    return ToolProposal.from_mapping(_decode_json_object(
        payload, max_bytes=MAX_TOOL_PROPOSAL_BYTES, label="tool proposal",
    ))


def decode_tool_result_json(payload: object) -> ToolResult:
    return ToolResult.from_mapping(_decode_json_object(
        payload, max_bytes=MAX_TOOL_RESULT_BYTES, label="tool result",
    ))


def validate_sandbox_run_result(result: ToolResult) -> ToolResult:
    """Accept an already bounded result value without treating it as trustworthy."""
    if not isinstance(result, ToolResult):
        raise TypeError("sandbox.run result is invalid")
    return result


def build_core_tool_contract_registry() -> ToolContractRegistry:
    descriptor = build_core_tool_registry().get("sandbox.run")
    if descriptor is None:  # Defensive fail-closed guard against catalog drift.
        raise ValueError("sandbox.run descriptor is unavailable")
    return ToolContractRegistry((ToolContract(
        descriptor=descriptor,
        tool_version=1,
        retry_class="never",
        argument_validator=validate_sandbox_run_arguments,
        result_validator=validate_sandbox_run_result,
        resource_requirements=("sandbox.backend",),
        limits={
            "max_files": MAX_SANDBOX_ARGUMENT_FILES,
            "max_inline_file_bytes": MAX_SANDBOX_INLINE_FILE_BYTES,
            "max_inline_total_bytes": MAX_SANDBOX_INLINE_TOTAL_BYTES,
            "max_objective_characters": MAX_SANDBOX_OBJECTIVE_CHARACTERS,
            "max_result_text_characters": MAX_TOOL_RESULT_TEXT_CHARACTERS,
        },
    ),))


__all__ = [
    "MAX_TOOL_JSON_DEPTH", "MAX_TOOL_PROPOSAL_BYTES", "MAX_TOOL_RESULT_BYTES",
    "TOOL_PROPOSAL_SCHEMA_VERSION", "TOOL_RESULT_SCHEMA_VERSION", "ToolContract",
    "ToolContractRegistry", "ToolProposal", "ToolResult", "build_core_tool_contract_registry",
    "decode_tool_proposal_json", "decode_tool_result_json", "validate_sandbox_run_arguments",
    "validate_sandbox_run_result",
]
