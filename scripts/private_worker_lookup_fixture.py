"""Fixed generated ELF lookup fixtures, bytes only; never files or execution.

Transforms only our generated C4/C5 fixtures, never supplied/installed binaries.
Main has no RUNPATH; intermediate has a transitive DT_NEEDED and no RUNPATH.
Only an explicitly approved sealed-root helper may materialize these bytes.
"""
import importlib.util
from pathlib import Path
import struct

spec = importlib.util.spec_from_file_location('lookup_fixed_base', Path(__file__).with_name('private_worker_loader_fixture.py'))
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
LEAF = b'libfixture-leaf.so'
RESIDENT = base.LOADER.rstrip(b'\0').rsplit(b'/', 1)[-1]
COOPERATIVE_READY_FD = 4
COOPERATIVE_RELEASE_FD = 5


def main_bytes():
    raw = bytearray(base.cwd_canary_bytes())
    # Fixed generated DT_RUNPATH slot becomes inert DT_FLAGS=0. No search tag.
    assert struct.unpack_from('<q', raw, 0x1000 + 6 * 16)[0] == 29
    struct.pack_into('<qQ', raw, 0x1000 + 6 * 16, 30, 0)
    return bytes(raw)


def cooperative_main_bytes():
    """Fixed inert entry code for the cooperative mapping experiment only.

    After the explicit loader transfers control, write one marker, close the
    readiness writer, and wait for the exact release byte. Exit with the
    relocated fixture value only on success; every I/O error fails. No runner
    or descriptor-setup path consumes these bytes.
    """
    raw = bytearray(main_bytes())
    entry, ready, release = 0x400, 0x9F0, 0x1300
    code, refusals = bytearray(), []

    def rip(prefix, target, tail=b""):
        end = entry + len(code) + len(prefix) + 4 + len(tail)
        code.extend(prefix + struct.pack("<i", target - end) + tail)

    def syscall(number, fd):
        code.extend(struct.pack("<BIBI", 0xBF, fd, 0xB8, number) + b"\x0f\x05")

    def require_equal():
        code.extend(b"\x0f\x85\0\0\0\0")
        refusals.append(len(code) - 4)

    def require_return(value):
        code.extend(b"\x48\x83\xf8" + bytes((value,)))  # cmp rax, imm8
        require_equal()

    def close(fd):
        syscall(3, fd)
        require_return(0)

    raw[ready] = ord("R")
    rip(b"\x48\x8d\x35", ready)  # lea rsi, [rip+ready]
    code.extend(b"\xba\x01\0\0\0")  # mov edx, 1
    syscall(1, COOPERATIVE_READY_FD)
    require_return(1)
    close(COOPERATIVE_READY_FD)

    rip(b"\x48\x8d\x35", release)
    code.extend(b"\xba\x01\0\0\0")
    syscall(0, COOPERATIVE_RELEASE_FD)
    require_return(1)
    rip(b"\x80\x3d", release, b"G")  # cmp byte [rip+release], 'G'
    require_equal()
    close(COOPERATIVE_RELEASE_FD)

    rip(b"\x48\x8b\x05", 0x1200)  # mov rax, [rip+relocated GOT]
    code.extend(bytes.fromhex("8b38b83c0000000f050f0b"))  # exit(fixture_value); ud2
    failure = len(code)
    syscall(60, 112)
    code.extend(b"\x0f\x0b")
    for offset in refusals:
        struct.pack_into("<i", code, offset, failure - offset - 4)
    if len(code) > 0x200:
        raise ValueError("cooperative fixture code bound")
    raw[entry:0x600] = code.ljust(0x200, b"\0")
    return bytes(raw)


def library_bytes(*, decoy=False):
    raw = bytearray(base.library_bytes(decoy=decoy))
    size = struct.unpack_from('<Q', raw, 0x1000 + 2 * 16 + 8)[0]
    raw[0x600 + size:0x600 + size + len(LEAF) + 1] = LEAF + b'\0'
    struct.pack_into('<Q', raw, 0x1000 + 2 * 16 + 8, size + len(LEAF) + 1)
    struct.pack_into('<qQqQ', raw, 0x1000 + 6 * 16, 1, size, 0, 0)
    # Fixed PT_DYNAMIC is last of the three generated shared-object headers.
    struct.pack_into('<QQ', raw, 64 + 2 * 56 + 32, 8 * 16, 8 * 16)
    return bytes(raw)


def leaf_bytes():
    raw = bytearray(base.library_bytes())
    strings = b'\0' + base.SYMBOL + b'\0' + LEAF + b'\0$ORIGIN\0'
    raw[0x600:0x600 + len(strings)] = strings
    struct.pack_into('<Q', raw, 0x1000 + 2 * 16 + 8, len(strings))
    struct.pack_into('<I', raw, 0x1200, 7)
    return bytes(raw)


def resident_request_bytes():
    """Intermediate requests the named resident in addition to its normal leaf.

    No search tags, version requirements, or imports from the resident. This
    exercises a name-based dependency only; the intermediate's data is unchanged.
    """
    raw = bytearray(library_bytes())
    size = struct.unpack_from('<Q', raw, 0x1000 + 2 * 16 + 8)[0]
    raw[0x600 + size:0x600 + size + len(RESIDENT) + 1] = RESIDENT + b'\0'
    struct.pack_into('<Q', raw, 0x1000 + 2 * 16 + 8, size + len(RESIDENT) + 1)
    struct.pack_into('<qQqQ', raw, 0x1000 + 7 * 16, 1, size, 0, 0)
    struct.pack_into('<QQ', raw, 64 + 2 * 56 + 32, 9 * 16, 9 * 16)
    return bytes(raw)
