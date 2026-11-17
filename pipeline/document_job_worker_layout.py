"""Pure conservative proposed-layout consistency, never loader acceptance.

Only a self-contained exact DT_RUNPATH=$ORIGIN subset is checked. Mixed paths,
RPATH, default lookup and runtime dlopen are NOT modeled or approved. Supplied
hashes/SONAMEs are declarations, not measured bytes, sealing or permission.
"""
from dataclasses import dataclass
import re

from pipeline.document_job_worker_alias_identity import review_worker_alias_identities
from pipeline.document_job_worker_dependencies import WorkerDependencyPlan, WorkerLibraryAlias
from pipeline.document_job_worker_elf import LOADER

POLICY = "worker-proposed-origin-layout-v1"
MAX_EDGES = 2048
RESERVED = frozenset({"proc", "sys", "dev", "tmp", "cwd", "build", "etc", "run", "home", "mnt"})


class WorkerLayoutError(ValueError):
    """Closed refusal reason; no caller content in error messages."""


@dataclass(frozen=True, slots=True, repr=False)
class WorkerLayoutEdge:
    requester: tuple[str, ...]
    needed: str
    target: tuple[str, ...]

    def __post_init__(self):
        WorkerLibraryAlias(self.needed, self.requester)
        WorkerLibraryAlias(self.needed, self.target)


@dataclass(frozen=True, slots=True, repr=False)
class WorkerLayoutReview:
    plan_fingerprint: str
    edge_count: int
    status: str = "internally_consistent_proposed_layout"

    def __post_init__(self):
        if (type(self.plan_fingerprint) is not str or
                re.fullmatch(r"[0-9a-f]{64}", self.plan_fingerprint) is None or
                type(self.edge_count) is not int or not 0 <= self.edge_count <= MAX_EDGES or
                self.status != "internally_consistent_proposed_layout"):
            raise WorkerLayoutError("worker layout refused: invalid_review")


def check_worker_proposed_layout(plan, identities, assignments):
    """Check exact regular-file targets already declared by the inventory.

    No remapping, symlinks, copies, filesystem reads or search simulation.
    PT_INTERP is checked separately at its fixed path, not an alias exception.
    In particular, a transitive dependency cannot borrow its parent's ORIGIN.
    """
    def require(condition, reason):
        if not condition:
            raise WorkerLayoutError("worker layout refused: " + reason)
    try:
        require(type(plan) is WorkerDependencyPlan, "invalid_input")
        WorkerDependencyPlan(plan.inventory, plan.aliases)
        require(type(assignments) is tuple and len(assignments) <= MAX_EDGES, "invalid_assignments")
        for row in assignments:
            require(type(row) is WorkerLayoutEdge, "invalid_assignments")
            WorkerLayoutEdge(row.requester, row.needed, row.target)
        supplied = tuple((r.requester, r.needed, r.target) for r in assignments)
        require(len(set(supplied)) == len(supplied) and set(supplied) == set(plan.edges), "edge_coverage")
        review = review_worker_alias_identities(plan, identities)
        require(all(r[2] == "declared_soname_matches" for r in review.outcomes), "soname_not_matching")
        members = {m.target: m for m in plan.inventory.members}
        hashes = [m.dependencies.raw_sha256 for m in members.values()]
        require(len(set(hashes)) == len(hashes), "duplicate_declared_bytes")
        for member in members.values():
            require(member.target[0].casefold() not in RESERVED, "reserved_destination")
            search = member.search
            require((search.category, search.tags) in
                    (("no_search_tag", ()), ("exact_origin", ("runpath",))), "unsupported_search")
            if member.dependencies.needed:
                require(search.category == "exact_origin", "dependency_search_missing")
            if member.role == "interpreter":
                require(member.target == tuple(LOADER.lstrip("/").split("/")) and
                        member.dependencies.interpreter is None, "interpreter_binding")
        for requester, name, target in supplied:
            require(target == requester[:-1] + (name,), "dependency_not_at_origin")
            require(members[target].role == "library", "alias_not_library")
        return WorkerLayoutReview(plan.fingerprint, len(supplied))
    except WorkerLayoutError:
        raise
    except (ValueError, TypeError, AttributeError, KeyError):
        raise WorkerLayoutError("worker layout refused: invalid_input") from None
