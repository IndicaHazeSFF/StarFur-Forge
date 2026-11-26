"""Read metadata only for an already-owned synthetic pipe descriptor."""

import os
import stat
import sys

from scripts.private_worker_cooperative_fds import DescriptorReviewError, Direction, PipeEnd


def observe_owned_pipe_end(fd, *, created_identity):
    """Check a descriptor against its caller-owned anonymous creation record.

    The caller must hold the exact handle exclusively across inspection and
    handoff, with no concurrent close/dup or reuse. FIFO metadata plus an inode
    is not proof of anonymous provenance, exclusive ownership, or inventory
    completeness. No open, close, read, write, or flag mutation is performed.
    """
    def require(ok):
        if not ok:
            raise DescriptorReviewError("owned cooperative pipe inspection refused")

    require(sys.platform == "linux" and type(fd) is int and 0 <= fd < (1 << 31)
            and type(created_identity) is tuple and len(created_identity) == 2
            and all(type(n) is int and 0 <= n < (1 << 64) for n in created_identity)
            and created_identity[1] != 0)
    try:
        import fcntl

        def check_type():
            info = os.fstat(fd)
            require(stat.S_ISFIFO(info.st_mode) and (info.st_dev, info.st_ino) == created_identity)

        check_type()
        status = fcntl.fcntl(fd, fcntl.F_GETFL)
        descriptor = fcntl.fcntl(fd, fcntl.F_GETFD)
        mode = status & os.O_ACCMODE
        require(mode in (os.O_RDONLY, os.O_WRONLY)
                and status & ~(os.O_ACCMODE | os.O_NONBLOCK) == 0
                and descriptor in (0, fcntl.FD_CLOEXEC))
        check_type()
        require(fcntl.fcntl(fd, fcntl.F_GETFL) == status
                and fcntl.fcntl(fd, fcntl.F_GETFD) == descriptor)
    except (OSError, ImportError):
        raise DescriptorReviewError("owned cooperative pipe inspection refused") from None

    direction = Direction.READ if mode == os.O_RDONLY else Direction.WRITE
    return PipeEnd(fd, *created_identity, direction, descriptor == fcntl.FD_CLOEXEC, True)
