"""N2b.2b synthetic x86-64 guard only; NOT a production syscall allowlist.

Pure program construction at import is inert. Only explicit install() changes
the calling test process; no application/provider/worker runtime is connected.
Unlisted syscalls remain allowed: passing this primitive is not sandbox approval.
"""
import ctypes
import errno
from pathlib import Path
import re

ARCH = 0xC000003E
KILL = 0x80000000
ALLOW = 0x7FFF0000
DENY = 0x00050000 | errno.EPERM
ENOSYS = 0x00050000 | errno.ENOSYS
NEW_NAMESPACES = 0x7E020000
NUMBERS = {
    "socket": 41, "socketpair": 53, "clone": 56, "execve": 59,
    "ptrace": 101, "pivot_root": 155, "chroot": 161, "mount": 165,
    "umount2": 166, "unshare": 272, "perf_event_open": 298,
    "name_to_handle_at": 303, "open_by_handle_at": 304, "setns": 308,
    "process_vm_readv": 310, "process_vm_writev": 311, "seccomp": 317,
    "bpf": 321, "execveat": 322, "io_uring_setup": 425,
    "io_uring_enter": 426, "io_uring_register": 427, "open_tree": 428,
    "move_mount": 429, "fsopen": 430, "fsconfig": 431, "fsmount": 432,
    "fspick": 433, "clone3": 435, "pidfd_getfd": 438, "mount_setattr": 442,
}
BLOCKED = tuple(n for name, n in NUMBERS.items()
                if name not in {"socket", "clone", "clone3", "execve", "seccomp"})


class SockFilter(ctypes.Structure):
    _fields_ = (("code", ctypes.c_uint16), ("jt", ctypes.c_uint8),
                ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32))


class SockFprog(ctypes.Structure):
    _fields_ = (("length", ctypes.c_uint16), ("filter", ctypes.POINTER(SockFilter)))


FilterArray = SockFilter * 128  # declare ctypes layout before root detachment


def program():
    """Return immutable cBPF tuples; numeric register arguments only."""
    load = lambda offset: (0x20, 0, 0, offset)
    equal = lambda value, yes, no: (0x15, yes, no, value)
    bits = lambda value, yes, no: (0x45, yes, no, value)
    ret = lambda value: (0x06, 0, 0, value)
    result = [load(4), equal(ARCH, 1, 0), ret(KILL), load(0),
              bits(0x40000000, 0, 1), ret(KILL)]
    for number in BLOCKED:
        result.extend((equal(number, 0, 1), ret(DENY)))
    result.extend((equal(NUMBERS["clone3"], 0, 1), ret(ENOSYS)))
    socket_block = (load(20), equal(0, 1, 0), ret(DENY), load(16),
                    equal(2, 2, 0), equal(10, 1, 0), ret(DENY), ret(ALLOW))
    result.append(equal(NUMBERS["socket"], 0, len(socket_block)))
    result.extend(socket_block)
    clone_block = (load(20), equal(0, 1, 0), ret(DENY), load(16),
                   bits(NEW_NAMESPACES, 0, 1), ret(DENY), ret(ALLOW))
    result.append(equal(NUMBERS["clone"], 0, len(clone_block)))
    result.extend(clone_block)
    result.append(ret(ALLOW))
    return tuple(result)


def verify_abi():
    """Exact installed-header preflight; never called on normal import."""
    header = Path("/usr/include/x86_64-linux-gnu/asm/unistd_64.h").read_text()
    if not all(re.search(rf"^#define __NR_{name} {number}$", header, re.M)
               for name, number in NUMBERS.items()):
        raise ValueError("syscall_abi_unverified")
    sched = Path("/usr/include/linux/sched.h").read_text()
    values = dict(re.findall(r"^#define\s+(CLONE_NEW\w+)\s+(0x[0-9a-fA-F]+)", sched, re.M))
    if sum(int(values.get(name, "0"), 16) for name in
           ("CLONE_NEWNS", "CLONE_NEWCGROUP", "CLONE_NEWUTS", "CLONE_NEWIPC",
            "CLONE_NEWUSER", "CLONE_NEWPID", "CLONE_NEWNET")) != NEW_NAMESPACES:
        raise ValueError("namespace_abi_unverified")


def install(lib):
    """Explicit one-thread synthetic-test operation; inherited by later forks/exec."""
    if ctypes.sizeof(SockFilter) != 8 or ctypes.sizeof(SockFprog) != 16:
        raise ValueError("filter_abi_unverified")
    if len(list(Path("/proc/self/task").iterdir())) != 1:
        raise ValueError("single_thread_required")
    if lib.prctl(39, 0, 0, 0, 0) != 1:  # PR_GET_NO_NEW_PRIVS
        raise ValueError("no_new_privileges_required")
    rows = program()
    if len(rows) > 128:
        raise ValueError("filter_too_large")
    storage = FilterArray()
    for index, row in enumerate(rows):
        storage[index] = SockFilter(*row)
    descriptor = SockFprog(len(rows), ctypes.cast(storage, ctypes.POINTER(SockFilter)))
    if lib.syscall(ctypes.c_long(NUMBERS["seccomp"]), ctypes.c_long(1),
                   ctypes.c_long(0), ctypes.byref(descriptor)) != 0:
        raise ValueError("filter_install_failed")
    if lib.prctl(21, 0, 0, 0, 0) != 2:  # PR_GET_SECCOMP
        raise ValueError("filter_state_unverified")
