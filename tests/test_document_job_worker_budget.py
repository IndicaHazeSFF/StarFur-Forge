from dataclasses import replace
from threading import Barrier, Thread, Event
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_budget import WorkerDispatchBudget, WorkerBudgetError
from pipeline.document_job_worker_protocol import WorkerRequest, WorkerResult, decode_request


class WorkerBudgetTests(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket', 'builtins.open', 'subprocess.Popen'):
            p = patch(name, side_effect=AssertionError('no I/O')); p.start(); self.addCleanup(p.stop)
        self.now = 100
        self.budget = WorkerDispatchBudget(_clock=lambda: self.now)
        self.binding = object()
        self.request = WorkerRequest('a'*32, 'b'*32, 'test:v1', 'fixed', 'synthetic PRIVATE', 4096, 256)
        self.result = WorkerResult('a'*32, 'b'*32, 'test:v1', 'completed', '{}', 'stop', '')

    def prepared(self, requests=None):
        return self.budget.prepare(self.binding, requests or (self.request,), expires_at=200)

    def active(self):
        return self.budget.confirm(self.prepared(), self.binding)

    def test_exact_challenge_instance_binding_and_one_confirmation(self):
        challenge = self.prepared()
        with self.assertRaises(WorkerBudgetError): self.budget.confirm(object(), self.binding)
        admission = self.budget.confirm(challenge, self.binding)
        with self.assertRaises(WorkerBudgetError): self.budget.confirm(challenge, self.binding)
        with self.assertRaises(WorkerBudgetError): self.budget.burn_for_send(challenge, self.binding)
        with self.assertRaises(WorkerBudgetError): WorkerDispatchBudget().burn_for_send(admission, self.binding)
        self.assertNotIn('PRIVATE', repr(admission))

    def test_burn_once_success_and_no_second_completion(self):
        a = self.active()
        self.assertEqual(decode_request(self.budget.burn_for_send(a, self.binding)), self.request)
        with self.assertRaises(WorkerBudgetError): self.budget.burn_for_send(a, self.binding)
        self.assertIs(self.budget.receive(a, self.binding, self.result), self.result)
        with self.assertRaises(WorkerBudgetError): self.budget.receive(a, self.binding, self.result)
        with self.assertRaises(WorkerBudgetError): self.budget.burn_for_send(a, self.binding)

    def test_cancel_before_after_and_late_response(self):
        a = self.active(); self.budget.cancel(a, self.binding)
        with self.assertRaises(WorkerBudgetError): self.budget.burn_for_send(a, self.binding)
        b = WorkerDispatchBudget(_clock=lambda:100)
        a = b.confirm(b.prepare(self.binding, (self.request,), expires_at=200), self.binding)
        b.burn_for_send(a,self.binding); b.cancel(a,self.binding)
        with self.assertRaises(WorkerBudgetError): b.receive(a,self.binding,self.result)

    def test_expiry_clock_regression_and_drift_fence(self):
        a = self.active(); self.now = 200
        with self.assertRaises(WorkerBudgetError): self.budget.burn_for_send(a,self.binding)
        self.now = 100
        with self.assertRaises(WorkerBudgetError): self.budget.burn_for_send(a,self.binding)
        b = WorkerDispatchBudget(_clock=lambda:100)
        a = b.confirm(b.prepare(self.binding,(self.request,),expires_at=200),self.binding)
        with self.assertRaises(WorkerBudgetError): b.burn_for_send(a,object())
        with self.assertRaises(WorkerBudgetError): b.burn_for_send(a,self.binding)

    def test_mismatch_or_truncation_fences_no_repair(self):
        for changes in ({'epoch':'c'*32}, {'dispatch':'c'*32}, {'finish_reason':'length'}):
            b = WorkerDispatchBudget(_clock=lambda:100)
            a = b.confirm(b.prepare(self.binding,(self.request,),expires_at=200),self.binding)
            b.burn_for_send(a,self.binding)
            with self.assertRaises(ValueError): b.receive(a,self.binding,replace(self.result,**changes))
            with self.assertRaises(WorkerBudgetError): b.burn_for_send(a,self.binding)

    def test_capture_bytes_order_and_duplicate_ids(self):
        second = replace(self.request,dispatch='c'*32)
        a = self.budget.confirm(self.prepared((self.request,second)),self.binding)
        self.budget.burn_for_send(a,self.binding); self.budget.receive(a,self.binding,self.result)
        self.assertEqual(decode_request(self.budget.burn_for_send(a,self.binding)),second)
        with self.assertRaises(WorkerBudgetError): self.prepared()

    def test_invalid_plans_and_abandonment(self):
        for requests in ((), [self.request], (self.request,self.request), (self.request,replace(self.request,model='other:v1',dispatch='c'*32))):
            with self.assertRaises(WorkerBudgetError): self.budget.prepare(self.binding,requests,expires_at=200)
        c=self.prepared(); self.budget.abandon(c,self.binding)
        with self.assertRaises(WorkerBudgetError): self.budget.confirm(c,self.binding)
        for value in (True,float('nan'),100,86501):
            with self.assertRaises(WorkerBudgetError): WorkerDispatchBudget(_clock=lambda:100).prepare(self.binding,(self.request,),expires_at=value)

    def test_concurrent_burn_only_one_gets_bytes(self):
        a=self.active(); barrier=Barrier(3); results=[]
        def run():
            barrier.wait()
            try: results.append(self.budget.burn_for_send(a,self.binding))
            except WorkerBudgetError: results.append(None)
        threads=[Thread(target=run) for _ in range(2)]
        for t in threads:t.start()
        barrier.wait()
        for t in threads:t.join(3); self.assertFalse(t.is_alive())
        self.assertEqual(sum(isinstance(r,bytes) for r in results),1)

    def test_close_invalidates_every_handle_and_refuses_reopen(self):
        a=self.active(); wire=self.budget.burn_for_send(a,self.binding)
        self.budget.close(); self.budget.close()
        self.assertEqual(decode_request(wire),self.request)  # not recalled/erased
        for operation in (lambda:self.budget.burn_for_send(a,self.binding),
                          lambda:self.budget.receive(a,self.binding,self.result),
                          lambda:self.prepared()):
            with self.assertRaises(WorkerBudgetError):operation()

    def test_cancel_linearizes_on_each_side_of_burn(self):
        for cancel_first in (True,False):
            b=WorkerDispatchBudget(_clock=lambda:100)
            a=b.confirm(b.prepare(self.binding,(self.request,),expires_at=200),self.binding)
            first=Event(); outcomes=[]
            def cancel():
                if not cancel_first:self.assertTrue(first.wait(3))
                b.cancel(a,self.binding)
                if cancel_first:first.set()
            def burn():
                if cancel_first:self.assertTrue(first.wait(3))
                try:outcomes.append(b.burn_for_send(a,self.binding))
                except WorkerBudgetError:outcomes.append(None)
                if not cancel_first:first.set()
            threads=[Thread(target=cancel),Thread(target=burn)]
            for t in threads:t.start()
            for t in threads:t.join(4);self.assertFalse(t.is_alive())
            self.assertEqual(isinstance(outcomes[0],bytes),not cancel_first)
            with self.assertRaises(WorkerBudgetError):b.receive(a,self.binding,self.result)

    def test_bad_clock_is_content_free_and_permanently_fences(self):
        a=self.active()
        self.budget._clock=lambda:(_ for _ in ()).throw(RuntimeError('PRIVATE'))
        with self.assertRaises(WorkerBudgetError) as caught:self.budget.burn_for_send(a,self.binding)
        self.assertNotIn('PRIVATE',str(caught.exception))
        self.budget._clock=lambda:100
        with self.assertRaises(WorkerBudgetError):self.budget.burn_for_send(a,self.binding)

    def test_burn_releases_payload_without_restoring_dispatch_id(self):
        a = self.active()
        wire = self.budget.burn_for_send(a, self.binding)
        self.assertEqual(self.budget._bytes, 0)
        self.assertTrue(all(not any(p['raw']) for p in self.budget._plans.values()))
        self.assertEqual(decode_request(wire), self.request)
        self.budget.receive(a, self.binding, self.result)
        with self.assertRaises(WorkerBudgetError):
            self.prepared()

    def test_expiry_sweeps_other_plan_bytes_without_replay(self):
        c = self.prepared()
        self.now = 200
        second = replace(self.request, dispatch='c'*32)
        self.budget.prepare(self.binding, (second,), expires_at=250)
        self.assertEqual(self.budget._plans[c]['raw'], [])
        self.assertEqual(self.budget._plans[c]['state'], 'fenced')
        with self.assertRaises(WorkerBudgetError):
            self.budget.prepare(self.binding, (self.request,), expires_at=250)

    def test_cancel_and_invalid_response_discard_unsent_bytes(self):
        for cancel in (True, False):
            b = WorkerDispatchBudget(_clock=lambda: 100)
            requests = self.request, replace(self.request, dispatch='c'*32)
            a = b.confirm(b.prepare(self.binding, requests, expires_at=200), self.binding)
            b.burn_for_send(a, self.binding)
            self.assertGreater(b._bytes, 0)
            if cancel:
                b.cancel(a, self.binding)
            else:
                with self.assertRaises(WorkerBudgetError):
                    b.receive(a, self.binding, replace(self.result, finish_reason='length'))
            self.assertEqual(b._bytes, 0)
            self.assertTrue(all(not p['raw'] for p in b._plans.values()))
