"""Exclusive receipt for the single cooperative synthetic test approval.

No directory acquisition, launcher or caller. A receipt is not approval;
the controller must independently hold the exact grant and stable anchor.
"""

import os
import re
import stat
import sys


RECEIPT = "c8l-cooperative-approval.spent"


class ChargeRefused(ValueError):
    """No submission is permitted by this result."""


def charge_once(directory_fd, *, directory_identity, attempt, scope_digest):
    """Durably charge before submission using a borrowed Linux directory fd.

    The caller owns the already durable, test-only directory location,
    trusted identity, and continuity across process restart. It must not
    recreate/replace the directory or infer approval from absence. An
    existing entry of any kind (including empty) refuses. No unlink, reset,
    retry, or inference about whether a manager request was sent.
    """
    def need(ok):
        if not ok:
            raise ChargeRefused("cooperative approval charge refused")

    need(sys.platform == "linux" and type(directory_fd) is int and directory_fd >= 0
         and type(directory_identity) is tuple and len(directory_identity) == 2
         and all(type(n) is int and n >= 0 for n in directory_identity)
         and directory_identity[1] != 0
         and type(attempt) is str and re.fullmatch(r"[0-9a-f]{32}", attempt) is not None
         and attempt != "0" * 32
         and type(scope_digest) is str
         and re.fullmatch(r"[0-9a-f]{64}", scope_digest) is not None
         and scope_digest != "0" * 64)
    payload = f"starfur-c8l-charge-v1\n{attempt}\n{scope_digest}\n".encode("ascii")
    uid = os.geteuid()

    def check_anchor():
        s = os.fstat(directory_fd)
        need((s.st_dev, s.st_ino) == directory_identity and stat.S_ISDIR(s.st_mode)
             and s.st_uid == uid and stat.S_IMODE(s.st_mode) == 0o700)

    try:
        check_anchor()
        fd = os.open(RECEIPT, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
        try:
            need(os.write(fd, payload) == len(payload))
            os.fsync(fd)
            os.fsync(directory_fd)
            s = os.fstat(fd)
            entry = os.stat(RECEIPT, dir_fd=directory_fd, follow_symlinks=False)
            need(stat.S_ISREG(s.st_mode) and s.st_mode == entry.st_mode
                 and stat.S_IMODE(s.st_mode) == 0o600 and s.st_uid == entry.st_uid == uid
                 and s.st_dev == entry.st_dev == directory_identity[0]
                 and s.st_ino == entry.st_ino and s.st_nlink == entry.st_nlink == 1
                 and s.st_size == entry.st_size == len(payload))
            check_anchor()
        finally:
            os.close(fd)
    except OSError:
        raise ChargeRefused("cooperative approval charge refused") from None
