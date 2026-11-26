"""Review supplied synthetic channel events. No pipes, waits, or OS evidence."""

from dataclasses import dataclass
from enum import Enum, auto

from scripts.private_worker_hold_lifecycle import Cleanup
from scripts.private_worker_mapping_observer import (
    ACCEPTANCE_NS,
    MappingObservationError,
    check_resident_mapping,
)


class CooperativeReviewError(ValueError):
    """Closed refusal without raw event or map contents."""


class Step(Enum):
    CHANNEL_OWNERSHIP_CHECKED = auto()
    READY = auto()
    READY_EOF = auto()
    CAPTURE_OPEN = auto()
    CAPTURE_CLOSED = auto()
    RELEASE = auto()
    EXIT_REAPED = auto()
    NO_READY_EOF = auto()


@dataclass(frozen=True, slots=True)
class Event:
    step: Step
    case: object
    time_ns: int
    payload: bytes | int | None = None


_POSITIVE = (
    (Step.CHANNEL_OWNERSHIP_CHECKED, None),
    (Step.READY, b"R"),
    (Step.READY_EOF, b""),
    (Step.CAPTURE_OPEN, None),
    (Step.CAPTURE_CLOSED, None),
    (Step.RELEASE, b"G"),
    (Step.EXIT_REAPED, 42),
)
_NEGATIVE = (
    (Step.CHANNEL_OWNERSHIP_CHECKED, None),
    (Step.NO_READY_EOF, b""),
    (Step.EXIT_REAPED, 127),
)


def review_cooperative_mapping(*, positive, negative, events, snapshot, identity,
                               segments, cleanup):
    """Return a descriptive synthetic summary after both controls and cleanup.

    Case tokens only correlate caller-supplied observations. A marker and an
    ordered transcript cannot attest descriptor ownership, fixture identity,
    complete event coverage, stable mappings, or an OS-held stop.
    """
    def require(ok):
        if not ok:
            raise CooperativeReviewError("cooperative mapping review refused")

    require(type(positive) is object and type(negative) is object and positive is not negative)
    require(type(events) is tuple and len(events) == len(_POSITIVE) + len(_NEGATIVE))
    previous = -1
    for case, series, block in (
        (positive, _POSITIVE, events[:len(_POSITIVE)]),
        (negative, _NEGATIVE, events[len(_POSITIVE):]),
    ):
        for (step, payload), event in zip(series, block):
            require(type(event) is Event and event.case is case and event.step is step
                    and type(event.payload) is type(payload) and event.payload == payload
                    and type(event.time_ns) is int and event.time_ns >= 0
                    and event.time_ns >= previous)
            previous = event.time_ns
            if step is Step.CAPTURE_OPEN:
                opened = previous
            elif step is Step.CAPTURE_CLOSED:
                require(previous - opened < ACCEPTANCE_NS)

    require(type(cleanup) is Cleanup and cleanup.unit_inactive is True
            and cleanup.cgroup_empty is True and cleanup.fixture_removed is True
            and cleanup.parent_unchanged is True)
    try:
        return check_resident_mapping(snapshot, identity=identity, segments=segments)
    except MappingObservationError:
        raise CooperativeReviewError("cooperative mapping review refused") from None
