"""Inert fixed-loader launch proposal; never readiness or execution authority.

Supplied image/forms are declarations, not measured bytes or observed kernel/
loader behavior. Outstanding requirements cannot be cleared by this contract.
There is no caller, file access, process launch, image writer or consent path.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from pipeline.document_job_worker_elf import LOADER, _soname_valid
from pipeline.document_job_worker_image import WorkerImageInventory, MAX_MEMBERS
from pipeline.document_job_worker_search_form import WorkerSearchFormReview, POLICY as SEARCH_POLICY

POLICY = "worker-fixed-loader-proposal-v1"
ARGV = (LOADER, "--inhibit-cache", "--library-path", "/worker", "--glibc-hwcaps-mask", "", "/worker/llama-server")
ENVIRONMENT = (("LANG", "C"),)
UNRESOLVED = ("independent_pins_and_fresh_complete_measurement", "immutable_namespace_and_exposure",
              "exact_dependency_and_resident_interpreter_resolution", "pinned_loader_runner_compatibility",
              "lifetime_cwd_and_fs_sharing", "descendant_exec_enforcement", "runtime_code_and_plugin_loading",
              "cpu_and_resource_enforcement", "network_and_private_ipc_enforcement", "exact_attempt_private_admission")
FORM_TEXT = {"no_search": (), "origin_runpath": ((29, "$ORIGIN"),),
             "origin_build_empty_runpath": ((29, "$ORIGIN:/build/llama-server-cpu/bin:"),)}


class WorkerLaunchProfileError(ValueError):
    """Content-free invalid supplied launch proposal."""


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True, slots=True, repr=False)
class WorkerLaunchProposal:
    inventory_fingerprint: str
    forms_fingerprint: str
    loader_sha256: str
    policy: str = POLICY
    argv: tuple[str, ...] = ARGV
    environment: tuple[tuple[str, str], ...] = ENVIRONMENT
    unresolved: tuple[str, ...] = UNRESOLVED
    status: str = "proposal_only"

    def __post_init__(self):
        if (not all(_digest(v) for v in (self.inventory_fingerprint, self.forms_fingerprint, self.loader_sha256))
                or type(self.policy) is not str or self.policy != POLICY
                or type(self.argv) is not tuple or any(type(v) is not str for v in self.argv) or self.argv != ARGV
                or type(self.environment) is not tuple or self.environment != ENVIRONMENT
                or any(type(row) is not tuple or any(type(v) is not str for v in row) for row in self.environment)
                or type(self.unresolved) is not tuple or self.unresolved != UNRESOLVED
                or any(type(v) is not str for v in self.unresolved)
                or type(self.status) is not str or self.status != "proposal_only"):
            raise WorkerLaunchProfileError("worker launch proposal is unavailable")

    @property
    def fingerprint(self):
        wire = json.dumps(dict(policy=self.policy, inventory=self.inventory_fingerprint,
                               forms=self.forms_fingerprint, loader=self.loader_sha256,
                               argv=self.argv, environment=self.environment, unresolved=self.unresolved,
                               status=self.status), sort_keys=True, separators=(",", ":")).encode("ascii")
        return sha256(wire).hexdigest()


def propose_worker_launch_profile(inventory, forms):
    """Bind exact declared member/search digests to an initial-process profile.

    Does not check SONAME/dependency closure or simulate the dynamic loader.
    In particular argv flags are not inherited exec enforcement; that remains
    unconditionally unresolved. Unknown other dynamic tags remain unassessed.
    """
    try:
        if type(inventory) is not WorkerImageInventory or type(forms) is not tuple or len(forms) > MAX_MEMBERS:
            raise ValueError
        WorkerImageInventory(inventory.members)
        members = {m.target: m for m in inventory.members}; bound = {}
        for row in forms:
            if type(row) is not tuple or len(row) != 2:
                raise ValueError
            target, review = row
            if (type(target) is not tuple or any(type(c) is not str for c in target) or
                    target not in members or target in bound or type(review) is not WorkerSearchFormReview):
                raise ValueError
            WorkerSearchFormReview(review.raw_sha256, review.search_fingerprint, review.form)
            if review.form not in FORM_TEXT:
                raise ValueError
            expected = sha256(json.dumps(dict(policy=SEARCH_POLICY, tags=FORM_TEXT[review.form]),
                            sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
            member = members[target]
            category, tags = {"no_search": ("no_search_tag", ()),
                              "origin_runpath": ("exact_origin", ("runpath",)),
                              "origin_build_empty_runpath": ("mixed_or_unsupported", ("runpath",))}[review.form]
            if (review.raw_sha256 != member.dependencies.raw_sha256 or review.search_fingerprint != expected or
                    (member.search.category, member.search.tags) != (category, tags)):
                raise ValueError
            bound[target] = review
        if set(bound) != set(members):
            raise ValueError
        counts = {role: 0 for role in ("entrypoint", "plugin", "interpreter", "library")}
        loader_target = tuple(LOADER.lstrip("/").split("/"))
        hashes = set()
        for target, m in members.items():
            counts[m.role] += 1; d = m.dependencies; form = bound[target].form
            if d.raw_sha256 in hashes:
                raise ValueError
            hashes.add(d.raw_sha256)
            if m.role == "interpreter":
                if (target != loader_target or d.object_kind != "shared_object" or
                        d.interpreter is not None or d.needed or form != "no_search"):
                    raise ValueError
            elif m.role == "entrypoint":
                if (target != ("worker", "llama-server") or d.object_kind != "executable" or
                        d.interpreter != LOADER or form != "origin_runpath"):
                    raise ValueError
            elif m.role == "plugin":
                if (target != ("worker", "libggml-cpu-x64.so") or d.object_kind != "shared_object" or
                        d.interpreter is not None or form != "origin_build_empty_runpath"):
                    raise ValueError
            elif (len(target) != 2 or target[0] != "worker" or not _soname_valid(target[1]) or
                  target[1] == loader_target[-1] or d.object_kind != "shared_object" or
                  form not in ("no_search", "origin_runpath")):
                raise ValueError
        if any(counts[r] != 1 for r in ("entrypoint", "plugin", "interpreter")):
            raise ValueError
        wire = json.dumps([(p, bound[p].raw_sha256, bound[p].search_fingerprint, bound[p].form)
                           for p in sorted(bound)], separators=(",", ":")).encode("ascii")
        return WorkerLaunchProposal(inventory.fingerprint, sha256(wire).hexdigest(),
                                    members[loader_target].dependencies.raw_sha256)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise WorkerLaunchProfileError("worker launch proposal is unavailable") from None
