# Pending copy manifest

## Scope

Only changed/new files from the current queued jobs may be copied from the
Windows repository to the existing WSL StarFur checkout. This is an exact
allowlist, not permission to mirror directories or copy the whole dirty tree.
See AGENTS.md for standing test/sync authority and exclusions.

## Pending files

None.

The 2026-10-28 locality policy and opt-in transport source/tests/AGENTS/commands
were copied and hash-verified. Six pure locality tests and all fifteen fake
transport/integration checks passed in WSL; all 135 annotation-job tests and
full 1,318-test provider-free discovery passed (one Windows-only skip each).
Final evidence files are synchronized and all queued copies hash-verified;
this cleared manifest is the final sync item. Stopped at real-server verification
operator gate with 50% quota remaining at the post-slice check. No actual
network/provider/service/production-state operation or commit was performed.

Prior verified checkpoint: private result-inspection source/tests/AGENTS/commands were copied and
hash-verified in WSL. Ten gates and the pure contract passed; all 114 annotation
job tests and full 1,297-test provider-free discovery passed (one Windows-only
skip each). Final evidence files are synchronized and all queued copies
hash-verified; this cleared manifest is the final sync item. Paused at ten gates; no new
commit, live provider or production state operation was requested/performed.

Prior verified evidence: the 2026-10-27 durable provenance source/tests/AGENTS/commands were copied and
hash-verified. All ten gates passed; all 103 annotation-job tests and full
1,286-test WSL discovery passed, one Windows-only skip each. Final evidence
copies are synchronized and hash-verified after quota was restored. This
cleared manifest is the final sync item. No live providers or production state;
changes remain uncommitted. Paused at ten successful unique gates.

Prior verified checkpoint: the 2026-10-26 per-attempt runtime adapter, application/processor changes,
tests, AGENTS and command documentation were copied and hash-verified in WSL.
All ten unique disposable runtime/store gates plus two pure contracts passed.
Full provider-free WSL discovery passed 1,275 tests (one Windows-only skip)
with ResourceWarning promoted to an error. All 92 annotation-job subsystem
tests passed (one skip). Final evidence files are synchronized and all queued
copies hash-verified; this cleared manifest is the final sync item.
Stopped at ten gates; the user requested a scoped furry commit after verification.
No live providers or production state were used. New edits must re-enter this
pending queue. Processing, shared-access ownership, background service and
review rehydration remain deferred. Prior durable evidence is in the sprint
records and changelog, not this pending deployment queue.

The subsequent documentation-only desktop overlay input/focus gate and its
changelog entry were also synchronized and verified. No source or runtime
behavior changed; native game/visual checks remain user-owned future gates.
The subsequent per-character sizing/presentation roadmap addition and changelog
entry were also synchronized and verified; no source behavior changed.

## Verified / no longer pending

- `pipeline/adventure_initiative.py`
- `tests/test_adventure_initiative.py`

Both source/test hashes matched Windows after the user's copy, and direct WSL
execution passed all 13 focused tests on 2026-10-20. No live provider or
production data operation was involved. Older cumulative file lists are retired;
durable history remains in CHANGELOG.md and the relevant sprint records.

## Queue lifecycle

Before a required/prudent test, copy only pending job files to the exact WSL
checkout and verify them. Remove verified entries; keep failed/unverified ones.
When all are verified, leave an empty pending list and copy/verify that final
manifest too. Later edits re-enter the queue. Test failure is not cleared by
copy success. Never clear git status, changelog, or sprint history as part of
resetting this list. No runtime data, local config, credentials, unrelated files,
directory mirroring, or repository deletion is authorized.

On copy failure, post-copy hash mismatch, unexpected independent file changes,
path/permission problems or possible runtime-data impact: pause, retain the
remaining queue and wait for the user; no automatic retry/force/workaround.
Ordinary scoped code/test failures, including synthetic lifecycle bugs, may be
fixed and retested under AGENTS.md. Material design/scope choices, missing
operator inputs, actual security failures, corruption, and unexpected external
effects still pause. "Finish this slice, then stop" includes focused verification
and authorized sync; after abrupt interruption inspect actual state before resume.
