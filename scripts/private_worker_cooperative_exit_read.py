"""One exit-info query on a caller-held synthetic worker pidfd; no live caller."""

import os
import select
import struct
import sys
import time

from scripts.private_worker_cooperative_exit_abi import (
    EXIT_BIT, INFO_SIZE, ExitInfoRefused, decode_exit_status,
)
from scripts.private_worker_cooperative_startup import Binding, WorkerExit


INFO_REQUEST = (3 << 30) | (INFO_SIZE << 16) | (0xFF << 8) | 11


def observe_worker_exit(pidfd, *, expected_identity, binding, expires_ns):
    """Borrow, never own, the exact pre-go pidfd on the reviewed x86-64 ABI.

    The sole caller must already establish ABI support, process/case binding
    and descriptor continuity through this call. Its identity pin is an
    additional consistency check, not proof of ownership or provenance.
    No open, close, wait, signal, retry, or terminal/cleanup decision.
    """
    def need(ok):
        if not ok:
            raise ExitInfoRefused("cooperative worker exit query refused")

    need(sys.platform == "linux" and sys.byteorder == "little"
         and type(pidfd) is int and 0 <= pidfd < 1 << 31
         and type(binding) is Binding and type(expires_ns) is int and expires_ns > 0
         and type(expected_identity) is tuple and len(expected_identity) == 2
         and all(type(n) is int and 0 <= n < 1 << 64 for n in expected_identity)
         and expected_identity[1] > 0)
    previous = -1

    def fence():
        nonlocal previous
        now = time.monotonic_ns()
        need(previous <= now < expires_ns)
        previous = now
        return now

    def check_handle():
        info = os.fstat(pidfd)
        need((info.st_dev, info.st_ino) == expected_identity and not os.get_inheritable(pidfd))

    try:
        import fcntl

        need(os.uname().machine == "x86_64")
        fence()
        check_handle()
        poller = select.poll()
        poller.register(pidfd, select.POLLIN)
        events = poller.poll(0)
        need(len(events) == 1 and events[0][0] == pidfd
             and events[0][1] & select.POLLIN
             and not events[0][1] & ~(select.POLLIN | select.POLLHUP))
        fence()
        buffer = bytearray(INFO_SIZE)
        struct.pack_into("<Q", buffer, 0, EXIT_BIT)
        need(fcntl.ioctl(pidfd, INFO_REQUEST, buffer, True) == 0)
        at = fence()
        status = decode_exit_status(bytes(buffer))
        check_handle()
        fence()
        return WorkerExit(binding, at, True, True, status)
    except (OSError, ImportError, AttributeError):
        raise ExitInfoRefused("cooperative worker exit query refused") from None
