"""Trusted-Core request equality binding, disconnected from disclosure.

The caller owns the system prompt and effective settings. These helpers verify
the exact wire request against a current store plan; they do not select settings,
accept deployment evidence, authorize disclosure, reserve work or send bytes.
"""
from dataclasses import dataclass
from hashlib import sha256

from pipeline.document_job_store import AnnotationJobStore, AnnotationJobStoreError, AnnotationJobWorkPlan
from pipeline.document_job_worker_protocol import WorkerProtocolError, WorkerRequest, encode_request


class WorkerChunkBindingError(ValueError):
    """Closed, content-free mismatch or stale store observation."""


def _deny():
    raise WorkerChunkBindingError("private worker chunk binding is unavailable") from None


@dataclass(frozen=True, slots=True, repr=False)
class WorkerChunkBinding:
    """Internal equality record, not an admission or serialized capability."""
    _store: AnnotationJobStore
    _plan: AnnotationJobWorkPlan
    _request_digest: str


def _measure(store, plan, request, *, expected_digest=None):
    if (type(store) is not AnnotationJobStore or type(plan) is not AnnotationJobWorkPlan
            or type(request) is not WorkerRequest):
        _deny()
    try:
        digest = sha256(encode_request(request)).hexdigest()
        if expected_digest is not None and digest != expected_digest:
            _deny()
        raw_chunk = request.chunk_text.encode("utf-8")
        chunk_digest = sha256(raw_chunk).hexdigest()
        chunk_size = len(raw_chunk)
        # Re-read under the store guard, including the original expiry and the
        # current checkpoint set. This is observation, not a retained guard.
        current = store.work_plan(plan.attempt)
    except (AnnotationJobStoreError, WorkerProtocolError):
        _deny()
    if current != plan or not current.pending:
        _deny()
    chunk = current.pending[0]
    if (chunk_digest, chunk_size) != (chunk.text_sha256, chunk.byte_count):
        _deny()
    return digest


def bind_worker_chunk(store: AnnotationJobStore, plan: AnnotationJobWorkPlan,
                      request: WorkerRequest) -> WorkerChunkBinding:
    """Bind exact request bytes to the first pending chunk, retaining no prose."""
    digest = _measure(store, plan, request)
    return WorkerChunkBinding(store, plan, digest)


def revalidate_worker_chunk(binding: WorkerChunkBinding, store: AnnotationJobStore,
                            request: WorkerRequest) -> None:
    """Refuse store/plan/request drift; success does not grant send authority."""
    if (type(binding) is not WorkerChunkBinding or binding._store is not store
            or type(binding._request_digest) is not str or len(binding._request_digest) != 64):
        _deny()
    _measure(store, binding._plan, request, expected_digest=binding._request_digest)
