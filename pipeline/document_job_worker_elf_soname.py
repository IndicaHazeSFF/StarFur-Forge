"""Pure supplied-byte DT_SONAME review, never alias or loading authority.

The bounded label is what the bytes declare, not trusted package identity,
dependency resolution, filesystem acquisition, CPU evidence or image readiness.
Search tags may be described internally but are never approved by this review.
Existing strict C1/C2 entry points still deny every RPATH/RUNPATH.
"""
from dataclasses import dataclass
import re

from pipeline.document_job_worker_elf import WorkerElfError, _parse_metadata, _soname_valid

POLICY = "worker-elf-soname-review-v1"


@dataclass(frozen=True, slots=True, repr=False)
class WorkerElfSonameReview:
    raw_sha256: str
    soname: str | None

    def __post_init__(self):
        if (type(self.raw_sha256) is not str or
                re.fullmatch(r"[0-9a-f]{64}", self.raw_sha256) is None or
                self.soname is not None and not _soname_valid(self.soname)):
            raise WorkerElfError("worker ELF SONAME review is unavailable")


def review_worker_elf_soname(raw: bytes) -> WorkerElfSonameReview:
    """Observe at most one bounded label; absence is None, not inferred identity.

    No path/name normalization, basename guessing, alias assignment, file read,
    loader call or production acceptance. Unknown dynamic tags stay unassessed.
    """
    try:
        metadata, _, soname = _parse_metadata(raw, review_search=True, review_soname=True)
        return WorkerElfSonameReview(metadata.raw_sha256, soname)
    except WorkerElfError:
        raise WorkerElfError("worker ELF SONAME review is unavailable") from None
