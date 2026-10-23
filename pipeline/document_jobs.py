"""Inert annotation-job metadata and fixed-retention recovery policy.

No storage, worker, provider, approval, deletion, or scheduling is implemented.
An interrupted/expired status is not proof that remote work has stopped.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta


ANNOTATION_JOB_SCHEMA_VERSION = 1
ANNOTATION_JOB_RETENTION = timedelta(hours=24)
ANNOTATION_JOB_STATES = frozenset({
    "queued", "running", "completed", "failed", "interrupted", "expired",
})


class AnnotationJobPolicyError(ValueError):
    """A content-free job metadata/policy violation."""


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AnnotationJobPolicyError("job timestamps must be timezone-aware")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError):
        raise AnnotationJobPolicyError("job timestamp is out of range") from None


@dataclass(frozen=True)
class AnnotationJobMetadata:
    """Content-free lifecycle data; not identity, authority, or stored results.

    The deadline is derived, never caller-selected or renewed. Future storage
    must separately validate durable identity, ownership, source/results, and
    atomic recovery. A completed label alone never validates persisted output.
    """

    submitted_at: datetime
    state: str = "queued"
    schema_version: int = ANNOTATION_JOB_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != ANNOTATION_JOB_SCHEMA_VERSION:
            raise AnnotationJobPolicyError("unsupported annotation job schema")
        if not isinstance(self.state, str) or self.state not in ANNOTATION_JOB_STATES:
            raise AnnotationJobPolicyError("unsupported annotation job state")
        submitted = _utc(self.submitted_at)
        try:
            submitted + ANNOTATION_JOB_RETENTION
        except OverflowError:
            raise AnnotationJobPolicyError("annotation job deadline is out of range") from None
        object.__setattr__(self, "submitted_at", submitted)

    @property
    def expires_at(self) -> datetime:
        return self.submitted_at + ANNOTATION_JOB_RETENTION


def _checked_time(job: AnnotationJobMetadata, now: datetime) -> datetime:
    if type(job) is not AnnotationJobMetadata:
        raise AnnotationJobPolicyError("validated annotation job metadata is required")
    current = _utc(now)
    if current < job.submitted_at:
        raise AnnotationJobPolicyError("job clock precedes submission")
    return current


def annotation_job_accessible(job: AnnotationJobMetadata, *, now: datetime) -> bool:
    """Retention eligibility only, never authorization to read private content."""
    current = _checked_time(job, now)
    return job.state != "expired" and current < job.expires_at


def recover_annotation_job(job: AnnotationJobMetadata, *, now: datetime) -> AnnotationJobMetadata:
    """Fence unfinished work; never auto-requeue it after process restart.

    Expiry denies content even if cleanup has not run. This pure function does
    not erase bytes, validate saved results, cancel a provider, or resume work.
    """
    current = _checked_time(job, now)
    if job.state == "expired" or current >= job.expires_at:
        return replace(job, state="expired")
    if job.state in {"queued", "running"}:
        return replace(job, state="interrupted")
    return job


def resume_annotation_job(job: AnnotationJobMetadata, *, now: datetime) -> AnnotationJobMetadata:
    """Return queued intent after a future trusted controller's explicit resume.

    This is not a user command, grant, admission lease, or automatic retry.
    Failed work needs a separate reviewed retry policy; completion is immutable.
    """
    current = _checked_time(job, now)
    if not annotation_job_accessible(job, now=current):
        raise AnnotationJobPolicyError("annotation job has expired")
    if job.state != "interrupted":
        raise AnnotationJobPolicyError("only interrupted annotation jobs may resume")
    return replace(job, state="queued")
