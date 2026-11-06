"""Pure descriptive dispatch lifecycle, not a controller or authority object.

Caller-supplied events describe what a future trusted controller observed.
Returning 'inflight' neither burns consent nor permits any write. No storage,
clock, provider, socket, process, replay registry or automatic retry exists here.
Native enforcement and opaque exact-attempt admission remain separate gates.
"""
from dataclasses import dataclass

STATES = frozenset({"prepared", "inflight", "completed", "fenced"})
EVENTS = frozenset({"dispatch_burned", "response_valid", "response_invalid",
                    "cancel", "timeout", "disconnect", "binding_changed", "restart"})


class WorkerLifecycleError(ValueError):
    """Content-free refusal of malformed descriptive lifecycle data."""


@dataclass(frozen=True)
class WorkerLifecycle:
    state: str = "prepared"
    disclosure_possible: bool = False

    def __post_init__(self):
        if (type(self.state) is not str or self.state not in STATES
                or type(self.disclosure_possible) is not bool
                or (self.state == "prepared" and self.disclosure_possible)
                or (self.state in {"inflight", "completed"} and not self.disclosure_possible)):
            raise WorkerLifecycleError("worker lifecycle description is invalid")


def advance_worker_lifecycle(current, event):
    """Return a new description or refuse an impossible/replayed transition.

    Slot burn is conservative: disclosure may occur even if a later write fails.
    Cancellation/disconnect/restart never establishes provider termination.
    Rejected/late completion cannot reopen a fenced/completed dispatch. A new
    descriptive object is freely constructible and grants no new attempt/consent.
    'response_valid' means envelope validated, NOT factual/extraction quality.
    """
    if type(current) is not WorkerLifecycle:
        raise WorkerLifecycleError("worker lifecycle description is invalid")
    current.__post_init__()
    if type(event) is not str or event not in EVENTS:
        raise WorkerLifecycleError("worker lifecycle event is invalid")
    if current.state in {"completed", "fenced"}:
        raise WorkerLifecycleError("worker dispatch is terminal")
    if event in {"cancel", "timeout", "disconnect", "binding_changed", "restart"}:
        return WorkerLifecycle("fenced", current.disclosure_possible)
    if current.state == "prepared" and event == "dispatch_burned":
        return WorkerLifecycle("inflight", True)
    if current.state == "inflight" and event in {"response_valid", "response_invalid"}:
        return WorkerLifecycle("completed" if event == "response_valid" else "fenced", True)
    raise WorkerLifecycleError("worker lifecycle transition is invalid")
