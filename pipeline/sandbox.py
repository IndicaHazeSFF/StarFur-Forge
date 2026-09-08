"""Bounded learning-sandbox contracts with no default code execution.

This module deliberately does not mistake a normal subprocess for secure
isolation.  The default service denies execution until a future container/VM
or equivalently isolated backend is injected.  It still provides one
deterministic contract for request validation, temporary-workspace handling,
timeouts/resource policy, and bounded user-visible reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import tempfile
import time
from typing import Protocol

from pipeline.persona_state import PERSONA_ID_RE


MAX_SANDBOX_FILES = 32
MAX_SANDBOX_FILE_CHARACTERS = 64_000
MAX_SANDBOX_TOTAL_CHARACTERS = 256_000
MAX_SANDBOX_OUTPUT_CHARACTERS = 8_000
MAX_SANDBOX_FILE_BYTES = 64_000
MAX_SANDBOX_TOTAL_BYTES = 256_000
MAX_SANDBOX_OUTPUT_BYTES = 8_000
MAX_SANDBOX_TIMEOUT_SECONDS = 600.0
SANDBOX_STATUSES = ("completed", "failed", "timed_out", "denied")
_RUN_ID_RE = re.compile(r"^SB-[a-z0-9][a-z0-9_-]{0,63}$")


def _bounded_text(name: str, value: str, *, limit: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string.")
    if not allow_empty:
        value = value.strip()
        if not value:
            raise ValueError(f"{name} must not be empty.")
    if len(value) > limit:
        raise ValueError(f"{name} must be at most {limit} characters.")
    return value


def _persona_id(value: str) -> str:
    normalized = _bounded_text("persona_id", value, limit=64).casefold()
    if not PERSONA_ID_RE.fullmatch(normalized):
        raise ValueError("persona_id must be a valid PersonaState identifier.")
    return normalized


def _relative_path(value: str) -> str:
    raw = _bounded_text("file path", value, limit=240)
    path = PurePosixPath(raw)
    if path.is_absolute() or raw != path.as_posix() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("file path must be a non-empty relative path without traversal.")
    if "\\" in raw or ":" in raw or any(char in raw for char in '*?"<>|'):
        raise ValueError("file path must use POSIX separators.")
    reserved = {"con", "prn", "aux", "nul"}
    for part in path.parts:
        stem = part.split(".", 1)[0].casefold()
        if stem in reserved or (len(stem) == 4 and stem[:3] in {"com", "lpt"} and stem[3].isdigit()):
            raise ValueError("file path uses a reserved Windows name.")
        if part.endswith((".", " ")):
            raise ValueError("file path has a Windows-unsafe trailing character.")
    return path.as_posix()


@dataclass(frozen=True)
class SandboxFile:
    """One text-only input file materialized only inside a temporary workspace."""

    path: str
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _relative_path(self.path))
        object.__setattr__(
            self,
            "content",
            _bounded_text("file content", self.content, limit=MAX_SANDBOX_FILE_CHARACTERS, allow_empty=True),
        )
        if len(self.content.encode("utf-8")) > MAX_SANDBOX_FILE_BYTES:
            raise ValueError(f"file content must be at most {MAX_SANDBOX_FILE_BYTES} UTF-8 bytes.")


@dataclass(frozen=True)
class SandboxPolicy:
    """Requested limits; a real future backend must enforce them independently."""

    execution_allowed: bool = False
    network_allowed: bool = False
    timeout_seconds: float = 30.0
    max_files: int = MAX_SANDBOX_FILES
    max_total_characters: int = MAX_SANDBOX_TOTAL_CHARACTERS
    max_output_characters: int = MAX_SANDBOX_OUTPUT_CHARACTERS

    def __post_init__(self) -> None:
        if not isinstance(self.execution_allowed, bool) or not isinstance(self.network_allowed, bool):
            raise TypeError("execution_allowed and network_allowed must be booleans.")
        if self.network_allowed:
            raise ValueError("network access is not supported by the sandbox foundation.")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float)):
            raise TypeError("timeout_seconds must be a number.")
        timeout = float(self.timeout_seconds)
        if not 0.1 <= timeout <= MAX_SANDBOX_TIMEOUT_SECONDS:
            raise ValueError(f"timeout_seconds must be between 0.1 and {MAX_SANDBOX_TIMEOUT_SECONDS}.")
        object.__setattr__(self, "timeout_seconds", timeout)
        for name, value, upper in (
            ("max_files", self.max_files, MAX_SANDBOX_FILES),
            ("max_total_characters", self.max_total_characters, MAX_SANDBOX_TOTAL_CHARACTERS),
            ("max_output_characters", self.max_output_characters, MAX_SANDBOX_OUTPUT_CHARACTERS),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer.")
            if not 1 <= value <= upper:
                raise ValueError(f"{name} must be between 1 and {upper}.")


@dataclass(frozen=True)
class SandboxRequest:
    """A declarative task; commands are intentionally not part of this API."""

    run_id: str
    persona_id: str
    task_kind: str
    objective: str
    files: tuple[SandboxFile, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not _RUN_ID_RE.fullmatch(self.run_id):
            raise ValueError("run_id must use the form SB-<stable-id>.")
        object.__setattr__(self, "persona_id", _persona_id(self.persona_id))
        object.__setattr__(self, "task_kind", _bounded_text("task_kind", self.task_kind, limit=80).casefold())
        object.__setattr__(self, "objective", _bounded_text("objective", self.objective, limit=1200))
        files = tuple(self.files)
        if not files:
            raise ValueError("files must not be empty.")
        if not all(isinstance(item, SandboxFile) for item in files):
            raise TypeError("files must contain SandboxFile values.")
        if len({item.path for item in files}) != len(files):
            raise ValueError("files must not contain duplicate paths.")
        object.__setattr__(self, "files", tuple(sorted(files, key=lambda item: item.path)))


@dataclass(frozen=True)
class SandboxBackendResult:
    """Bounded result supplied by a genuinely isolated future backend."""

    status: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        status = _bounded_text("status", self.status, limit=40).casefold()
        if status not in SANDBOX_STATUSES:
            raise ValueError(f"status must be one of {SANDBOX_STATUSES}.")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "stdout", _bounded_text("stdout", self.stdout, limit=MAX_SANDBOX_OUTPUT_CHARACTERS, allow_empty=True))
        object.__setattr__(self, "stderr", _bounded_text("stderr", self.stderr, limit=MAX_SANDBOX_OUTPUT_CHARACTERS, allow_empty=True))
        object.__setattr__(self, "detail", _bounded_text("detail", self.detail, limit=800, allow_empty=True))
        if self.exit_code is not None and (isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int)):
            raise TypeError("exit_code must be an integer or None.")


@dataclass(frozen=True)
class SandboxReport:
    """User-visible, bounded outcome without retaining the temporary workspace."""

    run_id: str
    persona_id: str
    task_kind: str
    status: str
    duration_ms: float
    file_count: int
    total_characters: int
    stdout: str
    stderr: str
    exit_code: int | None
    detail: str

    def public_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "persona_id": self.persona_id,
            "task_kind": self.task_kind,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "file_count": self.file_count,
            "total_characters": self.total_characters,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "detail": self.detail,
        }


class SandboxBackend(Protocol):
    """Future isolated execution adapter; it must enforce policy independently."""

    name: str

    def run(self, request: SandboxRequest, workspace: Path, policy: SandboxPolicy) -> SandboxBackendResult:
        ...


class DisabledSandboxBackend:
    """Safe default: no process, network, or code execution occurs."""

    name = "disabled"
    available = False

    def run(self, request: SandboxRequest, workspace: Path, policy: SandboxPolicy) -> SandboxBackendResult:
        return SandboxBackendResult(
            "denied",
            detail="No isolated sandbox backend is configured; execution was not attempted.",
        )


class SandboxService:
    """Validate/materialize bounded input and delegate only to an injected backend."""

    def __init__(self, backend: SandboxBackend | None = None):
        self.backend = backend or DisabledSandboxBackend()

    def run(self, request: SandboxRequest, *, policy: SandboxPolicy | None = None) -> SandboxReport:
        if not isinstance(request, SandboxRequest):
            raise TypeError("request must be a SandboxRequest instance.")
        policy = policy or SandboxPolicy()
        if not isinstance(policy, SandboxPolicy):
            raise TypeError("policy must be a SandboxPolicy instance.")
        file_count = len(request.files)
        total_characters = sum(len(item.content) for item in request.files)
        total_bytes = sum(len(item.content.encode("utf-8")) for item in request.files)
        if file_count > policy.max_files:
            raise ValueError("request exceeds the sandbox file limit.")
        if total_bytes > min(policy.max_total_characters, MAX_SANDBOX_TOTAL_BYTES):
            raise ValueError("request exceeds the sandbox input-size limit.")

        started = time.perf_counter()
        backend_available = getattr(self.backend, "available", True)
        supports_policy = getattr(self.backend, "supports_policy", None)
        if not isinstance(backend_available, bool) or not backend_available:
            result = SandboxBackendResult(
                "denied",
                detail="No isolated sandbox backend is configured; execution was not attempted.",
            )
            return self._report(request, result, started, file_count, total_characters, policy)
        if callable(supports_policy) and not supports_policy(policy):
            result = SandboxBackendResult(
                "denied",
                detail="The configured sandbox backend cannot enforce the requested policy.",
            )
            return self._report(request, result, started, file_count, total_characters, policy)
        if not policy.execution_allowed:
            result = SandboxBackendResult(
                "denied",
                detail="Sandbox execution is disabled by policy; no temporary files were created.",
            )
            return self._report(request, result, started, file_count, total_characters, policy)

        with tempfile.TemporaryDirectory(prefix="starfur-sandbox-") as temporary:
            workspace = Path(temporary)
            for item in request.files:
                target = workspace.joinpath(*PurePosixPath(item.path).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(item.content, encoding="utf-8")
            try:
                result = self.backend.run(request, workspace, policy)
                if not isinstance(result, SandboxBackendResult):
                    raise TypeError("sandbox backend must return SandboxBackendResult.")
            except Exception as error:
                # Exception text can contain paths, credentials, or provider
                # output.  Keep only a bounded class label in the public report.
                result = SandboxBackendResult("failed", detail=f"Sandbox backend error: {type(error).__name__}")
        return self._report(request, result, started, file_count, total_characters, policy)

    @staticmethod
    def _report(
        request: SandboxRequest,
        result: SandboxBackendResult,
        started: float,
        file_count: int,
        total_characters: int,
        policy: SandboxPolicy,
    ) -> SandboxReport:
        def cap(value: str) -> str:
            limit = min(policy.max_output_characters, MAX_SANDBOX_OUTPUT_BYTES)
            if len(value.encode("utf-8")) <= limit:
                return value
            encoded = value.encode("utf-8")[:limit]
            clipped = encoded.decode("utf-8", errors="ignore")
            return clipped + "\n[output truncated]"

        return SandboxReport(
            run_id=request.run_id,
            persona_id=request.persona_id,
            task_kind=request.task_kind,
            status=result.status,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            file_count=file_count,
            total_characters=total_characters,
            stdout=cap(result.stdout),
            stderr=cap(result.stderr),
            exit_code=result.exit_code,
            detail=result.detail,
        )


def format_sandbox_report(report: SandboxReport) -> str:
    """Render a concise terminal/UI-safe report without a workspace path."""
    if not isinstance(report, SandboxReport):
        raise TypeError("report must be a SandboxReport instance.")
    lines = [
        f"Sandbox run {report.run_id}",
        f"Status: {report.status}",
        f"Task: {report.task_kind}",
        f"Input: {report.file_count} file(s), {report.total_characters} characters",
        f"Duration: {report.duration_ms:.2f} ms",
    ]
    if report.exit_code is not None:
        lines.append(f"Exit code: {report.exit_code}")
    if report.detail:
        lines.append(f"Detail: {report.detail}")
    if report.stdout:
        lines.extend(("Stdout:", report.stdout))
    if report.stderr:
        lines.extend(("Stderr:", report.stderr))
    return "\n".join(lines)


__all__ = [
    "DisabledSandboxBackend",
    "MAX_SANDBOX_FILES",
    "MAX_SANDBOX_FILE_CHARACTERS",
    "MAX_SANDBOX_FILE_BYTES",
    "MAX_SANDBOX_OUTPUT_CHARACTERS",
    "MAX_SANDBOX_OUTPUT_BYTES",
    "MAX_SANDBOX_TIMEOUT_SECONDS",
    "MAX_SANDBOX_TOTAL_CHARACTERS",
    "MAX_SANDBOX_TOTAL_BYTES",
    "SANDBOX_STATUSES",
    "SandboxBackend",
    "SandboxBackendResult",
    "SandboxFile",
    "SandboxPolicy",
    "SandboxReport",
    "SandboxRequest",
    "SandboxService",
    "format_sandbox_report",
]
