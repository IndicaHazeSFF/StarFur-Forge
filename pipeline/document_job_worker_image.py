"""Pure bounded proposed image inventory; no acquisition or execution authority.

Logical POSIX destinations describe regular-file copies, never host paths or
symlinks. Supplied metadata is not independently measured image content. This
contract does not resolve dependencies, prove CPU behavior or accept RUNPATHs.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from pipeline.document_job_worker_elf import ElfDependencies
from pipeline.document_job_worker_elf_search import WorkerElfSearchReview

POLICY = "worker-image-inventory-v1"
MAX_MEMBERS = 64
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 64 * 1024 * 1024


class WorkerImageError(ValueError):
    """Content-free invalid supplied inventory."""


@dataclass(frozen=True, slots=True, repr=False)
class WorkerImageMember:
    target: tuple[str, ...]
    byte_count: int
    role: str
    dependencies: ElfDependencies
    search: WorkerElfSearchReview

    def __post_init__(self):
        if (type(self.target) is not tuple or not 1 <= len(self.target) <= 8 or
                any(type(c) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", c)
                    is None for c in self.target) or
                sum(len(c) for c in self.target) + len(self.target) - 1 > 512 or
                type(self.byte_count) is not int or not 64 <= self.byte_count <= MAX_MEMBER_BYTES or
                type(self.role) is not str or self.role not in
                ("entrypoint", "interpreter", "library", "plugin") or
                type(self.dependencies) is not ElfDependencies or
                type(self.search) is not WorkerElfSearchReview):
            raise WorkerImageError("worker image inventory is unavailable")
        try:
            ElfDependencies(self.dependencies.raw_sha256, self.dependencies.object_kind,
                            self.dependencies.interpreter, self.dependencies.needed)
            WorkerElfSearchReview(self.search.raw_sha256, self.search.category, self.search.tags)
        except ValueError:
            raise WorkerImageError("worker image inventory is unavailable") from None
        if self.dependencies.raw_sha256 != self.search.raw_sha256:
            raise WorkerImageError("worker image inventory is unavailable")


@dataclass(frozen=True, slots=True, repr=False)
class WorkerImageInventory:
    members: tuple[WorkerImageMember, ...]

    def __post_init__(self):
        if (type(self.members) is not tuple or not 1 <= len(self.members) <= MAX_MEMBERS
                or any(type(m) is not WorkerImageMember for m in self.members)):
            raise WorkerImageError("worker image inventory is unavailable")
        for member in self.members:
            WorkerImageMember(member.target, member.byte_count, member.role,
                              member.dependencies, member.search)
        paths = [m.target for m in self.members]
        folded = [tuple(c.casefold() for c in p) for p in paths]
        if (len(set(folded)) != len(paths) or
                any(p[:len(q)] == q for p in folded for q in folded if len(q) < len(p)) or
                sum(m.role == "entrypoint" for m in self.members) != 1 or
                self.total_bytes > MAX_TOTAL_BYTES):
            raise WorkerImageError("worker image inventory is unavailable")
        object.__setattr__(self, "members", tuple(sorted(self.members, key=lambda m: m.target)))

    @property
    def total_bytes(self):
        return sum(m.byte_count for m in self.members)

    @property
    def fingerprint(self):
        """Identity of supplied declarations, not a measured/sealed image digest."""
        rows = [dict(target=m.target, byte_count=m.byte_count, role=m.role,
                     raw_sha256=m.dependencies.raw_sha256,
                     object_kind=m.dependencies.object_kind,
                     interpreter=m.dependencies.interpreter, needed=m.dependencies.needed,
                     search_category=m.search.category, search_tags=m.search.tags)
                for m in self.members]
        wire = json.dumps(dict(policy=POLICY, members=rows), sort_keys=True,
                          separators=(",", ":"), ensure_ascii=True).encode("ascii")
        return sha256(wire).hexdigest()
