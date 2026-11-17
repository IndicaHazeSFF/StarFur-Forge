"""Pure narrow ELF dependency inspection for a future Linux worker image.

Supplied bytes only: no filesystem, discovery, loader execution or subprocess.
The result is metadata, not complete ELF validation, trusted acquisition, CPU-only
attestation, a dependency closure, deployment readiness or launch permission.
Section tables, relocations, dlopen targets and binary behavior are not inspected.
"""
from dataclasses import dataclass
from hashlib import sha256
import re
import struct

POLICY = "worker-elf64-x86-dependencies-v2"
MAX_ELF_BYTES = 64 * 1024 * 1024
MAX_PROGRAM_HEADERS = 128
MAX_DYNAMIC_ENTRIES = 256
MAX_STRING_BYTES = 1024 * 1024
LOADER = "/lib64/ld-linux-x86-64.so.2"
_SONAME = re.compile(r"lib[A-Za-z0-9_+-][A-Za-z0-9._+-]{0,94}\.so(?:\.[0-9]+)*")


def _soname_valid(name):
    # The fixed Linux loader may also occur as DT_NEEDED without a lib prefix.
    return (type(name) is str and len(name) <= 128 and
            (name == "ld-linux-x86-64.so.2" or _SONAME.fullmatch(name) is not None))


class WorkerElfError(ValueError):
    """Content-free unsupported/malformed dependency inspection."""


@dataclass(frozen=True, slots=True, repr=False)
class ElfDependencies:
    raw_sha256: str
    object_kind: str
    interpreter: str | None
    needed: tuple[str, ...]

    def __post_init__(self):
        if (type(self.raw_sha256) is not str or
                re.fullmatch(r"[0-9a-f]{64}", self.raw_sha256) is None or
                type(self.object_kind) is not str or
                self.object_kind not in ("executable", "shared_object") or
                self.interpreter is not None and
                (type(self.interpreter) is not str or self.interpreter != LOADER) or
                type(self.needed) is not tuple or len(self.needed) > 32 or
                any(not _soname_valid(n) for n in self.needed) or
                len(set(self.needed)) != len(self.needed)):
            raise WorkerElfError("worker ELF inspection is unavailable")


def inspect_worker_elf(raw: bytes) -> ElfDependencies:
    """Inspect bounded ELF64 LE x86-64 ET_EXEC/ET_DYN metadata, never load it.

Only the fixed Linux loader is accepted. Any RPATH/RUNPATH denies, including
empty values; dependency search policy must not be inferred from source bytes.
Unknown dynamic metadata is ignored, not certified safe. Missing dependencies
and runtime-loaded libraries require separate reviewed inventory/closure checks.
"""
    return _inspect_metadata(raw)[0]


def _inspect_metadata(raw, *, review_search=False):
    """Internal shared parser; review mode describes search tags, never approves."""
    metadata, search, _ = _parse_metadata(raw, review_search=review_search)
    return metadata, search


