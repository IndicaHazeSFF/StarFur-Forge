"""In-memory framing boundary for future authenticated supervisor IPC.

The receiver accepts only strict length-prefixed ``SupervisorIPCRequest``
envelopes and authenticates them through an injected verifier.  It opens no
transport, persists no replay state, dispatches no operation, and provides no
tool authority.  Native peer identity and OS transport isolation remain later
platform responsibilities.
"""

from __future__ import annotations

import struct

from .sandbox_ipc import (
    AuthenticatedSupervisorIPCRequest,
    MAX_SUPERVISOR_IPC_BYTES,
    SupervisorIPCAuthenticator,
    SupervisorIPCRequest,
)


SUPERVISOR_IPC_FRAME_HEADER_BYTES = 4
MAX_SUPERVISOR_IPC_FRAMES_PER_CONNECTION = 16
MAX_SUPERVISOR_IPC_CONNECTION_BYTES = (
    (SUPERVISOR_IPC_FRAME_HEADER_BYTES + MAX_SUPERVISOR_IPC_BYTES)
    * MAX_SUPERVISOR_IPC_FRAMES_PER_CONNECTION
)


class SupervisorIPCFramingError(ValueError):
    """Bounded framing rejection with no received content or transport detail."""


def frame_supervisor_ipc_request(request: SupervisorIPCRequest) -> bytes:
    """Encode one strict request with an unsigned network-order length prefix."""
    if not isinstance(request, SupervisorIPCRequest):
        raise TypeError("supervisor IPC frame request is invalid")
    payload = request.to_json_bytes()
    return struct.pack(">I", len(payload)) + payload


class AuthenticatedSupervisorIPCReceiver:
    """One bounded fail-closed connection parser; never an executor."""

    def __init__(
        self,
        authenticator: SupervisorIPCAuthenticator,
        *,
        trusted_peer_principal_id: str,
        maximum_frames: int = MAX_SUPERVISOR_IPC_FRAMES_PER_CONNECTION,
    ) -> None:
        if not isinstance(authenticator, SupervisorIPCAuthenticator):
            raise TypeError("supervisor IPC authenticator is invalid")
        if not isinstance(trusted_peer_principal_id, str):
            raise TypeError("supervisor IPC peer principal evidence is invalid")
        if (
            isinstance(maximum_frames, bool)
            or not isinstance(maximum_frames, int)
            or not 1 <= maximum_frames <= MAX_SUPERVISOR_IPC_FRAMES_PER_CONNECTION
        ):
            raise ValueError("supervisor IPC frame limit is invalid")
        self._authenticator = authenticator
        self._trusted_peer_principal_id = trusted_peer_principal_id
        self._maximum_frames = maximum_frames
        self._buffer = bytearray()
        self._received_bytes = 0
        self._frame_count = 0
        self._closed = False
        self._failed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def failed(self) -> bool:
        return self._failed

    def _reject(self, reason: str) -> None:
        self._failed = True
        self._closed = True
        self._buffer.clear()
        raise SupervisorIPCFramingError(reason)

    def feed(self, data: bytes) -> tuple[AuthenticatedSupervisorIPCRequest, ...]:
        """Parse complete frames; any framing/authentication fault poisons the connection."""
        if self._closed or self._failed:
            raise SupervisorIPCFramingError("supervisor IPC connection is closed")
        if not isinstance(data, bytes):
            self._reject("supervisor IPC frame bytes are invalid")
        if not data:
            return ()
        self._received_bytes += len(data)
        if self._received_bytes > MAX_SUPERVISOR_IPC_CONNECTION_BYTES:
            self._reject("supervisor IPC connection byte limit exceeded")
        self._buffer.extend(data)
        results: list[AuthenticatedSupervisorIPCRequest] = []
        while len(self._buffer) >= SUPERVISOR_IPC_FRAME_HEADER_BYTES:
            length = struct.unpack(">I", self._buffer[:SUPERVISOR_IPC_FRAME_HEADER_BYTES])[0]
            if not 1 <= length <= MAX_SUPERVISOR_IPC_BYTES:
                self._reject("supervisor IPC frame length is invalid")
            frame_end = SUPERVISOR_IPC_FRAME_HEADER_BYTES + length
            if len(self._buffer) < frame_end:
                break
            if self._frame_count >= self._maximum_frames:
                self._reject("supervisor IPC frame limit exceeded")
            payload = bytes(self._buffer[SUPERVISOR_IPC_FRAME_HEADER_BYTES:frame_end])
            del self._buffer[:frame_end]
            try:
                request = SupervisorIPCRequest.from_json_bytes(payload)
                authenticated = self._authenticator.authenticate(
                    request,
                    trusted_peer_principal_id=self._trusted_peer_principal_id,
                )
            except (TypeError, ValueError) as error:
                self._reject("supervisor IPC frame authentication failed")
                raise AssertionError("unreachable") from error
            self._frame_count += 1
            results.append(authenticated)
        return tuple(results)

    def close(self) -> None:
        """Close cleanly only at a frame boundary; partial disconnects fail closed."""
        if self._failed:
            raise SupervisorIPCFramingError("supervisor IPC connection is closed")
        if self._closed:
            return
        if self._buffer:
            self._reject("supervisor IPC connection ended with a partial frame")
        self._closed = True

    def abort(self) -> None:
        """Forget unprocessed bytes; this is not cancellation or verified stop."""
        self._buffer.clear()
        self._closed = True


__all__ = [
    "AuthenticatedSupervisorIPCReceiver",
    "MAX_SUPERVISOR_IPC_CONNECTION_BYTES",
    "MAX_SUPERVISOR_IPC_FRAMES_PER_CONNECTION",
    "SUPERVISOR_IPC_FRAME_HEADER_BYTES",
    "SupervisorIPCFramingError",
    "frame_supervisor_ipc_request",
]
