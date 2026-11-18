"""Pure byte-exact search-form review, NOT accepted search or image policy.

Closed labels distinguish the known literal forms without returning paths or
normalizing empty/build components. Even a recognized form grants no loading,
immutable cwd/default-path proof, CPU/dlopen eligibility or execution authority.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from pipeline.document_job_worker_elf import WorkerElfError, _inspect_metadata

POLICY = "worker-search-form-review-v1"
FORMS = frozenset({"no_search", "origin_runpath", "origin_build_empty_runpath", "unsupported"})


@dataclass(frozen=True, slots=True, repr=False)
class WorkerSearchFormReview:
    raw_sha256: str
    search_fingerprint: str
    form: str

    def __post_init__(self):
        if (any(type(v) is not str or re.fullmatch(r"[0-9a-f]{64}", v) is None
                for v in (self.raw_sha256, self.search_fingerprint)) or
                type(self.form) is not str or self.form not in FORMS):
            raise WorkerElfError("worker search-form review is unavailable")


def review_worker_search_form(raw):
    """Describe supplied bytes, not observed loader behavior or policy approval.

    RPATH (even $ORIGIN), duplicate/malformed tags, alternative syntax and any
    unrecognized combination never become the known RUNPATH form. Unknown
    other dynamic tags remain unassessed. Existing strict inspectors unchanged.
    """
    try:
        metadata, search = _inspect_metadata(raw, review_search=True)
        if not search:
            form = "no_search"
        elif search == {29: "$ORIGIN"}:
            form = "origin_runpath"
        elif search == {29: "$ORIGIN:/build/llama-server-cpu/bin:"}:
            form = "origin_build_empty_runpath"
        else:
            form = "unsupported"
        wire = json.dumps(dict(policy=POLICY, tags=sorted(search.items())),
                          sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        return WorkerSearchFormReview(metadata.raw_sha256, sha256(wire).hexdigest(), form)
    except WorkerElfError:
        raise WorkerElfError("worker search-form review is unavailable") from None
