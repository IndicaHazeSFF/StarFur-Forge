"""Read bounded synthetic mapping metadata from a caller-owned task anchor."""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import os
import signal
import stat
import sys
import time

from scripts.private_worker_mapping_observer import (
    ACCEPTANCE_NS,
    MAX_BYTES,
    READ_CHUNK,
    MappingObservationError,
    check_cooperative_page_coverage,
)


def _identity_form(value):
    return (type(value) is tuple and len(value) == 2
            and all(type(n) is int and 0 <= n < (1 << 64) for n in value)
            and value[1] > 0)


def _pending(pidfd):
    return os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None


@dataclass(frozen=True, slots=True)
class ChildHandles:
    pidfd: int
    task_dir: int
    task_identity: tuple[int, int]


@contextmanager
def bind_cooperative_child(proc_dir, *, proc_identity, fork_pid, deadline_ns):
    """Pair handles for the sole caller-owned, pre-exec gated direct child.

    A trusted single-threaded parent must supply its own fork result and the
    verified private proc root for its PID namespace. It must exclude all
    other reapers and SA_NOCLDWAIT before fork and through use of the binding.
    Checking Python's SIGCHLD disposition cannot establish that invariant.
    The proc root remains borrowed. This does not fork, control, or reap.
    Do not retain the yielded handles outside the context.
    """
    def require(ok):
        if not ok:
            raise MappingObservationError("cooperative child binding refused")

    require(sys.platform == "linux" and type(proc_dir) is int and proc_dir >= 0
            and _identity_form(proc_identity)
            and type(fork_pid) is int and 1 < fork_pid < (1 << 31)
            and type(deadline_ns) is int and deadline_ns >= 0)
    previous = -1

    def fence():
        nonlocal previous
        now = time.monotonic_ns()
        require(previous <= now < deadline_ns)
        previous = now

    def check_root():
        root = os.fstat(proc_dir)
        require(stat.S_ISDIR(root.st_mode) and (root.st_dev, root.st_ino) == proc_identity)
        fence()

    def close_owned(fd):
        try:
            os.close(fd)
        except OSError:
            raise MappingObservationError("cooperative child handle cleanup refused") from None

    with ExitStack() as owned:
        try:
            fence()
            require(signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL)
            check_root()
            pidfd = os.pidfd_open(fork_pid, 0)
            owned.callback(close_owned, pidfd)
            fence()
            require(_pending(pidfd))
            fence()
            task_dir = os.open(str(fork_pid), os.O_RDONLY | os.O_DIRECTORY
                               | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=proc_dir)
            owned.callback(close_owned, task_dir)
            fence()
            info = os.fstat(task_dir)
            task_identity = (info.st_dev, info.st_ino)
            require(stat.S_ISDIR(info.st_mode) and _identity_form(task_identity)
                    and info.st_dev == proc_identity[0] and task_identity != proc_identity)
            check_root()
            require(_pending(pidfd))
            fence()
        except (OSError, AttributeError):
            raise MappingObservationError("cooperative child binding refused") from None
        yield ChildHandles(pidfd, task_dir, task_identity)


def observe_cooperative_maps(task_dir, *, child_pidfd, task_identity, deadline_ns, identity, segments):
    """Open only maps relative to the supplied, already verified task directory.

    The sole parent/reaper must already have bound the directory to the
    exact same child as the owned pidfd. Keep both handles reserved; use a
    blocking pidfd with a nonblocking, non-reaping wait. A pending child
    at each check is not proof of stable mappings. The caller owns the
    release token and watchdog. Deadlines fence acceptance, not kernel I/O.
    No native caller is connected. Only a redacted comparison is returned.
    """
    def require(ok):
        if not ok:
            raise MappingObservationError("cooperative maps observation refused")

    require(sys.platform == "linux" and type(task_dir) is int and 0 <= task_dir < (1 << 31)
            and type(child_pidfd) is int and 0 <= child_pidfd < (1 << 31)
            and child_pidfd != task_dir
            and _identity_form(task_identity) and type(deadline_ns) is int and deadline_ns >= 0)

    started = time.monotonic_ns()
    previous = started
    expires = min(deadline_ns, started + ACCEPTANCE_NS)

    def fence():
        nonlocal previous
        now = time.monotonic_ns()
        require(previous <= now < expires)
        previous = now

    def check_anchor():
        info = os.fstat(task_dir)
        require(stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == task_identity)
        fence()

    def check_child():
        require(_pending(child_pidfd))
        fence()

    try:
        fence()
        check_anchor()
        check_child()
        fd = os.open("maps", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=task_dir)
        try:
            fence()
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_dev == task_identity[0])
            fence()
            raw = bytearray()
            while True:
                limit = min(READ_CHUNK, MAX_BYTES + 1 - len(raw))
                part = os.read(fd, limit)
                fence()
                require(type(part) is bytes and len(part) <= limit
                        and len(raw) + len(part) <= MAX_BYTES)
                if not part:
                    break
                raw.extend(part)
        finally:
            os.close(fd)
        fence()
        result = check_cooperative_page_coverage(bytes(raw), identity=identity, segments=segments)
        check_anchor()
        check_child()
        return result
    except (OSError, AttributeError, MappingObservationError):
        raise MappingObservationError("cooperative maps observation refused") from None
