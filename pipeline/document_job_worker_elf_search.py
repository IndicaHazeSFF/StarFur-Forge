"""Inert supplied-byte search-metadata review, never loader eligibility.

Exact $ORIGIN is a syntactic classification only. It proves no filesystem,
resolution, immutable image, CPU behavior, deployment or execution authority.
Existing C1/C2 entry points still reject every RPATH/RUNPATH.
"""
from dataclasses import dataclass
import re

from pipeline.document_job_worker_elf import WorkerElfError, _inspect_metadata

POLICY = "worker-elf-search-review-v1"


@dataclass(frozen=True, slots=True, repr=False)
class WorkerElfSearchReview:
    raw_sha256: str
    category: str
    tags: tuple[str, ...]

    def __post_init__(self):
        if (type(self.raw_sha256) is not str or
                re.fullmatch(r"[0-9a-f]{64}", self.raw_sha256) is None or
                type(self.category) is not str or self.category not in
                ("no_search_tag", "exact_origin", "mixed_or_unsupported") or
                type(self.tags) is not tuple or self.tags not in
                ((), ("rpath",), ("runpath",), ("rpath", "runpath")) or
                (self.category == "no_search_tag") != (not self.tags) or
                self.category == "exact_origin" and len(self.tags) != 1):
            raise WorkerElfError("worker ELF search review is unavailable")


def review_worker_elf_search(raw: bytes) -> WorkerElfSearchReview:
    """Classify bounded metadata; malformed input raises a content-free error.

    Paths are not normalized, retained or returned. Empty components, build
    paths, alternative tokens and conflicting tag kinds never become $ORIGIN.
    Unknown non-search ELF metadata remains unassessed, not certified safe.
    """
    try:
        metadata, search = _inspect_metadata(raw, review_search=True)
        return _make_review(metadata, search)
    except WorkerElfError:
        raise WorkerElfError("worker ELF search review is unavailable") from None


def _make_review(metadata, search):
    """Trusted parser composition only; never an acceptance producer."""
    tags = tuple(name for tag, name in ((15, "rpath"), (29, "runpath")) if tag in search)
    category = ("no_search_tag" if not search else "exact_origin"
                if len(search) == 1 and next(iter(search.values())) == "$ORIGIN"
                else "mixed_or_unsupported")
    return WorkerElfSearchReview(metadata.raw_sha256, category, tags)
