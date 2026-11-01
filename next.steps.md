# Rotating development handoff

Updated: 2026-10-31. Read this with AGENTS.md, session.files.md, authoritative ROADMAP.md, CHANGELOG.md and the referenced sprint record before acting. Inspect actual file/process/test state after interruption; do not assume an unfinished operation succeeded.

## Current slice

COMPLETED M1 / WSL-VERIFIED: strict inert manifest codec with seven synthetic
test methods. Focused 7-test suite and 177-test annotation-job subsystem passed
(one expected platform skip in subsystem), ResourceWarning treated as error.
Counter is 10/10; exact scoped commit/push is now due. No trusted evidence or live
processing enabled. Next: targeted review of measured evidence/consent choices.

COMPLETED HIGH-EFFORT M1 DESIGN: the private verification plan now specifies a
pure bounded manifest-byte decoder that may proceed independently of later
trusted-evidence review. No implementation or attestation was added. Next slice:
implement only M1 in pipeline/document_job_manifest.py and its synthetic tests;
do not connect filesystem, service, model invocation, consent or processing.
Medium is suitable for this now-explicit pure contract; return to High for the
authority-bearing verifier/admission work and escalate unresolved ambiguity.

COMPLETED SOL RECOVERY AUDIT / EXACT COPY VERIFIED: reviewed the timing fixes, metadata compatibility,
helper and records; 24 relevant Windows/WSL hashes matched and independent focused
audit passed 53 tests (one expected skip). No code changed or new blocking defect
identified in that scope. Counter stays 8/10: audit reruns do not inflate cadence.
Plan clarification: listed manifest digest is release-decoder-consumed identity,
not automatically whole-file or GGUF identity. Targeted measured-evidence review
remains pending. See 2026-10-31.sol-recovery-review.sprint.md.

COMPLETED CONTEXT RECOVERY / EXACT COPY VERIFIED: starfur.context.md now maps product intent, actual ownership/persistence/flows, implementation limits and documentation drift. Documentation review and nine-file exact Windows/WSL synchronization passed; final closure records use the pending queue until its verified clear. No new tests/smokes required. See 2026-10-31.context-recovery.sprint.md and docs/starfur.context.review.diff. Existing development rules are unchanged; the brief is not authority to replace them. Roger's quota-efficiency experiment directories are unrelated and excluded.

COMPLETED DEVELOPMENT / OPERATOR ACCEPTANCE PENDING: user.smokes.md plus one-command disposable CLI workflow runner. Required helper workflow and full regression passed. Roger's manual review remains pending. Next dependency: targeted Astra review of docs/private_annotation_verification.plan.md before choosing measured evidence identities/freshness/execution and consent contracts. Plan draft completed; context reconstruction does not clear this security-review gate. No verifier or public processing is enabled.

Active implementation track: disconnected private annotation jobs. Next is M1
only, a descriptor parser over supplied bytes, not another declaration wrapper
or an evidence producer. Real deployment/artifact/execution verification and
exact-job consent remain pending before processing. Scope and tests are fixed
in docs/private_annotation_verification.plan.md; no broad stage reorder.

## Completed since the current recovered checkpoint

- Exact model request, bounded metadata acquisition and pure declared-model equality foundations exist; October 31 records describe them. They do not attest local artifacts/execution or grant consent.
- Final source/result retention checks and post-parse completion acceptance check corrected; three new regressions passed.
- Astra reviewed those corrections and reconfirmed eleven Windows/WSL file hashes; no further blocking defect identified within that focused scope.
- Both maintained roadmaps mark completed foundations/corrections/decisions; broader deployment/consent/private-processing milestone remains incomplete. v5 remains proposed, not authoritative.
- Roger selected StarFur-Forge WSL as the intended private-annotation server location.
- Autonomous slice, safe-fix, targeted model escalation and ten-required-test-run backup rules recorded in AGENTS.md.

## Next actions and boundaries

1. Recheck session.files.md and current source/WSL state before changes. Windows is editing source; /home/roger/StarFur-Forge in distribution StarFur-Forge, user roger, is the exact test copy.
   Read starfur.context.md for the recovered product/architecture map. Roger normally leaves WSL running while messaging; do not start/stop it routinely. Windows has no local origin/main reference; this is missing tracking evidence, not a reason to modify its separate Git index. WSL HEAD/local origin/main were read again at the same recorded commit during context recovery; no remote contacted.
2. Implement M1 only from the completed Sol High contract. Required focused codec
   and annotation-job subsystem suites are two new gates (8/10 -> 10/10 if both
   pass), followed by scoped verified commit/push under existing rules. Keep
   source-byte hash distinct from server-declared/release-decoder identity.
   Before any trusted evidence producer or private disclosure, complete targeted
   review of executable trust, artifact/runner identity, freshness and exact-
   attempt consent. Earlier elevated read-only WSL inspection is not authority
   for service reconfiguration or implicit model probes.
