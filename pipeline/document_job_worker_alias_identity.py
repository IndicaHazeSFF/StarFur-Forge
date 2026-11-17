"""Pure alias/declared-SONAME comparison, not trusted image or loader policy.

Inputs are supplied plans and observations. Hash equality binds declarations,
not measured immutable backing, provenance, resolution order or launch authority.
Missing/different SONAMEs are explicit review outcomes, never filename guesses.
"""
from dataclasses import dataclass
import re

from pipeline.document_job_worker_dependencies import WorkerDependencyPlan, WorkerLibraryAlias, MAX_ALIASES
from pipeline.document_job_worker_elf_soname import WorkerElfSonameReview
from pipeline.document_job_worker_image import MAX_MEMBERS

POLICY = "worker-alias-soname-review-v1"
STATES = frozenset({"declared_soname_matches", "declared_soname_differs", "declared_soname_absent"})


class WorkerAliasIdentityError(ValueError):
    """Content-free malformed or unbound supplied comparison."""


@dataclass(frozen=True, slots=True, repr=False)
class WorkerAliasIdentityReview:
    plan_fingerprint: str
    outcomes: tuple[tuple[str, tuple[str, ...], str], ...]

    def __post_init__(self):
        try:
            if (type(self.plan_fingerprint) is not str or
                    re.fullmatch(r"[0-9a-f]{64}", self.plan_fingerprint) is None or
                    type(self.outcomes) is not tuple or len(self.outcomes) > MAX_ALIASES):
                raise ValueError
            names = []
            for row in self.outcomes:
                if type(row) is not tuple or len(row) != 3 or type(row[2]) is not str or row[2] not in STATES:
                    raise ValueError
                WorkerLibraryAlias(row[0], row[1]); names.append(row[0])
            if len(set(names)) != len(names):
                raise ValueError
            object.__setattr__(self, "outcomes", tuple(sorted(self.outcomes)))
        except (ValueError, TypeError):
            raise WorkerAliasIdentityError("worker alias identity review is unavailable") from None


def review_worker_alias_identities(plan, identities) -> WorkerAliasIdentityReview:
    """Compare exact aliases with supplied (logical target, SONAME review) pairs.

    Require exactly one same-hash observation for every alias-provider target,
    no missing/extra/duplicate sidecars. Comparisons are case-sensitive. Even
    all-match output is not independent acquisition, accepted identity, safe
    search behavior, SONAME version compatibility, dlopen closure or permission.
    """
    try:
        if (type(plan) is not WorkerDependencyPlan or type(identities) is not tuple
                or len(identities) > MAX_MEMBERS):
            raise ValueError
        WorkerDependencyPlan(plan.inventory, plan.aliases)
        members = {member.target: member for member in plan.inventory.members}
        required = {alias.target for alias in plan.aliases}
        observed = {}
        for pair in identities:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError
            target, observation = pair
            if (type(target) is not tuple or any(type(c) is not str for c in target)
                    or target not in required or target in observed
                    or type(observation) is not WorkerElfSonameReview):
                raise ValueError
            WorkerElfSonameReview(observation.raw_sha256, observation.soname)
            if observation.raw_sha256 != members[target].dependencies.raw_sha256:
                raise ValueError
            observed[target] = observation.soname
        if set(observed) != required:
            raise ValueError
        rows = tuple((alias.name, alias.target,
                      "declared_soname_absent" if observed[alias.target] is None else
                      "declared_soname_matches" if observed[alias.target] == alias.name else
                      "declared_soname_differs") for alias in plan.aliases)
        return WorkerAliasIdentityReview(plan.fingerprint, rows)
    except (ValueError, TypeError, AttributeError):
        raise WorkerAliasIdentityError("worker alias identity review is unavailable") from None
