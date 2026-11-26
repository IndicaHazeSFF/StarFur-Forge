"""Compare supplied synthetic-canary map snapshots. No acquisition or authority.

The future supervisor must independently bind the paused process/epoch, measure
the sealed loader, supply its reviewed segment shape, and verify the namespace.
Matching rows cannot attest any of those facts or exclude other code mappings.
"""
from dataclasses import dataclass
from contextlib import closing
import re

LOADER = b"/lib64/ld-linux-x86-64.so.2"
MAX_BYTES = 64 * 1024
MAX_ROWS = 512
MAX_SEGMENTS = 16
READ_CHUNK = 4096
ACCEPTANCE_NS = 1_000_000_000
_ROW = re.compile(
    rb"([0-9a-f]{1,16})-([0-9a-f]{1,16}) +([r-][w-][x-][ps]) +"
    rb"([0-9a-f]{1,16}) +([0-9a-f]{1,8}):([0-9a-f]{1,8}) +"
    rb"([0-9]{1,20})(?: +(.*))?"
)


class MappingObservationError(ValueError):
    """Closed refusal; never return raw process paths or addresses."""


@dataclass(frozen=True, slots=True)
class MappingObservation:
    mapping_count: int
    segment_count: int


@dataclass(frozen=True, slots=True)
class PausedCanaryStamp:
    """Supervisor-supplied equality stamp, not a live process credential."""

    pid: int
    start_ticks: int
    invocation: str
    pause_nonce: str

    def __post_init__(self):
        if (type(self.pid) is not int or not 0 < self.pid < 1 << 31
                or type(self.start_ticks) is not int or not 0 <= self.start_ticks < 1 << 64
                or any(type(v) is not str or re.fullmatch(r"[0-9a-f]{32}", v) is None
                       or v == "0" * 32 for v in (self.invocation, self.pause_nonce))):
            raise MappingObservationError("canary stamp refused")


def capture_bound_mapping(*, expected, attest_paused, open_snapshot, monotonic_ns,
                          identity, segments):
    """Bound a caller-owned pause to a bounded, one-shot snapshot comparison.

    Trusted adapters must attest the pinned child and same uninterrupted
    post-load stop, and open only its snapshot via an already anchored handle.
    No PID lookup, proc access, signaling or native caller is provided here.
    Deadline checks fence acceptance; they cannot cancel blocking adapters.
    """
    if type(expected) is not PausedCanaryStamp:
        raise MappingObservationError("bound mapping capture refused")

    previous = None

    def checked_time():
        nonlocal previous
        now = monotonic_ns()
        if type(now) is not int or now < 0 or (previous is not None and now < previous):
            raise MappingObservationError("bound mapping capture refused")
        previous = now
        return now

    def fenced():
        if checked_time() - started >= ACCEPTANCE_NS:
            raise MappingObservationError("bound mapping capture refused")

    def attest():
        actual = attest_paused()
        if type(actual) is not PausedCanaryStamp or actual != expected:
            raise MappingObservationError("bound mapping capture refused")
        fenced()

    try:
        started = checked_time()
        attest()
        chunks, total = [], 0
        with closing(open_snapshot()) as stream:
            fenced()
            while True:
                limit = min(READ_CHUNK, MAX_BYTES + 1 - total)
                part = stream.read(limit)
                fenced()
                if type(part) is not bytes or len(part) > limit or total + len(part) > MAX_BYTES:
                    raise MappingObservationError("bound mapping capture refused")
                if not part:
                    break
                chunks.append(part)
                total += len(part)
        fenced()
        result = check_resident_mapping(b"".join(chunks), identity=identity, segments=segments)
        fenced()
        attest()
        return result
    except (OSError, MappingObservationError):
        raise MappingObservationError("bound mapping capture refused") from None


def check_resident_mapping(snapshot, *, identity, segments):
    """Require one exact supplied loader layout at one base in supplied bytes.

    identity: (device major, device minor, inode) for the measured in-root file.
    segments: ordered (relative start, length, file offset, permissions) rows,
    including any expected RELRO split. This is not an ELF-to-maps simulator.
    """
    return _check_layout(snapshot, identity=identity, segments=segments, cooperative=False)


def check_cooperative_page_coverage(snapshot, *, identity, segments):
    """Compare exact 4 KiB file-backed page coverage, ignoring equivalent splits.

    Used only for the fixed native cooperative experiment. No ELF measurement,
    OS page-size check, or provenance comes from this supplied-byte comparison.
    """
    return _check_layout(snapshot, identity=identity, segments=segments, cooperative=True)


def _require(ok):
    if not ok:
        raise MappingObservationError("resident mapping observation refused")


def _canonical_pages(rows):
    result = []
    for start, size, offset, mode in rows:
        _require(all(value % 4096 == 0 for value in (start, size, offset))
                 and offset + size < 1 << 64)
        if result:
            pstart, psize, poffset, pmode = result[-1]
            if pstart + psize == start and poffset + psize == offset and pmode == mode:
                result[-1] = (pstart, psize + size, poffset, pmode)
                continue
        result.append((start, size, offset, mode))
    return tuple(result)


def _check_layout(snapshot, *, identity, segments, cooperative):
    require = _require

    require(type(identity) is tuple and len(identity) == 3 and
            all(type(v) is int and 0 <= v < 1 << 64 for v in identity) and identity[2] > 0)
    require(type(segments) is tuple and 1 <= len(segments) <= MAX_SEGMENTS)
    end, executable = 0, False
    for segment in segments:
        require(type(segment) is tuple and len(segment) == 4)
        start, size, offset, mode = segment
        require(all(type(v) is int and 0 <= v < 1 << 64 for v in (start, size, offset)) and
                start >= end and size > 0 and start + size < 1 << 64 and
                type(mode) is bytes and mode in (b"r--p", b"r-xp", b"rw-p", b"---p"))
        end = start + size
        executable |= mode == b"r-xp"
    require(segments[0][0] == segments[0][2] == 0 and executable)

    require(type(snapshot) is bytes and 0 < len(snapshot) <= MAX_BYTES and snapshot.endswith(b"\n"))
    lines = snapshot[:-1].split(b"\n")
    require(len(lines) <= MAX_ROWS)
    matches, last_end = [], 0
    for line in lines:
        row = _ROW.fullmatch(line)
        require(row is not None)
        low, high, mode, offset, major, minor, inode, name = row.groups()
        start, end = int(low, 16), int(high, 16)
        require(last_end <= start < end)
        last_end = end
        observed = (int(major, 16), int(minor, 16), int(inode))
        loader_name = bool(name and name.removesuffix(b" (deleted)").rsplit(b"/", 1)[-1] ==
                           LOADER.rsplit(b"/", 1)[-1])
        if observed == identity or loader_name:
            require(observed == identity and name == LOADER and len(matches) < MAX_SEGMENTS)
            matches.append((start, end - start, int(offset, 16), mode))
    require(bool(matches))
    base = matches[0][0]
    relative = tuple((start - base, size, offset, mode) for start, size, offset, mode in matches)
    if cooperative:
        require(base % 4096 == 0)
        require(_canonical_pages(relative) == _canonical_pages(segments))
    else:
        require(relative == segments)
    return MappingObservation(1, len(matches))
