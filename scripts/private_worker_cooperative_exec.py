"""Disconnected descriptor handoff for the fixed cooperative canary.

No OS backend, inventory scanner, fork or exec. The injected operations
must be trusted; a passing fake does not establish native inventory.
"""

from scripts.private_worker_cooperative_fds import (
    DescriptorReviewError, Direction, PipeEnd, check_descriptor_split,
)
from scripts.private_worker_lookup_fixture import COOPERATIVE_READY_FD, COOPERATIVE_RELEASE_FD


def prepare_exec_slots(*, ready_identity, release_identity, parent, child, ops):
    """Transfer two child-local ends to fixed slots, or refuse.

    Caller already closed every other descriptor, retired all previous
    owners and excludes concurrent descriptor mutation. The trusted adapter
    supplies an exact inventory (excluding its own closed scanner),
    kernel-style atomic dup operations and non-retried close semantics.
    On any refusal the caller must exit without exec, not retry or unwind
    former owners. No actual adapter/caller is wired.
    """
    targets = (COOPERATIVE_READY_FD, COOPERATIVE_RELEASE_FD)
    owned = set()

    def need(ok):
        if not ok:
            raise DescriptorReviewError("cooperative exec handoff refused")

    def inventory(expected):
        rows = ops.inventory()
        need(type(rows) is frozenset and all(type(fd) is int for fd in rows)
             and rows == frozenset(expected))

    def observe(fd, identity, direction, *, cloexec, blocking):
        row = ops.observe(fd, identity)
        need(row == PipeEnd(fd, *identity, direction, cloexec, True)
             and ops.get_blocking(fd) is blocking)
        return row

    def close(fd):
        # Retire before closing; never repeat an ambiguous close.
        owned.remove(fd)
        ops.close(fd)

    try:
        need(type(child) is tuple and len(child) == 2
             and all(type(end) is PipeEnd and type(end.fd) is int
                     and 0 <= end.fd < (1 << 31) for end in child))
        inputs = tuple(end.fd for end in child)
        need(inputs[0] != inputs[1])
        pairs = ((ready_identity, Direction.WRITE), (release_identity, Direction.READ))
        check_descriptor_split(
            ready_identity=ready_identity, release_identity=release_identity, parent=parent,
            child=tuple(PipeEnd(slot, end.device, end.inode, end.direction,
                                False, end.anonymous_pipe)
                        for slot, end in zip(targets, child)),
        )
        inventory(inputs)
        for end, (identity, direction) in zip(child, pairs):
            need(end == observe(end.fd, identity, direction, cloexec=True, blocking=False))
        owned.update(inputs)
        scratch = []
        for fd, (identity, direction) in zip(inputs, pairs):
            copy = ops.dup_cloexec(fd, max(targets) + 1)
            need(type(copy) is int and max(targets) < copy < (1 << 31)
                 and copy not in owned)
            owned.add(copy)
            scratch.append(copy)
            observe(copy, identity, direction, cloexec=True, blocking=False)
        for fd in inputs:
            close(fd)
        inventory(scratch)
        ops.set_blocking(scratch[1], True)
        for fd, slot in zip(scratch, targets):
            ops.dup_to_inheritable(fd, slot)
            owned.add(slot)
        for fd in scratch:
            close(fd)
        observed = tuple(
            observe(slot, identity, direction, cloexec=False, blocking=index == 1)
            for index, (slot, (identity, direction)) in enumerate(zip(targets, pairs))
        )
        inventory(targets)
        return observed
    except (OSError, DescriptorReviewError):
        for fd in sorted(owned):
            try:
                close(fd)
            except OSError:
                pass  # Terminal refusal; no claim that cleanup succeeded.
        raise DescriptorReviewError("cooperative exec handoff refused") from None
