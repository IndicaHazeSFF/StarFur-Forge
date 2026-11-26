"""Compare independently supplied C8l launch manifests; never acquire or launch."""

from dataclasses import dataclass
from hashlib import sha256
import re

from scripts.private_worker_cooperative_charge_scope import _digest


POLICY = ("cpu-quota=100%", "cpu-period-us=100000", "memory-max=268435456",
          "swap-max=0", "tasks-max=16", "active-us=10000000",
          "stop-grace-us=2000000", "restart=no", "kill-mode=control-group",
          "send-sigkill=yes", "no-new-privileges=yes")
FIXTURES = ("leaf", "main", "resident-request")


class LaunchPlanRefused(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    sources: tuple[tuple[str, str], ...]
    fixtures: tuple[tuple[str, str], ...]
    command_spec_sha256: str
    policy: tuple[str, ...]


def _rows_valid(rows, count):
    return (type(rows) is tuple and 1 <= len(rows) <= count
            and all(type(row) is tuple and len(row) == 2 and type(row[0]) is str
                    and len(row[0]) <= 96 and _digest(row[1]) for row in rows))


def _valid(plan):
    if not (type(plan) is LaunchPlan and _digest(plan.command_spec_sha256)
            and type(plan.policy) is tuple and len(plan.policy) == len(POLICY)
            and all(type(v) is str for v in plan.policy) and plan.policy == POLICY
            and _rows_valid(plan.sources, 48) and _rows_valid(plan.fixtures, len(FIXTURES))):
        return False
    names = tuple(name for name, _ in plan.sources)
    return (all(re.fullmatch(r"(?:scripts/private_worker_|pipeline/document_job_worker_)[a-z0-9_]+\.py",
                             name) is not None for name in names)
            and names == tuple(sorted(set(names)))
            and tuple(name for name, _ in plan.fixtures) == FIXTURES)


def bind_launch_plan(*, expected, observed):
    """Return a scoped digest only for exact supplied coverage and content.

    The separately reviewed expected manifest must enumerate the actual
    trusted source closure. Command specification covers the fixed selector,
    unit template, executable/argv/environment, remaining unit properties
    and positive/negative composition. This code cannot attest that the list
    is complete, the specification is safe, or any supplied bytes were read.
    """
    if not _valid(expected) or not _valid(observed) or expected != observed:
        raise LaunchPlanRefused("cooperative launch plan refused")
    pieces = ("starfur-cooperative-launch-plan-v1", expected.command_spec_sha256,
              *expected.policy, *(f"source:{key}:{digest}" for key, digest in expected.sources),
              *(f"fixture:{key}:{digest}" for key, digest in expected.fixtures))
    return sha256(("\n".join(pieces) + "\n").encode("ascii")).hexdigest()