3. A non-loopback server listener alone does not violate the client-destination/no-relay contract. Do not change it automatically or escalate models solely for that observation. Actual client target, relay behavior and evidence freshness remain relevant.
4. Agree the trusted evidence producer and exact-job consent design before runtime wiring/private-source disclosure. Stop for missing operator decisions, uncertain security effects, broader authority or corruption; ask for Astra only for unresolved reasoning/security/design ambiguity. Sol 6.1 High is the default.
5. Maintain completion/status, next dependency, tests, hashes and backup evidence in the same slice. Preserve runtime data and unrelated dirty files.

## Required tests and smoke gates

Counter: **10/10 successful required test runs** since the recovered checkpoint; scoped backup due. Older undocumented carry is unknown. Documentation-only slices add no runs.

| Count | Required run already completed in WSL | Result |
|---|---|---|
| 1 | Focused store/result/loopback regressions | 39 tests, OK, one expected platform skip |
| 2 | Annotation-job discovery | 166 tests, OK, one expected platform skip |
| 3 | Full provider-free discovery | 1,349 tests, OK, one expected platform skip |
| 4 | Listing/request/acquisition/binding compatibility contracts | 32 tests, OK |
| 5 | Annotation-job discovery after compatibility correction | 170 tests, OK, one expected platform skip |
| 6 | Full provider-free discovery after compatibility correction | 1,353 tests, OK, one expected platform skip |
| 7 | Required development smoke of new disposable CLI helper | WORKFLOW PASS, five expectations met; one gate total |
| 8 | Full provider-free discovery after helper addition | 1,353 tests, OK, one expected platform skip |
| 9 | Required M1 codec suite | 7 tests, OK |
| 10 | Required annotation-job subsystem after M1 | 177 tests, OK, one expected platform skip |

All used `-W error::ResourceWarning`. Full-suite repeat captured stderr after initial output truncation: zero resource-warning/unraisable-exception/traceback signals; duplicate run adds no count. Exact commands and source/test hashes: 2026-10-31.annotation-audit-followup.sprint.md.

Standalone mandatory smoke gates for the next deployment/consent slice: **not yet specified**. Define only those required by its agreed behavior; never run optional smokes or split assertions to reach ten. Unit methods within a suite do not count separately. A mandatory live model smoke requires the applicable disposable-state/authority boundaries; this handoff grants none.

## Backup and accumulated edited files

No new commit/push has occurred. WSL HEAD and locally recorded origin/main at audit time: eade99aa73aeac847fc679b135acf7cb83dd31ac; no fresh remote verification. Windows Git is an older separate baseline. Synchronization and passing tests do not establish GitHub backup.

Accumulated exact files edited/created by this chat's slices (review this allowlist at commit; do not stage the whole dirty tree):

- AGENTS.md
- starfur.context.md
- docs/starfur.context.review.diff
- 2026-10-31.context-recovery.sprint.md
- ROADMAP.md
- ROADMAP.v5.md
- CHANGELOG.md
- session.files.md
- next.steps.md
- user.smokes.md
- docs/private_annotation_verification.plan.md
- tests/manual_annotation_workflow_smoke.py
- 2026-10-31.annotation-audit-followup.sprint.md
- pipeline/document_job_model.py
- tests/test_document_job_model.py
- pipeline/document_job_store.py
- pipeline/document_job_loopback.py
- tests/test_document_job_store.py
- tests/test_document_job_result_store.py
- tests/test_document_job_loopback.py
- pipeline/document_job_model_request.py
- pipeline/document_job_model_acquisition.py
- pipeline/document_job_model_binding.py
- tests/test_document_job_model_request.py
- tests/test_document_job_model_acquisition.py
- tests/test_document_job_model_binding.py
- 2026-10-29.annotation-model-listing.sprint.md
- 2026-10-31.sol-recovery-review.sprint.md
- 2026-10-31.manifest-decoder-design.sprint.md
- pipeline/document_job_manifest.py
- tests/test_document_job_manifest.py
- 2026-10-31.manifest-codec.sprint.md

The request/acquisition/binding source/test files were authored earlier in this
same development chat and independently hash-verified on recovery; they and the
October 29 sprint are now explicitly included as accumulated unbacked work, not
because they appear untracked. The later parser correction has its own evidence.
Resolve any additional missing dependency through exact recorded scope, never a
whole-tree stage. Temporary quota trials, runtime and unrelated edits stay excluded.

## Rotation after backup

After a successful scoped commit AND verified GitHub push, replace completed-slice notes/test lists here with a compact last-verified-commit checkpoint and reset the successful-run counter for the next cycle. Carry unfinished work, pending copies, failures, blockers and unbacked files forward. Failed/uncertain commit or push never resets this file or the counter. Never erase CHANGELOG, sprint evidence, roadmap statuses or Git state as part of rotation.

Edit the rotated file in Windows and queue/synchronize it normally. That rotation is the first handoff update for the next commit cycle; do not create an endless extra commit merely to record the previous commit hash. Include it in the next ordinary scoped commit.
