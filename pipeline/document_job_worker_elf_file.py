"""Explicit POSIX ELF acquisition under a caller-trusted directory handle.

Read-only, one exact basename, bounded bytes/time acceptance and identity checks.
Return dependency/stat metadata only; no payload, root discovery, link following,
image creation, loader execution, installed-library resolution or launch caller.
Trusted-host stat observations are not hostile-writer/OS isolation or admission.
"""
from dataclasses import dataclass
import math
import os
import re
import stat
import sys
import time

from pipeline.document_job_blob_measurement import _identity
from pipeline.document_job_worker_elf import ElfDependencies, MAX_ELF_BYTES, inspect_worker_elf
from pipeline.document_job_worker_elf import _inspect_metadata, _parse_metadata
from pipeline.document_job_worker_elf_search import WorkerElfSearchReview, _make_review
from pipeline.document_job_worker_elf_soname import WorkerElfSonameReview


class WorkerElfFileError(ValueError):
    """Content-free acquisition refusal."""


@dataclass(frozen=True, slots=True, repr=False)
class WorkerElfFileObservation:
    dependencies: ElfDependencies
    identity: tuple[int, ...]

    def __post_init__(self):
        if (type(self.dependencies) is not ElfDependencies or type(self.identity) is not tuple
                or len(self.identity) != 8 or any(type(v) is not int for v in self.identity)):
            raise WorkerElfFileError("worker ELF acquisition is unavailable")
        ElfDependencies(self.dependencies.raw_sha256, self.dependencies.object_kind,
                        self.dependencies.interpreter, self.dependencies.needed)
        dev, ino, mode, uid, links, size, _, _ = self.identity
        if (dev < 0 or ino <= 0 or uid < 0 or links != 1 or not stat.S_ISREG(mode)
                or mode & 0o7022 or not 64 <= size <= MAX_ELF_BYTES):
            raise WorkerElfFileError("worker ELF acquisition is unavailable")


@dataclass(frozen=True, slots=True, repr=False)
class WorkerElfReviewObservation:
    file: WorkerElfFileObservation
    search: WorkerElfSearchReview

    def __post_init__(self):
        if type(self.file) is not WorkerElfFileObservation or type(self.search) is not WorkerElfSearchReview:
            raise WorkerElfFileError("worker ELF acquisition is unavailable")
        WorkerElfFileObservation(self.file.dependencies, self.file.identity)
        WorkerElfSearchReview(self.search.raw_sha256, self.search.category, self.search.tags)
        if self.file.dependencies.raw_sha256 != self.search.raw_sha256:
            raise WorkerElfFileError("worker ELF acquisition is unavailable")


@dataclass(frozen=True, slots=True, repr=False)
class WorkerElfIdentityObservation:
    file: WorkerElfFileObservation
    search: WorkerElfSearchReview
    soname: WorkerElfSonameReview

    def __post_init__(self):
        WorkerElfReviewObservation(self.file, self.search)
        if type(self.soname) is not WorkerElfSonameReview:
            raise WorkerElfFileError("worker ELF acquisition is unavailable")
        WorkerElfSonameReview(self.soname.raw_sha256, self.soname.soname)
        if self.file.dependencies.raw_sha256 != self.soname.raw_sha256:
            raise WorkerElfFileError("worker ELF acquisition is unavailable")


def inspect_worker_elf_file(directory_fd, name, *, expected_uid, max_bytes,
                            timeout_seconds, _clock=time.monotonic):
    """Strict C2 acquisition: every RPATH/RUNPATH remains refused."""
    return _acquire(directory_fd, name, expected_uid=expected_uid, max_bytes=max_bytes,
                    timeout_seconds=timeout_seconds, _clock=_clock, review=False)


