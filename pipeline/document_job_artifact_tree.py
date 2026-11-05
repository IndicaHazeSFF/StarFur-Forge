"""Explicit anchored POSIX model-tree measurement, disconnected from processing.

The trusted caller selects/opens the anchor. No environment/default-root lookup,
directory discovery, installed-model access, service, config interpretation or
locality/consent authority. Owner/stat checks assume a trusted local host; they
are not mount-namespace isolation or protection against hostile same-user/root.
"""
import math
import os
import re
import stat
import sys
import time

from pipeline.document_job_blob_measurement import measure_blob_set, _identity
from pipeline.document_job_manifest import MAX_TOTAL_BYTES
from pipeline.document_job_manifest_file import read_manifest_file
from pipeline.document_job_config_file import read_model_config


class ArtifactTreeError(ValueError):
    """Content-free anchored-tree refusal."""


_PART = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")


def measure_model_tree(anchor_fd, root_parts, model, *, expected_uid, max_bytes,
                       timeout_seconds, _clock=time.monotonic):
    """Measure one exact short model:tag below an explicit trusted anchor.

    root_parts is an exact tuple of 1..8 lowercase basenames, not an absolute
    path. Initial policy supports only registry.ollama.ai/library/model/tag;
    explicit host/namespace/digest forms, implicit tags and cloud labels deny.
    This is local storage layout, not permission to access that registry.
    Return (ParsedModelManifest, ordered blob hashes). No paths/payloads escape.
    """
    return _measure_model_tree(anchor_fd, root_parts, model, expected_uid=expected_uid,
                               max_bytes=max_bytes, timeout_seconds=timeout_seconds,
                               _clock=_clock, _with_config=False)


def inspect_model_tree_config(anchor_fd, root_parts, model, *, expected_uid, max_bytes,
                              timeout_seconds, _clock=time.monotonic):
    """Explicit stronger observation: measure tree AND decode exact config bytes.

    Returns (manifest, blob hashes, config metadata), never private-job readiness.
    max_bytes is the logical blob hash budget; two config reads add at most
    128 KiB bounded overhead, besides two bounded manifest reads, under the same
    acceptance deadline. No optional behavior is silently added to measurement.
    """
    return _measure_model_tree(anchor_fd, root_parts, model, expected_uid=expected_uid,
                               max_bytes=max_bytes, timeout_seconds=timeout_seconds,
                               _clock=_clock, _with_config=True)


def _measure_model_tree(anchor_fd, root_parts, model, *, expected_uid, max_bytes,
                        timeout_seconds, _clock, _with_config):
    handles = []
    try:
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or type(anchor_fd) is not int or anchor_fd < 0
                or type(root_parts) is not tuple or not 1 <= len(root_parts) <= 8
                or any(type(p) is not str or _PART.fullmatch(p) is None for p in root_parts)
                or type(model) is not str or len(model) > 128 or model.count(":") != 1
                or type(expected_uid) is not int or expected_uid < 0
                or type(max_bytes) is not int or not 1 <= max_bytes <= MAX_TOTAL_BYTES
                or type(timeout_seconds) not in (int, float)
                or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 120
                or not callable(_clock)):
            raise ValueError
        family, tag = model.split(":")
        if (_PART.fullmatch(family) is None or _PART.fullmatch(tag) is None
                or "cloud" in re.split(r"[:._-]", model)):
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
            value = timeout_seconds - (now() - started)
            if value <= 0:
                raise ValueError
            return value
        def valid(info, device):
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != expected_uid
                    or info.st_mode & 0o022 or info.st_dev != device):
                raise ValueError
        anchor = os.dup(anchor_fd)
        handles.append(anchor)
        initial = os.fstat(anchor)
        valid(initial, initial.st_dev)
        chain = []
        def child(parent, name):
            remaining()
            entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
            valid(entry, initial.st_dev)
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=parent)
            handles.append(fd)
            opened = os.fstat(fd)
            valid(opened, initial.st_dev)
            if _identity(opened) != _identity(entry):
                raise ValueError
            chain.append((parent, name, fd, _identity(opened)))
            return fd
        root = anchor
        for part in root_parts:
            root = child(root, part)
        blobs = child(root, "blobs")
        current = root
        for part in ("manifests", "registry.ollama.ai", "library", family):
            current = child(current, part)
        # Bind the exact manifest inode, not just identical content, across all
        # blob work. The reader separately validates its entry/handle equality.
        manifest_entry = os.stat(tag, dir_fd=current, follow_symlinks=False)
        parsed = read_manifest_file(current, tag, expected_uid=expected_uid,
                                    timeout_seconds=remaining(), _clock=now)
        members = ()
        metadata = None
        if _with_config:
            if parsed.declared_total > max_bytes:
                raise ValueError
            members = tuple((item.digest.replace(":", "-", 1),
                             _identity(os.stat(item.digest.replace(":", "-", 1),
                                               dir_fd=blobs, follow_symlinks=False)))
                            for item in (parsed.config, *parsed.layers))
            metadata = read_model_config(blobs, parsed, expected_uid=expected_uid,
                                         timeout_seconds=remaining(), _clock=now)
        measured = measure_blob_set(blobs, parsed, expected_uid=expected_uid,
                                    max_bytes=max_bytes, timeout_seconds=remaining(), _clock=now)
        if _with_config:
            repeated_config = read_model_config(blobs, parsed, expected_uid=expected_uid,
                                                timeout_seconds=remaining(), _clock=now)
            if repeated_config != metadata:
                raise ValueError
        repeated = read_manifest_file(current, tag, expected_uid=expected_uid,
                                      timeout_seconds=remaining(), _clock=now)
        if (repeated != parsed or _identity(os.stat(tag, dir_fd=current, follow_symlinks=False))
                != _identity(manifest_entry)):
            raise ValueError
        for parent, name, fd, identity in chain:
            remaining()
            if (_identity(os.fstat(fd)) != identity
                    or _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity):
                raise ValueError
        if _identity(os.fstat(anchor)) != _identity(initial):
            raise ValueError
        for name, identity in members:
            remaining()
            if _identity(os.stat(name, dir_fd=blobs, follow_symlinks=False)) != identity:
                raise ValueError
        remaining()
        return (parsed, measured, metadata) if _with_config else (parsed, measured)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        raise ArtifactTreeError("model artifact tree measurement failed") from None
    finally:
        active_failure = sys.exception() is not None
        failed = False
        for fd in reversed(handles):
            try:
                os.close(fd)
            except OSError:
                failed = True
        if failed and not active_failure:
            raise ArtifactTreeError("model artifact tree measurement failed") from None
