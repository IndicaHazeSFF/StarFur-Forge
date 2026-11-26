"""Allocate only the fixed synthetic readiness/release channel pair."""

from contextlib import contextmanager
import os
import sys

from scripts.private_worker_cooperative_fd_read import observe_owned_pipe_end
from scripts.private_worker_cooperative_fds import DescriptorReviewError, Direction


class _Channels:
    def __init__(self):
        self._owned = {}
        self._selected = False

    def _register(self, pair):
        self._owned.update((fd, None) for fd in pair)

    def _close(self, fds):
        failed = False
        for fd in fds:
            del self._owned[fd]
            try:
                os.close(fd)
            except OSError:
                failed = True
        if failed:
            raise DescriptorReviewError("cooperative channel cleanup refused")

    def _select(self, *, child):
        if self._selected or len(self._owned) != 4:
            raise DescriptorReviewError("cooperative channel selection refused")
        self._selected = True
        if child:
            self._close((self._ready_read.fd, self._release_write.fd))
            result = (self._ready_write, self._release_read)
            for end in result:
                del self._owned[end.fd]
            return result
        self._close((self._ready_write.fd, self._release_read.fd))
        return self._ready_read, self._release_write

    def retain_parent_ends(self):
        """Close child copies; borrow readiness reader and release writer."""
        return self._select(child=False)

    def transfer_child_ends(self):
        """Close parent copies; transfer ownership of both CLOEXEC ends."""
        return self._select(child=True)


@contextmanager
def create_cooperative_channels():
    """Create two private byte-stream pipes with all ends close-on-exec.

    Only the single-threaded, sealed synthetic supervisor may call this
    before forking its fixed canary. Caller must choose the process-local
    role immediately after fork and verify its complete exec inventory.
    Child setup must make its own release reader blocking before exec;
    parent endpoints must remain nonblocking for the deadline fence.
    No fork, descriptor inheritance change, or native caller here.
    """
    if sys.platform != "linux":
        raise DescriptorReviewError("cooperative channel platform refused")
    channels = _Channels()

    def pipe():
        pair = os.pipe2(os.O_CLOEXEC | os.O_NONBLOCK)
        channels._register(pair)
        reader, writer = pair
        info = os.fstat(reader)
        identity = (info.st_dev, info.st_ino)
        ends = (observe_owned_pipe_end(reader, created_identity=identity),
                observe_owned_pipe_end(writer, created_identity=identity))
        if (ends[0].direction is not Direction.READ or ends[1].direction is not Direction.WRITE
                or not all(end.close_on_exec for end in ends)
                or any(os.get_blocking(end.fd) for end in ends)):
            raise DescriptorReviewError("cooperative channel metadata refused")
        return ends

    try:
        try:
            channels._ready_read, channels._ready_write = pipe()
            channels._release_read, channels._release_write = pipe()
            a, b = channels._ready_read, channels._release_read
            if (a.device, a.inode) == (b.device, b.inode):
                raise DescriptorReviewError("cooperative channels are not distinct")
        except (OSError, AttributeError):
            raise DescriptorReviewError("cooperative channel creation refused") from None
        yield channels
    finally:
        channels._close(tuple(channels._owned))
