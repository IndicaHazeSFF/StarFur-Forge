"""Post-acknowledgement controller for the synthetic cooperative test.

No native launcher or manager/filesystem adapters. All effectful callbacks
are trusted, attempt-scoped adapters, not model/user supplied operations.
"""

from dataclasses import dataclass
import time

from scripts.private_worker_cooperative_exit_read import observe_worker_exit
from scripts.private_worker_cooperative_startup import Binding, StartupRefused, StartupReview


@dataclass(frozen=True, slots=True)
class PinnedWorker:
    binding: Binding
    pidfd: int
    identity: tuple[int, int]


@dataclass(frozen=True, slots=True)
class CaseResults:
    binding: Binding
    positive: int
    negative: int


@dataclass(frozen=True, slots=True)
class Retirement:
    binding: Binding
    descendants_exited: bool
    unit_collected: bool
    cgroup_absent: bool
    parent_unchanged: bool
    epoch_continuity: bool


def complete_acknowledged_attempt(review, *, acquire_verified_pin, recheck_pin,
                                  publish_go, read_cases, await_retirement,
                                  cleanup_exact_fixture):
    """Join case, exit and retirement evidence with the held pre-go pidfd.

    The caller owns durable charge and the single, verified start response.
    The pin context owns the verified pidfd until after retirement; adapters
    must not close, replace or reacquire it. Recheck independently verifies
    liveness and current invocation before go. Adapters enforce the shared
    deadline for I/O and independently bind their evidence; epoch continuity
    is not implied by a final not-found lookup. Cleanup may touch only the
    separately verified test fixture and runs only after retirement and pin
    cleanup. Any ambiguous callback outcome is terminal; there is no retry,
    manager mutation, cleanup fallback, or native caller in this module.
    """
    if type(review) is not StartupReview:
        raise StartupRefused("cooperative startup refused")
    now = time.monotonic_ns
    try:
        expires = review.check_acknowledged(now=now())
        with acquire_verified_pin(expires) as pin:
            if (type(pin) is not PinnedWorker or type(pin.pidfd) is not int
                    or not 0 <= pin.pidfd < 1 << 31
                    or type(pin.identity) is not tuple or len(pin.identity) != 2
                    or not all(type(n) is int and 0 <= n < 1 << 64 for n in pin.identity)
                    or pin.identity[1] == 0):
                review.refuse()
            review.bind(now=now(), binding=pin.binding, ready=True, pin_verified=True)
            current = recheck_pin(pin, expires)
            go = review.issue_go(now=now(), current=current)
            publish_go(go)
            cases = read_cases(pin, expires)
            if type(cases) is not CaseResults:
                review.refuse()
            review.result(now=now(), binding=cases.binding, positive=cases.positive,
                          negative=cases.negative)
            removal = await_retirement(pin, expires)
            if type(removal) is not Retirement or removal.binding is not pin.binding:
                review.refuse()
            terminal = observe_worker_exit(pin.pidfd, expected_identity=pin.identity,
                                           binding=pin.binding, expires_ns=expires)
            review.retire(now=now(), binding=removal.binding, worker_exit=terminal,
                          descendants_exited=removal.descendants_exited,
                          unit_collected=removal.unit_collected, cgroup_absent=removal.cgroup_absent,
                          parent_unchanged=removal.parent_unchanged,
                          epoch_continuity=removal.epoch_continuity)
        review.check_retired(now=now())
        cleaned = cleanup_exact_fixture(expires)
        review.finish(now=now(), fixture_cleanup_verified=cleaned)
    except BaseException:
        review.invalidate()
        raise
