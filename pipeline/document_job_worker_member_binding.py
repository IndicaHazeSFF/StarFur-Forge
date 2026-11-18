"""Pure supplied member-observation/layout binding, never deployment evidence.

Expected pins must be selected independently by a trusted caller. This function
cannot authenticate their origin, revalidate live files, retain handles, copy or
seal bytes, prove freshness/CPU behavior, or grant private disclosure/launch.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import stat

from pipeline.document_job_worker_dependencies import WorkerDependencyPlan, WorkerLibraryAlias
from pipeline.document_job_worker_elf_file import WorkerElfIdentityObservation
from pipeline.document_job_worker_image import MAX_MEMBERS, MAX_MEMBER_BYTES, MAX_TOTAL_BYTES
from pipeline.document_job_worker_layout import check_worker_proposed_layout

POLICY = "worker-supplied-member-binding-v1"


class WorkerMemberBindingError(ValueError):
    """Content-free invalid or unequal supplied snapshot."""


@dataclass(frozen=True, slots=True, repr=False)
class WorkerExpectedMember:
    target: tuple[str, ...]
    raw_sha256: str
    byte_count: int
    source_mode: int
    source_uid: int

    def __post_init__(self):
        try:
            WorkerLibraryAlias("libpin.so", self.target)
            if (type(self.raw_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", self.raw_sha256) is None
                    or type(self.byte_count) is not int or not 64 <= self.byte_count <= MAX_MEMBER_BYTES
                    or type(self.source_mode) is not int or not 0 <= self.source_mode <= 0xffff
                    or not stat.S_ISREG(self.source_mode) or self.source_mode & 0o7022
                    or type(self.source_uid) is not int or self.source_uid < 0):
                raise ValueError
        except ValueError:
            raise WorkerMemberBindingError("worker member binding is unavailable") from None


@dataclass(frozen=True, slots=True, repr=False)
class WorkerMemberBinding:
    plan_fingerprint: str
    observation_fingerprint: str
    member_count: int
    total_bytes: int

    def __post_init__(self):
        if (any(type(h) is not str or re.fullmatch(r"[0-9a-f]{64}", h) is None
                for h in (self.plan_fingerprint, self.observation_fingerprint)) or
                type(self.member_count) is not int or not 1 <= self.member_count <= MAX_MEMBERS or
                type(self.total_bytes) is not int or not 64 <= self.total_bytes <= MAX_TOTAL_BYTES):
            raise WorkerMemberBindingError("worker member binding is unavailable")


def bind_worker_member_observations(plan, expected, observations, assignments):
    """Bind exact coverage/hash/size/source-mode/uid/metadata to a proposed layout.

    Observations are supplied (target, WorkerElfIdentityObservation) pairs, not
    fresh acquisitions made here. Success is snapshot equality, not immutable
    backing, independently verified provenance, deployment readiness or consent.
    """
    try:
        if type(plan) is not WorkerDependencyPlan:
            raise ValueError
        WorkerDependencyPlan(plan.inventory, plan.aliases)
        members = {m.target: m for m in plan.inventory.members}
        if (type(expected) is not tuple or type(observations) is not tuple or
                not 1 <= len(expected) <= MAX_MEMBERS or not 1 <= len(observations) <= MAX_MEMBERS):
            raise ValueError
        pins, found, inodes = {}, {}, set()
        for pin in expected:
            if type(pin) is not WorkerExpectedMember:
                raise ValueError
            WorkerExpectedMember(pin.target, pin.raw_sha256, pin.byte_count, pin.source_mode, pin.source_uid)
            if pin.target not in members or pin.target in pins:
                raise ValueError
            pins[pin.target] = pin
        for row in observations:
            if type(row) is not tuple or len(row) != 2:
                raise ValueError
            target, value = row
            if (type(target) is not tuple or any(type(c) is not str for c in target) or
                    target not in pins or target in found or type(value) is not WorkerElfIdentityObservation):
                raise ValueError
            WorkerElfIdentityObservation(value.file, value.search, value.soname)
            member, pin = members[target], pins[target]
            identity = value.file.identity
            if (value.file.dependencies != member.dependencies or value.search != member.search or
                    value.file.dependencies.raw_sha256 != pin.raw_sha256 or
                    identity[5] != pin.byte_count or member.byte_count != pin.byte_count or
                    identity[2] != pin.source_mode or identity[3] != pin.source_uid or
                    identity[:2] in inodes):
                raise ValueError
            found[target] = value; inodes.add(identity[:2])
        if set(pins) != set(members) or set(found) != set(members):
            raise ValueError
        total = sum(p.byte_count for p in pins.values())
        if total > MAX_TOTAL_BYTES:
            raise ValueError
        providers = {a.target for a in plan.aliases}
        layout = check_worker_proposed_layout(plan, tuple((p, found[p].soname) for p in sorted(providers)), assignments)
        wire = json.dumps(dict(policy=POLICY, plan=layout.plan_fingerprint,
                               members=[(p, found[p].file.dependencies.raw_sha256, found[p].file.identity)
                                        for p in sorted(found)]), separators=(",", ":"), sort_keys=True).encode("ascii")
        return WorkerMemberBinding(layout.plan_fingerprint, sha256(wire).hexdigest(), len(found), total)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise WorkerMemberBindingError("worker member binding is unavailable") from None
