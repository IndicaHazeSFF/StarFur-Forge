"""Pure declared lookup requirements; NOT actual resolution or image approval."""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from pipeline.document_job_worker_alias_identity import review_worker_alias_identities
from pipeline.document_job_worker_dependencies import WorkerDependencyPlan
from pipeline.document_job_worker_elf import LOADER
from pipeline.document_job_worker_launch_profile import WorkerLaunchProposal, propose_worker_launch_profile, UNRESOLVED

POLICY = "worker-declared-lookup-requirements-v1"


class WorkerLookupRequirementError(ValueError):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class WorkerLookupRequirements:
    profile_fingerprint: str
    requirements_fingerprint: str
    dependency_count: int
    unresolved: tuple[str, ...] = UNRESOLVED
    status: str = "requirements_only"

    def __post_init__(self):
        if (any(type(v) is not str or re.fullmatch(r"[0-9a-f]{64}", v) is None
                for v in (self.profile_fingerprint, self.requirements_fingerprint)) or
                type(self.dependency_count) is not int or not 0 <= self.dependency_count <= 2048 or
                type(self.unresolved) is not tuple or self.unresolved != UNRESOLVED or
                any(type(v) is not str for v in self.unresolved) or
                type(self.status) is not str or self.status != "requirements_only"):
            raise WorkerLookupRequirementError("worker lookup requirements are unavailable")


def review_worker_lookup_requirements(plan, forms, identities, profile):
    """Recompute profile and bind each declared needed name to one proposed file.

    Regular providers require exact /worker/SONAME targets; the sole resident
    interpreter uses its fixed path/role/digest. These are requirements for a
    future loader test, NOT a simulation of actual lookup, loaded-object reuse,
    symbol/version compatibility, code closure, sealing or descendant behavior.
    Supplied declarations never authenticate bytes; every gate stays unresolved.
    """
    try:
        if type(plan) is not WorkerDependencyPlan or type(profile) is not WorkerLaunchProposal:
            raise ValueError
        WorkerDependencyPlan(plan.inventory, plan.aliases)
        expected = propose_worker_launch_profile(plan.inventory, forms)
        if profile != expected:
            raise ValueError
        identities_review = review_worker_alias_identities(plan, identities)
        if any(row[2] != "declared_soname_matches" for row in identities_review.outcomes):
            raise ValueError
        members = {m.target: m for m in plan.inventory.members}
        loader = tuple(LOADER.lstrip("/").split("/")); edges = []
        for requester, name, target in plan.edges:
            provider = members[target]
            if name == loader[-1]:
                if (target != loader or provider.role != "interpreter" or
                        provider.dependencies.raw_sha256 != profile.loader_sha256):
                    raise ValueError
                mode = "resident_interpreter_requirement"
            else:
                if target != ("worker", name) or provider.role != "library":
                    raise ValueError
                mode = "private_library_path_requirement"
            edges.append((requester, name, target, provider.dependencies.raw_sha256, mode))
        wire = json.dumps(dict(policy=POLICY, plan=plan.fingerprint, profile=profile.fingerprint,
                               edges=edges), sort_keys=True, separators=(",", ":")).encode("ascii")
        return WorkerLookupRequirements(profile.fingerprint, sha256(wire).hexdigest(), len(edges))
    except (ValueError, TypeError, AttributeError, KeyError):
        raise WorkerLookupRequirementError("worker lookup requirements are unavailable") from None
