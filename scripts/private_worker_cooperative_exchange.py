"""Test-only cooperative exchanges, not a launcher or supervisor."""

from enum import Enum, auto
import os
import select
import sys
import time

from scripts.private_worker_cooperative_maps import ChildHandles, _pending, observe_cooperative_maps
from scripts.private_worker_mapping_observer import MappingObservation, MappingObservationError


def _fd(fd):
    return type(fd) is int and 0 <= fd < (1 << 31)


def _require(ok):
    if not ok:
        raise MappingObservationError("cooperative exchange refused")


class _Deadline:
    def __init__(self, expires):
        _require(type(expires) is int and expires >= 0)
        self.expires = expires
        self.previous = -1

    def remaining(self):
        now = time.monotonic_ns()
        _require(self.previous <= now < self.expires)
        self.previous = now
        return self.expires - now

    def poll(self, poller, fd, *, allowed):
        timeout = min((self.remaining() + 999_999) // 1_000_000, (1 << 31) - 1)
        events = poller.poll(timeout)
        self.remaining()
        _require(len(events) == 1 and events[0][0] == fd and events[0][1] != 0
                 and events[0][1] & ~allowed == 0)


def _readiness_reader(fd, deadline):
    deadline.remaining()
    _require(os.get_blocking(fd) is False)
    poller = select.poll()
    allowed = select.POLLIN | select.POLLHUP
    poller.register(fd, allowed)

    def read_ready(limit):
        deadline.poll(poller, fd, allowed=allowed)
        data = os.read(fd, limit)
        deadline.remaining()
        _require(type(data) is bytes and len(data) <= limit)
        return data

    return read_ready


class ReleaseState(Enum):
    UNUSED = auto()
    NO_WRITE = auto()
    WRITE_UNCONFIRMED = auto()
    BYTE_WRITTEN = auto()


class ReleaseAttempt:
    """One-shot bookkeeping owned by the sole parent for exactly one case.

    Not thread-safe or persistent. BYTE_WRITTEN only confirms the local
    write, not delivery, on-time acceptance, exit or cleanup.
    """

    __slots__ = ("_state",)

    def __init__(self):
        self._state = ReleaseState.UNUSED

    @property
    def state(self):
        return self._state


def capture_and_release(*, child, ready_reader, release_writer, deadline_ns, identity, segments,
                        attempt):
    """Borrow verified, exclusively owned channels and child handles.

    The trusted parent owns exact pipe creation, inventory, bound lifetime,
    watchdog, and cleanup. This positive-only path consumes readiness and
    will not retry a failed or ambiguous operation. The write is not an
    overall success receipt: require reaping, negative control, and cleanup.
    No live caller is connected.
    """
    _require(type(attempt) is ReleaseAttempt and attempt.state is ReleaseState.UNUSED)
    attempt._state = ReleaseState.NO_WRITE
    _require(sys.platform == "linux" and type(child) is ChildHandles)
    fds = (ready_reader, release_writer, child.pidfd, child.task_dir)
    _require(all(_fd(fd) for fd in fds) and len(set(fds)) == len(fds))
    deadline = _Deadline(deadline_ns)

    try:
        read_ready = _readiness_reader(ready_reader, deadline)
        _require(os.get_blocking(release_writer) is False)
        _require(read_ready(2) == b"R")
        _require(read_ready(1) == b"")
        result = observe_cooperative_maps(
            child.task_dir, child_pidfd=child.pidfd, task_identity=child.task_identity,
            deadline_ns=deadline_ns, identity=identity, segments=segments,
        )
        _require(type(result) is MappingObservation and _pending(child.pidfd))
        deadline.remaining()
        attempt._state = ReleaseState.WRITE_UNCONFIRMED
        _require(os.write(release_writer, b"G") == 1)
        attempt._state = ReleaseState.BYTE_WRITTEN
        deadline.remaining()
        return result
    except (OSError, AttributeError, MappingObservationError):
        raise MappingObservationError("cooperative release refused") from None


def observe_missing_leaf(*, child_pidfd, ready_reader, deadline_ns):
    """Require empty readiness and observe exit 127 without consuming status.

    Only the trusted sole parent/reaper may call this with an already-bound
    negative child and its verified nonblocking readiness end. It receives
    no release handle. Regardless of result the parent still owns the reap;
    this observation is not a final receipt.
    """
    _require(sys.platform == "linux" and _fd(child_pidfd) and _fd(ready_reader)
             and child_pidfd != ready_reader)
    deadline = _Deadline(deadline_ns)
    try:
        _require(_readiness_reader(ready_reader, deadline)(1) == b"")
        poller = select.poll()
        poller.register(child_pidfd, select.POLLIN)
        deadline.poll(poller, child_pidfd, allowed=select.POLLIN)
        exited = os.waitid(os.P_PIDFD, child_pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        deadline.remaining()
        _require(exited is not None and exited.si_code == os.CLD_EXITED
                 and exited.si_status == 127)
    except (OSError, AttributeError, MappingObservationError):
        raise MappingObservationError("cooperative missing-leaf control refused") from None
