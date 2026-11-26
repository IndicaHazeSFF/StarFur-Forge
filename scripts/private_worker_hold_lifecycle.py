"""Check synthetic supervisor transcripts; no process or capture adapter."""

from dataclasses import dataclass
from enum import Enum, auto

from scripts.private_worker_mapping_observer import (
    MAX_SEGMENTS,
    MappingObservation,
    PausedCanaryStamp,
)


class HoldReviewError(ValueError):
    """Closed refusal; transcript contents are never reported."""


class Step(Enum):
    ATTACHED_WITH_REQUIRED_OPTIONS = auto()
    EXPECTED_EXEC = auto()
    EXPECTED_ENTRY_STOP = auto()
    CAPTURE_STARTED = auto()
    CAPTURE_CLOSED_WHILE_HELD = auto()
    POSITIVE_EXIT_42_REAPED = auto()
    NEGATIVE_EXIT_127_REAPED_WITHOUT_ENTRY = auto()


_SEQUENCE = (
    Step.ATTACHED_WITH_REQUIRED_OPTIONS,
    Step.EXPECTED_EXEC,
    Step.EXPECTED_ENTRY_STOP,
    Step.CAPTURE_STARTED,
    Step.CAPTURE_CLOSED_WHILE_HELD,
    Step.POSITIVE_EXIT_42_REAPED,
    Step.NEGATIVE_EXIT_127_REAPED_WITHOUT_ENTRY,
)


@dataclass(frozen=True, slots=True)
class Observation:
    step: Step
    task: PausedCanaryStamp


@dataclass(frozen=True, slots=True)
class Cleanup:
    unit_inactive: bool
    cgroup_empty: bool
    fixture_removed: bool
    parent_unchanged: bool


def review_held_capture(*, positive, negative, observations, mapping, cleanup):
    """Return a descriptive mapping summary only after both controls and cleanup.

    The stamps are fake correlation data (the negative control never paused at
    entry). An ordered transcript cannot show that facts were actually observed,
    no event was omitted, or a task remained stopped. It is not an authority
    token and is not consumed as evidence by any native or production caller.
    """
    def require(ok):
        if not ok:
            raise HoldReviewError("held capture transcript refused")

    require(type(positive) is PausedCanaryStamp and type(negative) is PausedCanaryStamp)
    require(positive.invocation == negative.invocation and positive.pid != negative.pid
            and positive.pause_nonce != negative.pause_nonce)
    require(type(observations) is tuple and len(observations) == len(_SEQUENCE))
    for step, observation in zip(_SEQUENCE, observations):
        expected = negative if step is Step.NEGATIVE_EXIT_127_REAPED_WITHOUT_ENTRY else positive
        require(type(observation) is Observation and observation.step is step
                and type(observation.task) is PausedCanaryStamp and observation.task == expected)
    require(type(mapping) is MappingObservation
            and type(mapping.mapping_count) is int and mapping.mapping_count == 1
            and type(mapping.segment_count) is int and 1 <= mapping.segment_count <= MAX_SEGMENTS)
    require(type(cleanup) is Cleanup and cleanup.unit_inactive is True
            and cleanup.cgroup_empty is True and cleanup.fixture_removed is True
            and cleanup.parent_unchanged is True)
    return mapping
