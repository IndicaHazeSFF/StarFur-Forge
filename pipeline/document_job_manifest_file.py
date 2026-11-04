"""Bounded POSIX manifest acquisition from an explicitly supplied directory.

No root/model discovery, service, payload export, deployment evidence or consent.
The caller must safely select/open the exact manifest directory separately.
"""
import math
import os
import re
import stat
import sys
import time

from pipeline.document_job_manifest import decode_model_manifest, MAX_MANIFEST_BYTES
from pipeline.document_job_blob_measurement import _identity


class ManifestFileError(ValueError):
    """Content-free manifest acquisition refusal."""


def read_manifest_file(directory_fd, name, *, expected_uid, timeout_seconds,
                       _clock=time.monotonic):
    """Read one basename without following links; return descriptor data only."""
    directory = handle = None
    try:
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or type(directory_fd) is not int or directory_fd < 0
                or type(name) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name) is None
                or type(expected_uid) is not int or expected_uid < 0
                or type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or not 0 < timeout_seconds <= 120 or not callable(_clock)):
            raise ValueError
        previous = None
        def now():
            nonlocal previous
            value = _clock()
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or (previous is not None and value < previous)):
                raise ValueError
            previous = value
            return value
        started = now()
        def remaining():
            if now() - started >= timeout_seconds:
                raise ValueError
        directory = os.dup(directory_fd)
        root = os.fstat(directory)
        if (not stat.S_ISDIR(root.st_mode) or root.st_uid != expected_uid or root.st_mode & 0o022):
            raise ValueError
        remaining()
        entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1
                or entry.st_uid != expected_uid or entry.st_mode & 0o022
                or not 2 <= entry.st_size <= MAX_MANIFEST_BYTES):
            raise ValueError
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(handle)
        if (_identity(before) != _identity(entry) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != expected_uid or before.st_mode & 0o022
                or not 2 <= before.st_size <= MAX_MANIFEST_BYTES):
            raise ValueError
        if _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _identity(before):
            raise ValueError
        parts = []
        size = 0
        while True:
            remaining()
            part = os.read(handle, min(16384, MAX_MANIFEST_BYTES+1-size))
            remaining()
            if not part:
                break
            size += len(part)
            if size > MAX_MANIFEST_BYTES or size > before.st_size:
                raise ValueError
            parts.append(part)
        if size != before.st_size:
            raise ValueError
        parsed = decode_model_manifest(b"".join(parts))
        if (_identity(os.fstat(handle)) != _identity(before)
                or _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _identity(before)
                or _identity(os.fstat(directory)) != _identity(root)):
            raise ValueError
        remaining()
        return parsed
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        raise ManifestFileError("model manifest acquisition failed") from None
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
            raise ManifestFileError("model manifest acquisition failed") from None
