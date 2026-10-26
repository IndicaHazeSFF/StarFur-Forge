# Pending copy manifest

## Scope

Only changed/new files from the current queued jobs may be copied from the
Windows repository to the existing WSL StarFur checkout. This is an exact
allowlist, not permission to mirror directories or copy the whole dirty tree.
See AGENTS.md for standing test/sync authority and exclusions.

## Pending files

None.

The application chunk seam, processor/store changes, fixtures, tests and
AGENTS.md were copied and verified in WSL on 2026-10-25. All twenty unique
fake-provider integration gates passed. The final provider-free WSL suite ran
1,245 tests successfully (one Windows-only skip) with ResourceWarning promoted
to an error. Final evidence documents are synchronized; the cleared manifest
itself must also be synchronized. Paused after twenty successful gates;
public controls, ownership/access policy, background
service integration and review rehydration remain deferred.

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
