# Pending copy manifest

## Scope

Only changed/new files from the current queued jobs may be copied from the
Windows repository to the existing WSL StarFur checkout. This is an exact
allowlist, not permission to mirror directories or copy the whole dirty tree.
See AGENTS.md for standing test/sync authority and exclusions.

## Pending files

(none)

The passive story-binding status slice was copied by exact path and SHA-256
verified in WSL on 2026-10-21. Its focused provider-free regression and
disposable AssistantSession smoke passed: a matching generic roleplay label
remained visibly unbound, while `adventure begin` made the private story
binding active. This final cleared manifest itself must be copied and verified
before a later slice adds a new queue entry.

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

On copy failure, post-copy hash mismatch, unexpected file changes, path/permission
problems or possible runtime-data impact: pause, retain the remaining queue and
wait for the user; no automatic retry/force/workaround. Ordinary code/test
failures may be repaired within the current job. Corruption, security-boundary
failures, unexpected external effects or broader-authority fixes still pause.
The workflow-rule edits remain queued above; no WSL sync or test was performed.
