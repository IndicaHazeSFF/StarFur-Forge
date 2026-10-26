"""Explicit bounded annotation-job steps over a trusted injected Core runtime.

No background threads, provider construction, API authority, automatic resume,
review/memory publication or verified provider-stop claim. Production assembly
must supply the application's exact gated annotation-chunk seam, not a package
or model-selected callable. In-process adapters remain trusted components.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import secrets
from threading import RLock

from pipeline.document_annotation import DocumentAnnotationDeferredError
from pipeline.document_intake import DocumentAnnotationResult
from pipeline.document_job_results import encode_annotation_job_result
from pipeline.document_job_runtime import AnnotationJobRuntimeError
from pipeline.document_job_store import AnnotationJobAttempt, AnnotationJobStore, AnnotationJobStoreError


MAX_PROCESSOR_RUNS = 32
_DEFER_REASONS = frozenset({"focus_mode", "provider_capacity_busy", "provider_unavailable", "route_unavailable"})
_OUTCOMES = {
    "checkpointed": frozenset({"chunk_saved"}),
    "ready": frozenset({"no_pending_chunks"}),
    "deferred": _DEFER_REASONS | {"step_busy", "chunks_pending"},
    "interrupted": frozenset({"controller_interrupted"}),
    "failed": frozenset({"annotation_failed", "storage_failed", "runtime_binding_changed"}),
    "completed": frozenset({"result_saved"}),
}


class AnnotationJobProcessorError(ValueError):
    """Content-free invalid processor/run request."""


@dataclass(frozen=True)
class AnnotationJobRun:
    """Opaque process-local binding, never an API/user authentication token."""
    job_id: str
    _id: str = field(repr=False)
    _attempt: AnnotationJobAttempt = field(repr=False)


@dataclass(frozen=True)
class AnnotationJobStep:
    status: str
    reason: str
    checkpointed_chunks: int = 0

    def __post_init__(self):
        if (not isinstance(self.status, str) or self.status not in _OUTCOMES
                or not isinstance(self.reason, str) or self.reason not in _OUTCOMES[self.status]
                or type(self.checkpointed_chunks) is not int
                or self.checkpointed_chunks != (1 if self.status == "checkpointed" else 0)):
            raise AnnotationJobProcessorError("annotation step outcome is invalid")


@dataclass
class _RunState:
    handle: AnnotationJobRun
    busy: bool = False
    interrupted: bool = False


class AnnotationJobProcessor:
    def __init__(self, store: AnnotationJobStore, runtime):
        if not isinstance(store, AnnotationJobStore) or not callable(getattr(runtime, "annotate_document_chunk", None)):
            raise AnnotationJobProcessorError("trusted annotation store/runtime is required")
        self._store = store
        self._runtime = runtime
        self._lock = RLock()
        self._runs: dict[str, _RunState] = {}

    def _state(self, handle: AnnotationJobRun) -> _RunState:
        if type(handle) is not AnnotationJobRun or not isinstance(handle._id, str):
            raise AnnotationJobProcessorError("annotation run is not current")
        state = self._runs.get(handle._id)
        if state is None or state.handle is not handle:
            raise AnnotationJobProcessorError("annotation run is not current")
        return state

    def start(self, job_id: str) -> AnnotationJobRun:
        """Bind one queued job only; never resume, admit or call a provider."""
        with self._lock:
            if len(self._runs) >= MAX_PROCESSOR_RUNS:
                raise AnnotationJobProcessorError("annotation processor is at capacity")
            identity = secrets.token_hex(16)
            if identity in self._runs:
                raise AnnotationJobProcessorError("annotation run identity collision")
            attempt = self._store.mark_running(job_id)
            handle = AnnotationJobRun(job_id, identity, attempt)
            self._runs[identity] = _RunState(handle)
            return handle

    def _fence(self, state: _RunState) -> bool:
        """Fence result acceptance, not provider execution or OS termination."""
        with self._lock:
            state.interrupted = True
            recorded = True
            try:
                self._store.interrupt(state.handle._attempt)
            except AnnotationJobStoreError:
                # Do not guess/retry a stale/uncertain durable operation or
                # overwrite another run. The caller receives storage_failed.
                recorded = False
            if not state.busy:
                self._runs.pop(state.handle._id, None)
            return recorded

    def interrupt(self, handle: AnnotationJobRun) -> AnnotationJobStep:
        """Explicitly stop accepting output; no claim that a provider stopped."""
        with self._lock:
            state = self._state(handle)
            if self._fence(state):
                return AnnotationJobStep("interrupted", "controller_interrupted")
            return AnnotationJobStep("failed", "storage_failed")

    def step(self, handle: AnnotationJobRun) -> AnnotationJobStep:
        """Process at most one unfinished chunk. Never loop, wait, or retry."""
        with self._lock:
            state = self._state(handle)
            if state.interrupted:
                return AnnotationJobStep("interrupted", "controller_interrupted")
            if state.busy:
                return AnnotationJobStep("deferred", "step_busy")
            state.busy = True
        try:
            selected = self._store.next_chunk(handle._attempt)
            if selected is None:
                return AnnotationJobStep("ready", "no_pending_chunks")
            document, chunk_id = selected
            # Never hold the processor lifecycle lock across a provider/runtime
            # call. Application-owned policy/capacity/session locks stay there.
            result = self._runtime.annotate_document_chunk(document, chunk_id)
            with self._lock:
                if state.interrupted:
                    return AnnotationJobStep("interrupted", "controller_interrupted")
                if type(result) is not DocumentAnnotationResult:
                    raise ValueError("invalid annotation result")
                encode_annotation_job_result(document, result)
                # Per-chunk aggregate execution metadata is not silently
                # summed into a whole-job claim. Chunk failure attempts remain.
                self._store.save_checkpoint(handle._attempt, chunk_id, replace(result, execution=None))
                return AnnotationJobStep("checkpointed", "chunk_saved", 1)
        except DocumentAnnotationDeferredError as error:
            with self._lock:
                if state.interrupted:
                    return AnnotationJobStep("interrupted", "controller_interrupted")
                if isinstance(error.reason, str) and error.reason in _DEFER_REASONS:
                    return AnnotationJobStep("deferred", error.reason)
            saved = self._fence(state)
            return AnnotationJobStep("failed", "annotation_failed" if saved else "storage_failed")
        except AnnotationJobRuntimeError:
            saved = self._fence(state)
            return AnnotationJobStep("failed", "runtime_binding_changed" if saved else "storage_failed")
        except AnnotationJobStoreError:
            self._fence(state)
            return AnnotationJobStep("failed", "storage_failed")
        except Exception:
            saved = self._fence(state)
            return AnnotationJobStep("failed", "annotation_failed" if saved else "storage_failed")
        except BaseException:
            self._fence(state)
            raise
        finally:
            with self._lock:
                state.busy = False
                if state.interrupted:
                    self._runs.pop(handle._id, None)

    def finish(self, handle: AnnotationJobRun) -> AnnotationJobStep:
        """Explicit all-checkpoint finalization; never performs missing work."""
        with self._lock:
            state = self._state(handle)
            if state.interrupted:
                return AnnotationJobStep("interrupted", "controller_interrupted")
            if state.busy:
                return AnnotationJobStep("deferred", "step_busy")
            try:
                if self._store.next_chunk(handle._attempt) is not None:
                    return AnnotationJobStep("deferred", "chunks_pending")
                self._store.finish_checkpoints(handle._attempt)
            except AnnotationJobStoreError:
                self._fence(state)
                return AnnotationJobStep("failed", "storage_failed")
            self._runs.pop(handle._id, None)
            return AnnotationJobStep("completed", "result_saved")
