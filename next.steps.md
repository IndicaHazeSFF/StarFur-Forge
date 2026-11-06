# Rotating development handoff

Updated 2026-11-06: W1-W4 COMPLETED / WSL-VERIFIED; scoped backup due.

## Last verified backup

1044bce32a2bac4d8293c046403e38eedf4758d2, WSL main/GitHub verified.
Prior M2d/e/f code backed up. Counter starts 2/10 carried after backup.
No new commit/push; next.steps/session rotation belongs to this cycle.

## Current slice

Roger approved targeted Astra isolation/control design. WSL reference: private
network worker + dedicated Ollama/descendants, supervisor-owned private IPC;
ordinary clients unchanged. Core consumes exact dispatch authority before first
private IPC byte. No setup/services/launch/probe/private processing authorized.
Platform-neutral interface; Windows later needs tested isolation/IPC/ACL backend.
W1 wire codec is pure data/equality, NOT authentication/admission/replay prevention.
Design STOP resolved; actual enforcement/deployment/consent still incomplete.

Required WSL tests PASS: tests.test_document_job_worker_protocol (10), then
annotation-job subsystem (234, one expected skip), ResourceWarning as error.
Counter now 4/10. No manual/live smoke needed. Operator prior workflow
PASS unchanged; preserve user.smokes.md and optional pending checks.

## Next dependency / model handoff

W2 descriptive reducer/fixtures PASS: 6 focused and 240 annotation-job tests
(one expected skip), ResourceWarning as error. Counter now 6/10.
High resumed: W3 PASS, 8 focused/248 subsystem/1,431 full, expected skip once
in subsystem/full. Counter 9/10. Next bounded prerequisite: controller shutdown
fencing and deterministic cancellation/disclosure race coverage.
Real store/deployment/consent producers and preflight/transport remain disconnected.
No real transport, consent issuance, launcher or
security verification may be inferred from codec success. Authority-bearing
integration/native enforcement still needs High and separately scoped setup.

## Synchronization and backup

Completion records copied/hash-verified; final queue closure synchronized against
the recorded completion hashes. Baselines/receipts in session.files.md
and 2026-11-01.annotation-worker-design.sprint.md. Counter11 after W4 gates;
carry one after successful scoped commit/push. W4: 11 focused/251 subsystem,
one expected skip. Full pre-hardening regression: 1,431/one skip. No live smokes.
All current accumulated unbacked paths:

- AGENTS.md
- CHANGELOG.md
- ROADMAP.md
- starfur.context.md
- next.steps.md
- session.files.md
- 2026-11-01.annotation-worker-design.sprint.md
- docs/private_annotation_verification.plan.md
- pipeline/document_job_worker_protocol.py
- tests/test_document_job_worker_protocol.py
- pipeline/document_job_worker_lifecycle.py
- tests/test_document_job_worker_lifecycle.py
- pipeline/document_job_worker_budget.py
- tests/test_document_job_worker_budget.py

No other files authorized for copy/commit. No runtime/config/private data touched.
Stop on exact copy/path/hash/independent-change failures; never force or mirror.
