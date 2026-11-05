"""Bounded exact config-blob read/decode; no raw payload or deployment authority."""
import math
import os
import stat
import sys
import time

from pipeline.document_job_blob_measurement import _identity
from pipeline.document_job_config import decode_model_config
from pipeline.document_job_manifest import ParsedModelManifest, ManifestBlobDescriptor, MAX_MANIFEST_BYTES


class ConfigFileError(ValueError):
    """Content-free config acquisition refusal."""


def read_model_config(directory_fd, manifest, *, expected_uid, timeout_seconds,
                      _clock=time.monotonic):
    """Read exact config descriptor under caller-trusted blobs-directory handle.

    Return validated metadata only. Caller still owns root/model mapping,
    deployment acceptance, surrounding artifact freshness and disclosure consent.
    Deadline bounds acceptance, not forced termination of blocked kernel reads.
    """
    directory = handle = None
    try:
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or type(directory_fd) is not int or directory_fd < 0
                or type(manifest) is not ParsedModelManifest
                or type(expected_uid) is not int or expected_uid < 0
                or type(timeout_seconds) not in (int, float)
                or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120
                or not callable(_clock)):
            raise ValueError
        ParsedModelManifest(manifest.raw_bytes_sha256, manifest.config, manifest.layers, manifest.declared_total)
        item = manifest.config
        ManifestBlobDescriptor(item.media_type, item.digest, item.size)
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
            if now()-started >= timeout_seconds:
                raise ValueError
        directory = os.dup(directory_fd)
        root = os.fstat(directory)
        if not stat.S_ISDIR(root.st_mode) or root.st_uid != expected_uid or root.st_mode & 0o022:
            raise ValueError
        name = item.digest.replace(":", "-", 1)
        remaining()
        entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != expected_uid
                or entry.st_nlink != 1 or entry.st_mode & 0o022 or entry.st_size != item.size
                or not 2 <= entry.st_size <= MAX_MANIFEST_BYTES):
            raise ValueError
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        if _identity(os.fstat(handle)) != _identity(entry):
            raise ValueError
        parts = []; size = 0
        while True:
            remaining()
            part = os.read(handle, min(16384, item.size+1-size))
            remaining()
            if not part:
                break
            size += len(part)
            if size > item.size:
                raise ValueError
            parts.append(part)
        if size != item.size:
            raise ValueError
        metadata = decode_model_config(b"".join(parts), manifest)
        if (_identity(os.fstat(handle)) != _identity(entry)
                or _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _identity(entry)
                or _identity(os.fstat(directory)) != _identity(root)):
            raise ValueError
        remaining()
        return metadata
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        raise ConfigFileError("model config acquisition failed") from None
    finally:
        active_failure = sys.exception() is not None
        failed = False
        for fd in (handle, directory):
            if fd is not None:
                try: os.close(fd)
                except OSError: failed = True
        if failed and not active_failure:
            raise ConfigFileError("model config acquisition failed") from None
