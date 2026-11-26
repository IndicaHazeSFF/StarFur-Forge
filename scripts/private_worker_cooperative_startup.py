"""Fake-only lifecycle for one cooperative synthetic supervisor attempt.

Consumes supplied observations; no manager, filesystem, or process adapter.
Object lifetime is not durable attempt charging or restart recovery.
"""

from dataclasses import dataclass
from enum import Enum, auto
import re


class StartupRefused(ValueError):
    pass


class Phase(Enum):
    NEW = auto()
    CHARGED = auto()
    ACKNOWLEDGED = auto()
    BOUND = auto()
    GO_ISSUED = auto()
    RESULT_OBSERVED = auto()
    RETIRED = auto()
    PASSED = auto()
    REFUSED = auto()


@dataclass(frozen=True, slots=True)
class Binding:
    attempt: object
    epoch: str
    # Opaque token supplied by the fake verified-handle owner, not a PID.
    worker: object


@dataclass(frozen=True, slots=True)
class Go:
    binding: Binding
    expires: int


@dataclass(frozen=True, slots=True)
class WorkerExit:
    """Supplied normalized kernel observation, never acquired here.

    The trusted adapter must check the ABI and returned EXIT bit and bind the
    observation to the continuously held worker pidfd, not a reopened PID.
    """

    binding: Binding
    at: int
    readable: bool
    exit_present: bool
    raw_status: int


def _time(value):
    return type(value) is int and value >= 0


def go_is_current(go, *, binding, expires, now):
    """Pure worker-side comparison, not acquisition or one-use consumption."""
    return (type(go) is Go and type(binding) is Binding and go.binding is binding
            and _time(now) and _time(expires) and _time(go.expires)
            and go.expires == expires and now < expires)


class StartupReview:
    """Single-controller fake review; effects are never performed here.

    Caller must attest verified properties, exact pin, result and retirement.
    Once charged, replace neither this record nor its approved attempt after
    refusal. Unknown evidence cannot be upgraded by a later observation.
    """

    def __init__(self, *, attempt, expires):
        if type(attempt) is not object or not _time(expires):
            raise StartupRefused("cooperative startup refused")
        self._attempt = attempt
        self._expires = expires
        self._now = -1
        self._binding = None
        self._phase = Phase.NEW
        self._charged = False

    @property
    def phase(self):
        return self._phase

    @property
    def charged(self):
        return self._charged

    def invalidate(self):
        if self._phase is not Phase.PASSED:
            self._phase = Phase.REFUSED

    def refuse(self):
        self.invalidate()
        raise StartupRefused("cooperative startup refused")

    def _fence(self, phase, now, *checks):
        if (self._phase is not phase or not _time(now)
                or not self._now <= now < self._expires
                or not all(check is True for check in checks)):
            self.refuse()
        self._now = now

    def charge(self, *, now, preflight):
        self._fence(Phase.NEW, now, preflight)
        self._charged = True
        self._phase = Phase.CHARGED

    def acknowledge_start(self, *, now, acknowledged):
        self._fence(Phase.CHARGED, now, acknowledged)
        self._phase = Phase.ACKNOWLEDGED

    def check_acknowledged(self, *, now):
        self._fence(Phase.ACKNOWLEDGED, now)
        return self._expires

    def bind(self, *, now, binding, ready, pin_verified):
        valid = (type(binding) is Binding and binding.attempt is self._attempt
                 and type(binding.worker) is object and type(binding.epoch) is str
                 and re.fullmatch(r"[0-9a-f]{32}", binding.epoch) is not None
                 and binding.epoch != "0" * 32)
        self._fence(Phase.ACKNOWLEDGED, now, valid, ready, pin_verified)
        self._binding = binding
        self._phase = Phase.BOUND

    def issue_go(self, *, now, current):
        self._fence(Phase.BOUND, now, current is self._binding)
        self._phase = Phase.GO_ISSUED
        return Go(self._binding, self._expires)

    def result(self, *, now, binding, positive, negative):
        self._fence(Phase.GO_ISSUED, now, binding is self._binding,
                    type(positive) is int and positive == 42,
                    type(negative) is int and negative == 127)
        self._phase = Phase.RESULT_OBSERVED

    def retire(self, *, now, binding, worker_exit, descendants_exited,
               unit_collected, cgroup_absent, parent_unchanged, epoch_continuity):
        clean_exit = (type(worker_exit) is WorkerExit
                      and worker_exit.binding is self._binding
                      and worker_exit.readable is True and worker_exit.exit_present is True
                      and type(worker_exit.raw_status) is int and worker_exit.raw_status == 0
                      and _time(worker_exit.at) and _time(now)
                      and self._now <= worker_exit.at <= now)
        self._fence(Phase.RESULT_OBSERVED, now, binding is self._binding,
                    clean_exit, descendants_exited, unit_collected,
                    cgroup_absent, parent_unchanged, epoch_continuity)
        self._phase = Phase.RETIRED

    def finish(self, *, now, fixture_cleanup_verified):
        self._fence(Phase.RETIRED, now, fixture_cleanup_verified)
        self._phase = Phase.PASSED

    def check_retired(self, *, now):
        self._fence(Phase.RETIRED, now)
