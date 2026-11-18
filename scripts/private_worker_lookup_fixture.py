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


def main_bytes():
    raw = bytearray(base.cwd_canary_bytes())
    # Fixed generated DT_RUNPATH slot becomes inert DT_FLAGS=0. No search tag.
    assert struct.unpack_from('<q', raw, 0x1000 + 6 * 16)[0] == 29
    struct.pack_into('<qQ', raw, 0x1000 + 6 * 16, 30, 0)
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
