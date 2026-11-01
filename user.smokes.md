# Temporary operator smoke handoff

Maintain until Roger explicitly says to stop. This is the short checklist for the next operator session; keep outcomes and remaining checks current. Development test success does not mark Roger's manual acceptance complete.

## Start here — one command in the StarFur-Forge WSL terminal

```bash
cd /home/roger/StarFur-Forge && .venv/bin/python -W error::ResourceWarning -m tests.manual_annotation_workflow_smoke
```

Expected: five PASS lines and a final **WORKFLOW PASS**, exit 0. Read the labels and confirm they match what you intended. No root account, service restart, model, credentials or production store is needed. The helper accepts no arguments/store paths and creates an owner-only disposable store for synthetic input; it cleans up only its own temporary directory. It refuses native Windows. On FAIL or interruption, stop and report the phase label; do not paste private logs or retry against a real store.

| Workflow check | Expected | Roger's result |
|---|---|---|
| Confirmed synthetic document submission | queued, content-free progress | PENDING |
| New CLI process opens the job | queued intent fenced as interrupted | PENDING |
| Explicit resume, then another status request | resume changes intent only; no worker; original expiry unchanged | PENDING |
| Inspect without confirmation / inspect unfinished job | both refuse; no candidate page or record change | PENDING |
| Wrong deletion confirmation / exact deletion / list | wrong refuses; exact removes fixture job; empty list | PENDING |

These exercise the real `starfur.py annotation-jobs` CLI in separate processes. A passing workflow is not quality, secure-erasure, verified cloud disablement or model-execution evidence. The helper does not process a job or call a model.

## Broader boundary check — optional for Roger's comprehensive review

If you want the deterministic lifecycle/inspection integration coverage too, use this one additional command in the same WSL directory:

```bash
.venv/bin/python -W error::ResourceWarning -m unittest tests.test_document_job_control tests.test_document_job_submission tests.test_document_job_inspection tests.test_document_job_processor tests.test_document_job_runtime tests.test_document_job_provenance -v
```

Expected: OK. Fixtures own their temporary state. This checks consent/refusal, paging, exact source binding, persistence/restart, interruption, runtime drift and checkpoint evidence using fakes. It is optional operator review, not a required development gate, and does not add to the commit counter merely by being listed here. Roger's result: PENDING.

## Not ready for a manual end-to-end claim

- Live private processing: NOT ENABLED. Server/artifact/execution verification and exact-job consent are unfinished. Do not use a real private document or start a service/model merely to make this checklist pass.
- Completed-result terminal presentation: covered by the synthetic inspection suite above; a real approved-result walkthrough remains PENDING until processing exists.
- OpenWebUI/API/document-review and apartment visual checks: OUTSIDE this annotation-job slice; add a separate bounded disposable workflow when those surfaces change. Do not substitute the annotation helper for visual or model-quality acceptance.

## Developer verification versus operator acceptance

New helper development check: PASSED on 2026-10-31 (all five workflow labels, final WORKFLOW PASS). Full provider-free regression after adding helper: PASSED, 1,353 tests with one expected skip and zero stderr warning/traceback signals. The helper checkpoint was 8/10; current development counter/backup state is in next.steps.md (M1 now reaches 10/10). Operator results below remain independent of that counter. No operator result has been claimed. Keep this file across ordinary slices; rotation of next.steps.md must not erase pending operator checks. When Roger runs a check, record pass/fail, relevant code/commit checkpoint and a concise content-free observation. Stop maintaining only on explicit revocation; do not delete automatically.
