"""Synthetic x86-64 cwd-guard bytecode; explicit C5-only self installation.

Adds chdir/fchdir EPERM to the existing negative synthetic guard. Unknown calls
still allow. This is not production policy, a locked cwd, filesystem isolation,
or evidence of initial cwd/FS-sharing/immutable-root/exec enforcement.
Native C5 installation needs separately reviewed code and separate approval;
no Core/provider caller or automatic installation exists.
"""
import importlib.util
import ctypes
import re
from pathlib import Path

spec = importlib.util.spec_from_file_location("cwd_synthetic_base", Path(__file__).with_name("private_worker_syscall_policy.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

POLICY = "synthetic-cwd-guard-x86-v1"
CHDIR = 80
FCHDIR = 81
CLONE_FS = 0x200


def program():
    """Pure bounded cBPF tuples, no OS calls, installation or verification."""
    original = base.program()
    if type(original) is not tuple or not original or original[-1] != (0x06, 0, 0, base.ALLOW):
        raise ValueError("cwd guard composition is unavailable")
    # Reload syscall number: preceding family/clone branches can load arguments.
    tail = ((0x20, 0, 0, 0), (0x15, 0, 1, CHDIR), (0x06, 0, 0, base.DENY),
            (0x15, 0, 1, FCHDIR), (0x06, 0, 0, base.DENY), original[-1])
    result = original[:-1] + tail
    if len(result) > 128:
        raise ValueError("cwd guard composition is unavailable")
    return result


def verify_abi():
    """Explicit fixed public-header preflight before detaching the host root."""
    base.verify_abi()
    header = Path("/usr/include/x86_64-linux-gnu/asm/unistd_64.h").read_text()
    for name, number in (("fstat", 5), ("getcwd", 79), ("chdir", CHDIR), ("fchdir", FCHDIR), ("unshare", 272)):
        if not re.search(rf"^#define __NR_{name} {number}$", header, re.M):
            raise ValueError("cwd_abi_unverified")
    sched = Path("/usr/include/linux/sched.h").read_text()
    found = re.search(r"^#define\s+CLONE_FS\s+(0x[0-9a-fA-F]+)", sched, re.M)
    if found is None or int(found[1], 16) != CLONE_FS:
        raise ValueError("cwd_abi_unverified")


def install(lib):
    """Explicit one-thread/no-new-privs synthetic C5 operation, not readiness."""
    if ctypes.sizeof(base.SockFilter) != 8 or ctypes.sizeof(base.SockFprog) != 16:
        raise ValueError("filter_abi_unverified")
    if len(list(Path("/proc/self/task").iterdir())) != 1:
        raise ValueError("single_thread_required")
    if lib.prctl(39, 0, 0, 0, 0) != 1:
        raise ValueError("no_new_privileges_required")
    rows = program(); storage = base.FilterArray()
    for i, row in enumerate(rows): storage[i] = base.SockFilter(*row)
    descriptor = base.SockFprog(len(rows), ctypes.cast(storage, ctypes.POINTER(base.SockFilter)))
    if lib.syscall(ctypes.c_long(base.NUMBERS["seccomp"]), ctypes.c_long(1), ctypes.c_long(0), ctypes.byref(descriptor)) != 0:
        raise ValueError("filter_install_failed")
    if lib.prctl(21, 0, 0, 0, 0) != 2:
        raise ValueError("filter_state_unverified")