def _parse_metadata(raw, *, review_search=False, review_soname=False):
    """Shared bounded parser; optional observations never accept a loader image."""
    try:
        if type(raw) is not bytes or not 64 <= len(raw) <= MAX_ELF_BYTES:
            raise ValueError

        def region(offset, size):
            if not (0 <= offset <= len(raw) and 0 <= size <= len(raw) - offset):
                raise ValueError
            return memoryview(raw)[offset:offset + size]

        header = struct.unpack("<16sHHIQQQIHHHHHH", region(0, 64))
        ident, kind, machine, version, _, phoff, _, flags, ehsize, phsize, phnum, *_ = header
        if (ident[:7] != b"\x7fELF\x02\x01\x01" or ident[7] not in (0, 3) or
                ident[8:] != b"\0" * 8 or kind not in (2, 3) or
                machine != 62 or version != 1 or flags != 0 or ehsize != 64 or
                phsize != 56 or not 1 <= phnum <= MAX_PROGRAM_HEADERS or phoff < 64):
            raise ValueError
        table = region(phoff, phnum * 56)
        loads, dynamics, interpreters = [], [], []
        for index in range(phnum):
            ptype, pflags, offset, address, _, size, memsize, align = struct.unpack_from(
                "<IIQQQQQQ", table, index * 56)
            # PT_NULL has no defined remaining fields. Other segments are bounded.
            if ptype == 0:
                continue
            region(offset, size)
            if pflags & ~7 or address + memsize >= 1 << 64:
                raise ValueError
            if ptype == 1:
                if (size > memsize or align not in (0, 1) and
                        (align & (align - 1) or address % align != offset % align)):
                    raise ValueError
                loads.append((offset, address, size))
            elif ptype == 2:
                dynamics.append((offset, address, size))
            elif ptype == 3:
                if not 2 <= size <= 128:
                    raise ValueError
                value = bytes(region(offset, size))
                if value != LOADER.encode("ascii") + b"\0":
                    raise ValueError
                interpreters.append(LOADER)
        if not loads or len(dynamics) > 1 or len(interpreters) > 1:
            raise ValueError

        def mapped(address, size):
            matches = [off + address - start for off, start, length in loads
                       if start <= address and size <= length - (address - start)]
            if len(matches) != 1:
                raise ValueError
            return region(matches[0], size), matches[0]

        needed, search, soname = [], {}, None
        if dynamics:
            offset, address, size = dynamics[0]
            if not size or size % 16 or size // 16 > MAX_DYNAMIC_ENTRIES:
                raise ValueError
            dynamic, bound_offset = mapped(address, size)
            if bound_offset != offset:
                raise ValueError
            values, references, ended, soname_reference = {}, [], False, None
            for pos in range(0, size, 16):
                tag, value = struct.unpack_from("<qQ", dynamic, pos)
                if ended:
                    if tag != 0 or value != 0:
                        raise ValueError
                    continue
                if tag == 0:
                    ended = True
                elif tag in (15, 29):  # DT_RPATH / DT_RUNPATH, even empty
                    if not review_search or tag in search:
                        raise ValueError
                    search[tag] = value
                elif tag == 1:  # DT_NEEDED
                    references.append(value)
                    if len(references) > 32:
                        raise ValueError
                elif tag == 14 and review_soname:  # DT_SONAME, including offset zero
                    if soname_reference is not None:
                        raise ValueError
                    soname_reference = value
                elif tag in (5, 10):  # DT_STRTAB / DT_STRSZ
                    if tag in values:
                        raise ValueError
                    values[tag] = value
            if not ended:
                raise ValueError
            if references or search or soname_reference is not None:
                if set(values) != {5, 10} or not 1 <= values[10] <= MAX_STRING_BYTES:
                    raise ValueError
                strings, _ = mapped(values[5], values[10])
                strings = bytes(strings)
                for tag, reference in tuple(search.items()):
                    if not 0 <= reference < len(strings):
                        raise ValueError
                    end = strings.find(b"\0", reference, min(reference + 4097, len(strings)))
                    if end < 0:
                        raise ValueError
                    text = strings[reference:end].decode("ascii")
                    if any(ord(c) < 32 or ord(c) > 126 for c in text):
                        raise ValueError
                    search[tag] = text
                for reference in references:
                    if not 0 <= reference < len(strings):
                        raise ValueError
                    end = strings.find(b"\0", reference, min(reference + 129, len(strings)))
                    if end < 0:
                        raise ValueError
                    name = strings[reference:end].decode("ascii")
                    if not _soname_valid(name) or name in needed:
                        raise ValueError
                    needed.append(name)
                if soname_reference is not None:
                    if not 0 <= soname_reference < len(strings):
                        raise ValueError
                    end = strings.find(b"\0", soname_reference,
                                       min(soname_reference + 129, len(strings)))
                    if end < 0:
                        raise ValueError
                    soname = strings[soname_reference:end].decode("ascii")
                    if not _soname_valid(soname):
                        raise ValueError
        metadata = ElfDependencies(sha256(raw).hexdigest(),
                               "executable" if kind == 2 else "shared_object",
                               interpreters[0] if interpreters else None, tuple(needed))
        return metadata, search, soname
    except (ValueError, UnicodeError, struct.error, OverflowError):
        raise WorkerElfError("worker ELF inspection is unavailable") from None
