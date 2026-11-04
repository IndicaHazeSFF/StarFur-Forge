"""Disconnected POSIX single-blob measurement; no locality or consent authority.

The trusted caller supplies an already safely opened blobs directory and owner.
This does not discover paths, validate a deployment or isolate hostile writers.
Time limits fence acceptance; a blocked kernel read is not forcibly terminated.
"""
import math
import os
import stat
import sys
import time
from hashlib import sha256

from pipeline.document_job_manifest import (
    ManifestBlobDescriptor, ParsedModelManifest, MAX_BLOB_BYTES, MAX_TOTAL_BYTES,
)


class BlobMeasurementError(ValueError):
    """Content-free measurement refusal."""


def measure_blob_set(directory_fd, manifest, *, expected_uid, max_bytes,
                     timeout_seconds, _clock=time.monotonic):
    """Measure all supplied descriptors under one byte/time acceptance budget.

    The manifest is already-decoded data, not an attested on-disk manifest. The
    caller still owns trusted root selection, config validation and deployment
    admission. Return ordered hashes only, no payload or readiness evidence.
    """
    directory = None
    try:
        if (type(manifest) is not ParsedModelManifest
                or type(directory_fd) is not int or directory_fd < 0
                or type(expected_uid) is not int or expected_uid < 0
                or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_TOTAL_BYTES
                or type(timeout_seconds) not in (int, float)
                or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120
                or not callable(_clock) or os.name != "posix"):
            raise ValueError
        ParsedModelManifest(manifest.raw_bytes_sha256, manifest.config,
                            manifest.layers, manifest.declared_total)
        if manifest.declared_total > max_bytes:
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
            result = timeout_seconds - (now() - started)
            if result <= 0:
                raise ValueError
            return result
        directory = os.dup(directory_fd)
        root = os.fstat(directory)
        if (not stat.S_ISDIR(root.st_mode) or root.st_uid != expected_uid
                or root.st_mode & 0o022):
            raise ValueError
        descriptors = (manifest.config, *manifest.layers)
        for item in descriptors:
            ManifestBlobDescriptor(item.media_type, item.digest, item.size)
        names = tuple(item.digest.replace(":", "-", 1) for item in descriptors)
        before = []
        for name, item in zip(names, descriptors):
            remaining()
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != expected_uid
                    or info.st_nlink != 1 or info.st_mode & 0o022 or info.st_size != item.size):
                raise ValueError
            before.append(_identity(info))
        measured = []
        for descriptor in descriptors:
            measured.append(measure_blob(directory, descriptor, expected_uid=expected_uid,
                                         max_bytes=descriptor.size,
                                         timeout_seconds=remaining(), _clock=now))
        # Recheck earlier files too: a later measurement must not hide a change
        # to an earlier blob. These remain trusted-host change indicators.
        for name, identity in zip(names, before):
            remaining()
            if _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != identity:
                raise ValueError
        if _identity(os.fstat(directory)) != _identity(root):
            raise ValueError
        remaining()
        return tuple(measured)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        raise BlobMeasurementError("model blob measurement failed") from None
    finally:
        if directory is not None:
            active_failure = sys.exception() is not None
            try:
                os.close(directory)
            except OSError:
                if not active_failure:
                    raise BlobMeasurementError("model blob measurement failed") from None


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def measure_blob(directory_fd, descriptor, *, expected_uid, max_bytes,
                 timeout_seconds, _clock=time.monotonic):
    """Return measured SHA-256 only after exact descriptor equality checks.

    No opening by arbitrary path, writing, payload return, readiness, provider or
    verification boolean. All referenced artifacts/config/runner checks remain
    separate. Trusted clock injection is a test seam, not plugin isolation.
    """
    directory = blob = None
    try:
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or type(directory_fd) is not int or directory_fd < 0
                or type(descriptor) is not ManifestBlobDescriptor
                or type(expected_uid) is not int or expected_uid < 0
                or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BLOB_BYTES
                or descriptor.size > max_bytes
                or type(timeout_seconds) not in (int, float)
                or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120
                or not callable(_clock)):
            raise ValueError
        # Revalidate even an object altered through trusted Python reflection.
        ManifestBlobDescriptor(descriptor.media_type, descriptor.digest, descriptor.size)
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
        if (not stat.S_ISDIR(root.st_mode) or root.st_uid != expected_uid
                or root.st_mode & 0o022):
            raise ValueError
        name = descriptor.digest.replace(":", "-", 1)
        remaining()
        blob = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(blob)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != expected_uid or before.st_mode & 0o022
                or before.st_size != descriptor.size):
            raise ValueError
        if _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _identity(before):
            raise ValueError
        digest = sha256()
        read = 0
        while True:
            remaining()
            part = os.read(blob, min(65536, descriptor.size + 1 - read))
            remaining()
            if not part:
                break
            read += len(part)
            if read > descriptor.size or read > max_bytes:
                raise ValueError
            digest.update(part)
        if (read != descriptor.size or digest.hexdigest() != descriptor.digest[7:]
                or _identity(os.fstat(blob)) != _identity(before)
                or _identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != _identity(before)
                or _identity(os.fstat(directory)) != _identity(root)):
            raise ValueError
        remaining()
        return digest.hexdigest()
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        raise BlobMeasurementError("model blob measurement failed") from None
    finally:
        # Attempt both cleanups even if one close fails. Never return a measured
        # hash after uncertain cleanup, or expose raw OS/path error text.
        cleanup_failed = False
        for handle in (blob, directory):
            if handle is not None:
                try:
                    os.close(handle)
                except OSError:
                    cleanup_failed = True
        if cleanup_failed and sys.exception() is None:
            raise BlobMeasurementError("model blob measurement failed") from None
