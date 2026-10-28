"""Pure bounded private-result presentation; no review or writable authority.

The caller must separately authorize disclosure. Candidate prose may contain
source excerpts. Raw observation/source fields, provider metadata and runtime
fingerprints are never added to this projection. Output is not sanitized truth.
"""

import json

from pipeline.document_job_results import (
    MAX_RESULT_CANDIDATES, decode_annotation_job_result, encode_annotation_job_result,
)


DEFAULT_INSPECTION_LIMIT = 5
MAX_INSPECTION_LIMIT = 10
MAX_INSPECTION_PAGE_BYTES = 128 * 1024


class AnnotationJobInspectionError(ValueError):
    """Closed invalid/oversized result-view failure."""


def validate_inspection_range(offset, limit):
    if (type(offset) is not int or not 0 <= offset <= MAX_RESULT_CANDIDATES
            or type(limit) is not int or not 1 <= limit <= MAX_INSPECTION_LIMIT):
        raise AnnotationJobInspectionError("annotation result page range is invalid")


def build_annotation_result_page(document, result, *, offset=0, limit=DEFAULT_INSPECTION_LIMIT):
    """Revalidate exact source-bound results, then detach one explicit page.

    Job-display refs are not memory/proposal/review IDs and cannot approve or
    hand off candidates. No provider, persistence, indexing or state writer.
    """
    validate_inspection_range(offset, limit)
    try:
        checked = decode_annotation_job_result(document, encode_annotation_job_result(document, result))
        total = len(checked.candidates)
        if offset > total:
            raise ValueError
        selected = checked.candidates[offset:offset + limit]
        candidates = []
        for ordinal, candidate in enumerate(selected, start=offset + 1):
            proposal = candidate.proposal
            candidates.append({
                "display_ref": f"JC-{ordinal:04d}",
                "subject": proposal["subject"], "memory_type": proposal["memory_type"],
                "summary": proposal["summary"], "details": proposal["details"],
                "importance": proposal["importance"],
                "model_declared_confidence": proposal["confidence"],
                "retention": proposal["retention"],
            })
        next_offset = offset + len(candidates)
        page = {"schema_version": 1, "trust": "untrusted_noncanonical", "quality_verified": False,
                "candidate_count": total, "failed_chunk_count": len(checked.failures),
                "offset": offset, "limit": limit, "returned_count": len(candidates),
                "next_offset": next_offset if next_offset < total else None,
                "candidates": candidates}
        if len(json.dumps(page, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_INSPECTION_PAGE_BYTES:
            raise ValueError
        return page
    except (ValueError, TypeError, AttributeError, UnicodeError, RecursionError):
        raise AnnotationJobInspectionError("annotation result page is invalid or exceeds capacity") from None
