"""Inert fixed Linux x86-64 loader fixtures; bytes only, never write or execute.

Main reads one relocated data symbol and exits via Linux syscall60. Library
contains a single integer42 (intended) or13 (decoy), no instructions or imports.
This generator is NOT a validator, compiler or general executable-code API.
Only an explicitly approved sealed-root helper may materialize/execute fixtures.
"""
import struct

LOADER = b"/lib64/ld-linux-x86-64.so.2\0"
SIZE = 8192
SYMBOL = b"fixture_value"
LIBRARY = b"libfixture.so"


def _elf(*, library, decoy=False, cwd_guard=False):
    raw = bytearray(SIZE)
    base = 0 if library else 0x400000
    runpath = b"$ORIGIN:/build/llama-server-cpu/bin:" if cwd_guard else b"$ORIGIN"
    strings = b"\0" + SYMBOL + b"\0" + LIBRARY + b"\0" + runpath + b"\0"
    symbol_offset = 1
    library_offset = 2 + len(SYMBOL)
    origin_offset = library_offset + len(LIBRARY) + 1
    # SysV hash with one bucket and two symbol slots (undefined slot0 + slot1).
    raw[0x780:0x794] = struct.pack("<IIIII", 1, 2, 1, 0, 0)
    raw[0x600:0x600 + len(strings)] = strings
    struct.pack_into("<IBBHQQ", raw, 0x700 + 24, symbol_offset, 0x11, 0,
                     1 if library else 0, 0x1200 if library else 0, 4)
    dynamic = [(4, base + 0x780), (5, base + 0x600), (10, len(strings)),
               (6, base + 0x700), (11, 24)]
    if library:
        dynamic.append((14, library_offset))
        struct.pack_into("<I", raw, 0x1200, 13 if decoy else 42)
    else:
        dynamic += [(1, library_offset), (29, origin_offset), (7, base + 0x800),
                    (8, 24), (9, 24), (21, 0)]
        # R_X86_64_GLOB_DAT: loader writes the address of fixture_value into GOT.
        struct.pack_into("<QQq", raw, 0x800, base + 0x1200, (1 << 32) | 6, 0)
        # mov rax,[rip+GOT]; mov edi,[rax]; mov eax,60; syscall
        code, failures = bytearray(), []
        def rip(prefix, target, tail=b""):
            displacement = target - (0x400 + len(code) + len(prefix) + 4 + len(tail))
            code.extend(prefix + struct.pack("<i", displacement) + tail)
        def require():
            code.extend(b"\x0f\x85\0\0\0\0"); failures.append(len(code) - 4)
        if cwd_guard:
            raw[0x900:0x907] = b"/decoy\0"
            # fstat(3,scratch) must succeed and describe an actual directory.
            code.extend(bytes.fromhex("bf03000000")); rip(b"\x48\x8d\x35", 0x1400)
            code.extend(bytes.fromhex("b8050000000f054883f800")); require()
            rip(b"\x8b\x05", 0x1400 + 24)  # Linux x86-64 stat.st_mode
            code.extend(bytes.fromhex("2500f000003d00400000")); require()
            # Valid chdir and fchdir requests must both return raw -EPERM.
            rip(b"\x48\x8d\x3d", 0x900)
            code.extend(bytes.fromhex("b8500000000f054883f8ff")); require()
            code.extend(bytes.fromhex("bf03000000b8510000000f054883f8ff")); require()
            # getcwd must still return exactly /cwd plus its terminating NUL.
            rip(b"\x48\x8d\x3d", 0x1300)
            code.extend(bytes.fromhex("be10000000b84f0000000f054883f805")); require()
            rip(b"\x81\x3d", 0x1300, b"/cwd"); require()
            rip(b"\x80\x3d", 0x1304, b"\0"); require()
        rip(b"\x48\x8b\x05", 0x1200)
        code.extend(bytes.fromhex("8b38b83c0000000f05"))
        failed = len(code)
        code.extend(bytes.fromhex("bf70000000b83c0000000f05") if cwd_guard else b"")
        for offset in failures:
            struct.pack_into("<i", code, offset, failed - (offset + 4))
        if len(code) > 512:
            raise ValueError("fixture code bound")
        raw[0x400:0x400 + len(code)] = code
        raw[0x300:0x300 + len(LOADER)] = LOADER
    dynamic.append((0, 0))
    for index, row in enumerate(dynamic):
        struct.pack_into("<qQ", raw, 0x1000 + index * 16, *row)
    count = 3 if library else 5
    headers = [] if library else [(6, 4, 64, base + 64, 0, count * 56, count * 56, 8)]
    if not library:
        headers.append((3, 4, 0x300, base + 0x300, 0, len(LOADER), len(LOADER), 1))
    headers += [(1, 5, 0, base, 0, 4096, 4096, 4096),
                (1, 6, 4096, base + 4096, 0, 4096, 4096, 4096)]
    headers.append((2, 6, 0x1000, base + 0x1000, 0, len(dynamic) * 16, len(dynamic) * 16, 8))
    raw[:64] = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01" + b"\0" * 9,
                           3 if library else 2, 62, 1, 0 if library else base + 0x400,
                           64, 0, 0, 64, 56, count, 0, 0, 0)
    for index, row in enumerate(headers):
        struct.pack_into("<IIQQQQQQ", raw, 64 + index * 56, *row)
    return bytes(raw)


def canary_bytes():
    """Fixed main with DT_NEEDED libfixture.so, exact $ORIGIN, no libc."""
    return _elf(library=False)


def cwd_canary_bytes():
    """Fixed mixed-path main, valid-directory checks and post-exec cwd probes."""
    return _elf(library=False, cwd_guard=True)


def library_bytes(*, decoy=False):
    if type(decoy) is not bool:
        raise ValueError("fixture selector is unavailable")
    return _elf(library=True, decoy=decoy)
