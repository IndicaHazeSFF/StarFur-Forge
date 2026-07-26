# Changelog

## 2026-07-26 — Expanded pipeline surgery guidance

- Purpose: document durable pipeline contracts, provenance rules, invalidation behavior, migration cautions, and service-free testing practices for future Python surgery sessions.
- Modified: AGENTS.md and CHANGELOG.md.
- Behavior: documentation only; no runtime pipeline or data behavior changed.
- Verification: documentation inspection only; no sync, SQLite mutation, Chroma rebuild, or full analysis was run.


## 2026-07-26 — Safe corpus-repair preparation

- Purpose: repair the canonical manuscript-analysis path and prepare safe reprocessing without running destructive repair.
- Modified: pipeline/chunker.py, pipeline/sync.py, pipeline/ingest.py, and regression tests under tests/.
- Behavior: sync now analyzes Prechunker-generated canon/chapters/**/*.md; Chonker preserves accumulated prose; Chroma re-embeds unchanged Markdown when its semantic index version is missing or stale while retaining the normal hash/version skip path.
- Cleanup invariant: tests verify that source cleanup removes only appearances, extracted facts, and pending proposals for the source, preserving entities, aliases, confirmed facts, and reviewed proposal history.
- Versions: CHUNKER_VERSION bumped to 3; semantic index version set to 2.
- Verification: python -m unittest discover -s tests -v (8 tests passed). No sync, SQLite mutation, Chroma rebuild, or full analysis was run.
