"""Disconnected bookkeeping for the sole synthetic supervisor's consuming wait."""

from enum import Enum, auto

from scripts.private_worker_cooperative_exchange import _Deadline, _fd, _require
from scripts.private_worker_mapping_observer import MappingObservationError


class ReapState(Enum):
    UNUSED = auto()
    NO_WAIT = auto()
    WAIT_UNCONFIRMED = auto()
    NO_STATUS = auto()
    STATUS_CONSUMED = auto()


class ReapAttempt:
    """One case, one supervisor, one borrowed exact-child pidfd.

    The parent binds the handle before use and keeps it reserved. The state
    reports the wait outcome, not process-tree or managed-unit cleanup.
    """

    __slots__ = ("_pidfd", "_expected", "_state")

    def __init__(self, *, child_pidfd, expected_exit):
        _require(_fd(child_pidfd) and type(expected_exit) is int and expected_exit in (42, 127))
        self._pidfd = child_pidfd
        self._expected = expected_exit
        self._state = ReapState.UNUSED

    @property
    def state(self):
        return self._state


def consume_observed_exit(*, attempt, deadline_ns, wait_once, exited_code):
    """Run one injected nonblocking, consuming wait on the recorded pidfd.

    The future sole-reaper adapter must use P_PIDFD/WEXITED/WNOHANG, with no
    WNOWAIT, retry, signal or PID lookup. It returns None for no status or
    the exact wait result. A refusal is never permission to repeat the
    acceptance wait. A separate verified cleanup path remains required.
    """
    _require(type(attempt) is ReapAttempt and attempt.state is ReapState.UNUSED)
    attempt._state = ReapState.NO_WAIT
    deadline = _Deadline(deadline_ns)
    _require(type(exited_code) is int)
    try:
        deadline.remaining()
        attempt._state = ReapState.WAIT_UNCONFIRMED
        row = wait_once(attempt._pidfd)
        attempt._state = ReapState.NO_STATUS if row is None else ReapState.STATUS_CONSUMED
        deadline.remaining()
        _require(row is not None and row.si_code == exited_code
                 and row.si_status == attempt._expected)
    except (OSError, AttributeError, MappingObservationError):
        raise MappingObservationError("cooperative consuming wait refused") from None