def review_worker_elf_file(directory_fd, name, *, expected_uid, max_bytes,
                           timeout_seconds, _clock=time.monotonic):
    """Explicit metadata review; search classification is NOT loading eligibility.

    Unsupported search strings may be described, never accepted or returned.
    Same no-follow/owner/device/identity/byte/deadline checks as strict C2.
    No root selection, image copy, loader, deployment or consent authority.
    """
    return _acquire(directory_fd, name, expected_uid=expected_uid, max_bytes=max_bytes,
                    timeout_seconds=timeout_seconds, _clock=_clock, review=True)


def review_worker_elf_identity_file(directory_fd, name, *, expected_uid, max_bytes,
                                    timeout_seconds, _clock=time.monotonic):
    """Observe file/dependencies/search/SONAME from one exact acquired byte set.

    Same anchored read and final identity/deadline/cleanup fences; no alias,
    loader/image/CPU acceptance, discovery, permission or public runtime caller.
    """
    return _acquire(directory_fd, name, expected_uid=expected_uid, max_bytes=max_bytes,
                    timeout_seconds=timeout_seconds, _clock=_clock,
                    review=True, identity_review=True)


def _acquire(directory_fd, name, *, expected_uid, max_bytes,
             timeout_seconds, _clock, review, identity_review=False):
    """Read one regular no-link ELF and return immutable redacted observation.

    Caller must already trust/open the exact directory; no absolute paths,
    implicit root selection, symlink aliases, subprocess or permission producer.
    Deadline fences acceptance, not cancellation of a blocked kernel read.
    """
    directory = handle = None
    try:
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or type(directory_fd) is not int or directory_fd < 0
                or type(name) is not str or
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", name) is None
                or type(expected_uid) is not int or expected_uid < 0
                or type(max_bytes) is not int or not 64 <= max_bytes <= MAX_ELF_BYTES
                or type(timeout_seconds) not in (int, float) or
                not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120
                or not callable(_clock)):
            raise ValueError
        previous = None
        def now():
            nonlocal previous
            value = _clock()
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or previous is not None and value < previous):
                raise ValueError
            previous = value
            return value
        started = now()
        def remaining():
            if now() - started >= timeout_seconds:
                raise ValueError
        directory = os.dup(directory_fd)
        root = os.fstat(directory)
        if not stat.S_ISDIR(root.st_mode) or root.st_uid != expected_uid or root.st_mode & 0o022:
            raise ValueError
        remaining()
        entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != expected_uid
                or entry.st_nlink != 1 or entry.st_dev != root.st_dev
                or entry.st_mode & 0o7022 or not 64 <= entry.st_size <= max_bytes):
            raise ValueError
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        if _identity(os.fstat(handle)) != _identity(entry):
            raise ValueError
        chunks, total = [], 0
        while True:
            remaining()
            part = os.read(handle, min(65536, entry.st_size + 1 - total))
            remaining()
            if not part:
                break
            total += len(part)
            if total > entry.st_size or total > max_bytes:
                raise ValueError
            chunks.append(part)
        if total != entry.st_size:
            raise ValueError
        raw = b"".join(chunks)
        if review:
            if identity_review:
                metadata, search, soname = _parse_metadata(raw, review_search=True, review_soname=True)
                named = WorkerElfSonameReview(metadata.raw_sha256, soname)
            else:
                metadata, search = _inspect_metadata(raw, review_search=True)
            reviewed = _make_review(metadata, search)
        else:
            metadata = inspect_worker_elf(raw)
        if (_identity(os.fstat(handle)) != _identity(entry) or
                _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _identity(entry)
                or _identity(os.fstat(directory)) != _identity(root)):
            raise ValueError
        remaining()
        observation = WorkerElfFileObservation(metadata, _identity(entry))
        if identity_review:
            return WorkerElfIdentityObservation(observation, reviewed, named)
        return WorkerElfReviewObservation(observation, reviewed) if review else observation
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, RuntimeError, StopIteration):
        raise WorkerElfFileError("worker ELF acquisition is unavailable") from None
    finally:
        active_failure = sys.exception() is not None
        failed = False
        for fd in (handle, directory):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    failed = True
        if failed and not active_failure:
            raise WorkerElfFileError("worker ELF acquisition is unavailable") from None
