"""Pure equality binding for the single C8l synthetic charge receipt.

The expected record must come from separately reviewed approval and anchor
evidence, never from the observation being checked. No acquisition, freshness
check, filesystem access, charging, or supervisor authority.
"""

from dataclasses import dataclass
from hashlib import sha256
import re


APPROVAL = "c8l-cooperative-one-shot"


class ChargeScopeRefused(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ChargeScope:
    approval: str
    directory_uid: int
    directory_identity: tuple[int, int]
    loader_sha256: str
    launch_plan_sha256: str


def _digest(value):
    return (type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None
            and value != "0" * 64)


def _number(value, limit):
    return type(value) is int and 0 <= value < limit


def _valid(scope):
    return (type(scope) is ChargeScope and type(scope.approval) is str
            and scope.approval == APPROVAL
            and _number(scope.directory_uid, 1 << 32) and scope.directory_uid > 0
            and type(scope.directory_identity) is tuple and len(scope.directory_identity) == 2
            and all(_number(n, 1 << 64) for n in scope.directory_identity)
            and scope.directory_identity[1] > 0
            and _digest(scope.loader_sha256) and _digest(scope.launch_plan_sha256))


def bind_charge_scope(*, expected, observed):
    """Return a domain-separated receipt digest for an exact supplied match.

    The launch-plan pin represents the reviewed fixed fixture/controller
    manifest and exact unit/limit policy, not measured live enforcement.
    The receipt basename remains fixed; different hashes do not re-arm it.
    """
    if not _valid(expected) or not _valid(observed) or observed != expected:
        raise ChargeScopeRefused("cooperative charge scope refused")
    device, inode = expected.directory_identity
    fields = ("starfur-cooperative-charge-scope-v1", expected.approval,
              str(expected.directory_uid), str(device), str(inode),
              expected.loader_sha256, expected.launch_plan_sha256)
    return sha256(("\n".join(fields) + "\n").encode("ascii")).hexdigest()
