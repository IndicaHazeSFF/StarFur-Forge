"""Pure explicit alias/dependency assignment, not dynamic-loader simulation.

Assignments bind logical names to declared members. They do not validate actual
SONAMEs, resolution order, dlopen coverage, immutable backing, CPU behavior or
execution eligibility. No symlink, host lookup, provider or image is created.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from pipeline.document_job_worker_elf import LOADER, _soname_valid
from pipeline.document_job_worker_image import WorkerImageInventory

POLICY = "worker-image-declared-dependencies-v1"
MAX_ALIASES = 128


class WorkerDependencyError(ValueError):
    """Content-free invalid declared dependency assignment."""


@dataclass(frozen=True, slots=True, repr=False)
class WorkerLibraryAlias:
    name: str
    target: tuple[str, ...]

    def __post_init__(self):
        if (not _soname_valid(self.name) or type(self.target) is not tuple or
                not 1 <= len(self.target) <= 8 or
                any(type(c) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", c)
                    is None for c in self.target) or
                sum(len(c) for c in self.target) + len(self.target) - 1 > 512):
            raise WorkerDependencyError("worker dependency assignment is unavailable")


@dataclass(frozen=True, slots=True, repr=False)
class WorkerDependencyPlan:
    inventory: WorkerImageInventory
    aliases: tuple[WorkerLibraryAlias, ...]

    def __post_init__(self):
        try:
            if (type(self.inventory) is not WorkerImageInventory or
                    type(self.aliases) is not tuple or len(self.aliases) > MAX_ALIASES or
                    any(type(a) is not WorkerLibraryAlias for a in self.aliases)):
                raise ValueError
            WorkerImageInventory(self.inventory.members)
            for alias in self.aliases:
                WorkerLibraryAlias(alias.name, alias.target)
            names = [a.name.casefold() for a in self.aliases]
            if len(set(names)) != len(names):
                raise ValueError
            members = {m.target: m for m in self.inventory.members}
            mapping = {a.name: a.target for a in self.aliases}
            required = {n for m in members.values() for n in m.dependencies.needed}
            if set(mapping) != required:
                raise ValueError
            loader = tuple(LOADER.lstrip("/").split("/"))
            for alias in self.aliases:
                provider = members.get(alias.target)
                if (provider is None or provider.role not in ("library", "interpreter") or
                        provider.dependencies.object_kind != "shared_object" or
                        alias.name == loader[-1] and alias.target != loader):
                    raise ValueError
            needs_loader = any(m.dependencies.interpreter is not None for m in members.values())
            interpreters = [m for m in members.values() if m.role == "interpreter"]
            if needs_loader:
                if (len(interpreters) != 1 or interpreters[0].target != loader or
                        interpreters[0].dependencies.interpreter is not None):
                    raise ValueError
            elif interpreters:
                raise ValueError
            roots = {m.target for m in members.values() if m.role in ("entrypoint", "plugin")}
            edges = {m.target: {mapping[n] for n in m.dependencies.needed} for m in members.values()}
            if needs_loader:
                for m in members.values():
                    if m.dependencies.interpreter is not None:
                        edges[m.target].add(loader)
            seen, pending = set(), list(roots)
            while pending:
                p = pending.pop()
                if p not in seen:
                    seen.add(p)
                    pending.extend(edges[p] - seen)
            if seen != set(members):
                raise ValueError
            object.__setattr__(self, "aliases", tuple(sorted(self.aliases, key=lambda a: a.name)))
        except ValueError:
            raise WorkerDependencyError("worker dependency assignment is unavailable") from None

    @property
    def edges(self):
        """Canonical (requester, needed label, declared target) tuples only."""
        mapping = {a.name: a.target for a in self.aliases}
        return tuple(sorted((m.target, name, mapping[name])
                            for m in self.inventory.members for name in m.dependencies.needed))

    @property
    def fingerprint(self):
        wire = json.dumps(dict(policy=POLICY, inventory=self.inventory.fingerprint,
                               aliases=[(a.name, a.target) for a in self.aliases]),
                          sort_keys=True, separators=(",", ":")).encode("ascii")
        return sha256(wire).hexdigest()
