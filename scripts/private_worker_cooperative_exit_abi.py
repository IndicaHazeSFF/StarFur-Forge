"""Decode supplied Linux x86-64 PIDFD_GET_INFO v0 bytes only.

No ioctl, process inspection, native ABI detection or proof of authenticity.
The caller must supply the exact verified little-endian v0 layout, a
successful kernel response, and separately bind it to the held pidfd.
"""

import struct


INFO_SIZE = 64
EXIT_BIT = 1 << 3
EXIT_OFFSET = 60


class ExitInfoRefused(ValueError):
    pass


def decode_exit_status(response):
    """Return only the reported raw wait status, never ancillary fields."""
    if type(response) is not bytes or len(response) != INFO_SIZE:
        raise ExitInfoRefused("cooperative worker exit info refused")
    mask, = struct.unpack_from("<Q", response)
    if mask & EXIT_BIT == 0:
        raise ExitInfoRefused("cooperative worker exit info refused")
    status, = struct.unpack_from("<i", response, EXIT_OFFSET)
    return status
