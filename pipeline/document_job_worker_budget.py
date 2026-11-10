"""Disconnected trusted-Core one-use byte budget, not deployment acceptance.

Bindings/challenges are process-local exact objects, never serialized authority.
Trusted future assembly must bind real store/attempt/source/settings/deployment,
obtain operator consent and run fresh policy/capacity/enforcement checks. This
module does none of those, calls no transport and cannot establish readiness.
Burn returns exact captured bytes once; callers must never cache/replay them.
"""
import math
from threading import Lock
import time

from pipeline.document_job_worker_protocol import encode_request, encode_result


class WorkerBudgetError(ValueError):
    pass


def _deny():
    raise WorkerBudgetError("private worker budget is unavailable") from None


class WorkerDispatchBudget:
    """Bounded controller-local registry. No public/application caller exists."""
    def __init__(self, *, _clock=time.time):
        if not callable(_clock):
            _deny()
        self._clock = _clock
        self._last = None
        self._lock = Lock()
        self._plans = {}
        self._ids = set()
        self._bytes = 0
        self._closed = False

    def _fence(self, plan):
        self._bytes -= sum(len(raw) for raw in plan['raw'] if raw is not None)
        plan.update(state='fenced', raw=[], inflight=None)

    def _now(self):
        try:
            if self._closed:
                _deny()
            value = self._clock()
            if type(value) not in (int, float) or not -1e12 < value < 1e12 or not math.isfinite(value):
                _deny()
            if self._last is not None and value < self._last:
                _deny()
            self._last = value
            for plan in self._plans.values():
                if value >= plan['expires'] and plan['state'] in {'awaiting_confirmation', 'active'}:
                    self._fence(plan)
            return value
        except BaseException as error:
            for plan in self._plans.values():
                self._fence(plan)
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            _deny()

    def prepare(self, binding, requests, *, expires_at):
        """Capture exact wire bytes; never inspect private storage or grant send."""
        if (binding is None or type(requests) is not tuple or not 1 <= len(requests) <= 16
                or type(expires_at) not in (int, float) or not -1e12 < expires_at < 1e12
                or not math.isfinite(expires_at)):
            _deny()
        raw = tuple(encode_request(request) for request in requests)
        keys = tuple((r.epoch, r.dispatch) for r in requests)
        settings = {(r.epoch, r.model, r.context_size, r.max_output_tokens) for r in requests}
        if len(set(keys)) != len(keys) or len(settings) != 1:
            _deny()
        with self._lock:
            now = self._now()
            if (not now < expires_at <= now + 86400 or len(self._plans) >= 32
                    or self._bytes + sum(map(len, raw)) > 4 * 1024 * 1024
                    or any(key in self._ids for key in keys)):
                _deny()
            challenge = object()
            self._plans[challenge] = dict(binding=binding, raw=list(raw), expires=expires_at,
                correlations=tuple((r.epoch, r.dispatch, r.model) for r in requests),
                state='awaiting_confirmation', next=0, inflight=None, admission=None)
            self._ids.update(keys)
            self._bytes += sum(map(len, raw))
            return challenge

    def _current(self, handle, binding, *, admission=False):
        # Identity-keyed objects issued by this instance; arbitrary values deny.
        plan = self._plans.get(handle) if type(handle) is object else None
        if admission:
            plan = next((p for p in self._plans.values() if p['admission'] is handle), None) if type(handle) is object else None
        if plan is None:
            _deny()
        now = self._now()
        if plan['binding'] is not binding or now >= plan['expires']:
            self._fence(plan)
            _deny()
        return plan

    def confirm(self, challenge, binding):
        """Trusted local controller hook only, NOT an operator approval surface."""
        with self._lock:
            plan = self._current(challenge, binding)
            if plan['state'] != 'awaiting_confirmation':
                _deny()
            admission = object()
            plan.update(state='active', admission=admission)
            return admission

    def burn_for_send(self, admission, binding):
        """Linearize with cancel and consume BEFORE returning private wire bytes.

        No slot restoration, reconnect, retry or dispatch of a second chunk while
        a response is pending. A thrown/lost return may mean disclosure possible.
        External preflight is separate and must run before calling this hook.
        """
        with self._lock:
            plan = self._current(admission, binding, admission=True)
            if plan['state'] != 'active' or plan['inflight'] is not None:
                _deny()
            index = plan['next']
            if index >= len(plan['raw']):
                _deny()
            plan['next'] += 1
            plan['inflight'] = plan['correlations'][index]
            raw = plan['raw'][index]
            plan['raw'][index] = None
            self._bytes -= len(raw)
            return raw

    def receive(self, admission, binding, result):
        """Correlate an envelope, never checkpoint or publish its contents."""
        with self._lock:
            plan = self._current(admission, binding, admission=True)
            if plan['state'] != 'active' or plan['inflight'] is None:
                _deny()
            try:
                encode_result(result)
                if ((result.epoch, result.dispatch, result.model) != plan['inflight']
                        or result.status != 'completed' or result.finish_reason != 'stop'):
                    _deny()
            except BaseException:
                self._fence(plan)
                raise
            plan['inflight'] = None
            if plan['next'] == len(plan['raw']):
                plan['state'] = 'completed'
            return result

    def cancel(self, handle, binding):
        """Fence acceptance only. Does not attest provider termination."""
        with self._lock:
            plan = self._current(handle, binding, admission=True)
            self._fence(plan)

    def abandon(self, challenge, binding):
        with self._lock:
            plan = self._current(challenge, binding)
            self._fence(plan)

    def close(self):
        """Invalidate all handles and drop registry references, not secure erasure.

        Already returned bytes/provider work cannot be recalled. A fresh registry
        is not permission to reconstruct old attempts or reuse previous consent.
        """
        with self._lock:
            self._closed = True
            self._plans.clear()
            self._ids.clear()
            self._bytes = 0
