"""Provider-free cross-process admission for one exact provider.

This module owns only a nonblocking OS advisory lease.  It does not call or
probe a provider, queue or wait, inspect processes, persist ownership metadata,
kill work, enforce GPU/CPU budgets, or coordinate across different operating
system lock implementations.  A persistent lock file is merely an inode/handle
for the OS lock; its contents are never treated as ownership evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import os
from pathlib import Path
import secrets
import stat
import threading

from pipeline.task_routing import normalize_provider_id

try:  # POSIX production, including WSL.
    import fcntl
except ImportError:  # pragma: no cover - Windows standard-library fallback.
    fcntl = None


PROVIDER_PROCESS_GATE_SCHEMA_VERSION = 1
PROVIDER_PROCESS_LOCK_PREFIX = ".provider-workload-"
PROVIDER_PROCESS_LOCK_SUFFIX = ".lock"


class ProviderProcessGateError(RuntimeError):
    """Raised when cross-process capacity cannot be enforced safely."""


class ProviderProcessLease:
    """Opaque process-bound proof of one held advisory provider lease."""

    __slots__ = (
        "_schema_version", "_coordinator_token", "_descriptor", "_lease_id",
        "_process_id", "_provider_id", "_released",
    )

    def __init__(
        self, *, coordinator_token: object, descriptor: int, lease_id: str,
        provider_id: str,
    ) -> None:
        if not isinstance(descriptor, int) or descriptor < 0:
            raise ValueError("provider process lease descriptor is invalid")
        if not isinstance(lease_id, str) or len(lease_id) != 24:
            raise ValueError("provider process lease ID is invalid")
        if normalize_provider_id(provider_id) != provider_id:
            raise ValueError("provider process lease provider ID is invalid")
        self._schema_version = PROVIDER_PROCESS_GATE_SCHEMA_VERSION
        self._coordinator_token = coordinator_token
        self._descriptor = descriptor
        self._lease_id = lease_id
        self._process_id = os.getpid()
        self._provider_id = provider_id
        self._released = False

    @property
    def schema_version(self) -> int:
        return self._schema_version

    @property
    def lease_id(self) -> str:
        return self._lease_id

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def active(self) -> bool:
        return not self._released and self._process_id == os.getpid()


@dataclass(frozen=True)
class ProviderProcessAdmission:
    """One immediate cross-process admission decision."""

    status: str
    provider_id: str
    reason: str | None
    lease: ProviderProcessLease | None

    def __post_init__(self) -> None:
        if self.status not in {"admitted", "deferred"}:
            raise ValueError("provider process admission status is invalid")
        if normalize_provider_id(self.provider_id) != self.provider_id:
            raise ValueError("provider process admission provider ID is invalid")
        if self.status == "admitted":
            if self.reason is not None or not isinstance(self.lease, ProviderProcessLease):
                raise ValueError("admitted provider process decision requires one lease")
            if self.lease.provider_id != self.provider_id:
                raise ValueError("provider process lease binding is invalid")
        elif self.reason != "concurrency_busy" or self.lease is not None:
            raise ValueError("deferred provider process decision is invalid")


def _is_reparse_or_symlink(path: Path, metadata: os.stat_result | None = None) -> bool:
    details = os.lstat(path) if metadata is None else metadata
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(details.st_mode) or bool(attributes & reparse_flag)


class ProviderProcessGate:
    """Immediate capacity-one admission shared by cooperating OS processes."""

    def __init__(self, root: Path | str, *, id_factory=None) -> None:
        self._root = Path(root)
        if not self._root.is_absolute():
            raise ProviderProcessGateError("provider process gate root must be absolute")
        try:
            metadata = os.lstat(self._root)
        except OSError as error:
            raise ProviderProcessGateError("provider process gate root is unavailable") from error
        if not stat.S_ISDIR(metadata.st_mode) or _is_reparse_or_symlink(self._root, metadata):
            raise ProviderProcessGateError("provider process gate root is unsafe")
        self._id_factory = id_factory or (lambda: secrets.token_hex(12))
        if not callable(self._id_factory):
            raise TypeError("provider process gate ID factory is invalid")
        self._coordinator_token = object()
        self._leases: dict[str, ProviderProcessLease] = {}
        self._lock = threading.Lock()

    def lock_path(self, provider_id: object) -> Path:
        """Return the content-free lock path for one normalized provider ID."""
        normalized = normalize_provider_id(provider_id)
        digest = hashlib.sha256(normalized.encode("ascii")).hexdigest()
        return self._root / f"{PROVIDER_PROCESS_LOCK_PREFIX}{digest}{PROVIDER_PROCESS_LOCK_SUFFIX}"

    def try_acquire(self, provider_id: object) -> ProviderProcessAdmission:
        """Try once to hold one exact provider lease; never wait or execute."""
        normalized = normalize_provider_id(provider_id)
        path = self.lock_path(normalized)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except OSError as error:
            raise ProviderProcessGateError("provider process lock cannot be opened safely") from error
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ProviderProcessGateError("provider process lock file is unsafe")
            if metadata.st_size < 1:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if not self._try_lock(descriptor):
                os.close(descriptor)
                return ProviderProcessAdmission(
                    "deferred", normalized, "concurrency_busy", None,
                )
            lease = ProviderProcessLease(
                coordinator_token=self._coordinator_token,
                descriptor=descriptor,
                lease_id=self._id_factory(),
                provider_id=normalized,
            )
            with self._lock:
                if lease.lease_id in self._leases:
                    self._unlock(descriptor)
                    raise ProviderProcessGateError("provider process lease ID is duplicated")
                self._leases[lease.lease_id] = lease
            return ProviderProcessAdmission("admitted", normalized, None, lease)
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise

    def release(self, lease: object) -> bool:
        """Release only this coordinator's active exact lease."""
        if (
            not isinstance(lease, ProviderProcessLease)
            or lease._coordinator_token is not self._coordinator_token
            or not lease.active
        ):
            return False
        with self._lock:
            if self._leases.get(lease.lease_id) is not lease:
                return False
            try:
                self._unlock(lease._descriptor)
                os.close(lease._descriptor)
            except OSError as error:
                raise ProviderProcessGateError("provider process lease cannot be released") from error
            lease._released = True
            del self._leases[lease.lease_id]
            return True

    @staticmethod
    def _try_lock(descriptor: int) -> bool:
        try:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:  # pragma: no cover - Windows-only standard-library fallback.
                import msvcrt
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return True
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                return False
            raise ProviderProcessGateError("provider process lock cannot be acquired") from error

    @staticmethod
    def _unlock(descriptor: int) -> None:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return
        import msvcrt  # pragma: no cover - Windows-only standard-library fallback.
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)


__all__ = [
    "PROVIDER_PROCESS_GATE_SCHEMA_VERSION", "ProviderProcessAdmission",
    "ProviderProcessGate", "ProviderProcessGateError", "ProviderProcessLease",
]
