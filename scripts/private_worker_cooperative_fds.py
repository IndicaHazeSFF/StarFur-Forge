"""Check supplied fixture descriptor observations; never inspect live FDs."""

from dataclasses import dataclass
from enum import Enum, auto

from scripts.private_worker_lookup_fixture import COOPERATIVE_READY_FD, COOPERATIVE_RELEASE_FD


class DescriptorReviewError(ValueError):
    """Refuse without reporting raw descriptor metadata."""


class Direction(Enum):
    READ = auto()
    WRITE = auto()


@dataclass(frozen=True, slots=True)
class PipeEnd:
    fd: int
    device: int
    inode: int
    direction: Direction
    close_on_exec: bool
    anonymous_pipe: bool


def check_descriptor_split(*, ready_identity, release_identity, parent, child):
    """Check a proposed exact child inventory and parent's two channel ends.

    Trusted acquisition must independently establish anonymous provenance,
    completeness of both channel inventories, and continuity through exec.
    This pure check cannot detect omitted entries or attest isolation. The
    parent's existing non-channel handles are outside this contract.
    """
    def require(ok):
        if not ok:
            raise DescriptorReviewError("cooperative descriptor split refused")

    def valid_identity(value):
        return (type(value) is tuple and len(value) == 2
                and all(type(n) is int and 0 <= n < (1 << 64) for n in value)
                and value[1] != 0)

    require(valid_identity(ready_identity) and valid_identity(release_identity)
            and ready_identity != release_identity)

    def check(ends, *, is_child):
        require(type(ends) is tuple and len(ends) == 2)
        by_identity = {}
        fds = set()
        for end in ends:
            require(type(end) is PipeEnd and type(end.fd) is int
                    and 0 <= end.fd < (1 << 31) and end.fd not in fds
                    and end.anonymous_pipe is True
                    and end.close_on_exec is (not is_child))
            key = (end.device, end.inode)
            require(valid_identity(key) and key not in by_identity)
            fds.add(end.fd)
            by_identity[key] = end
        require(set(by_identity) == {ready_identity, release_identity})
        ready, release = by_identity[ready_identity], by_identity[release_identity]
        require(ready.direction is (Direction.WRITE if is_child else Direction.READ)
                and release.direction is (Direction.READ if is_child else Direction.WRITE))
        if is_child:
            require(ready.fd == COOPERATIVE_READY_FD and release.fd == COOPERATIVE_RELEASE_FD)

    check(parent, is_child=False)
    check(child, is_child=True)
