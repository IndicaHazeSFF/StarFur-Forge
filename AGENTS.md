# StarFur Forge Development Guidance

## Working-directory and execution rules

- Run Python commands from the repository root: C:/Users/roger/Documents/Codex/StarFur Forge (or the equivalent project root in WSL).
- Prefer package execution such as python -m pipeline.ingest and python -m unittest discover -s tests -v. Do not execute package modules as loose files when their imports assume the project root.
- Keep the current local-first integrations intact: Ollama provides annotation/embeddings and Chroma is an external semantic index. Unit tests must not require either service.
- Treat data/starfur.db, data/sync_manifest.json, data/perf.jsonl, and Chroma as runtime state. Inspect and back up before any repair; do not reset, reinitialize, or delete them as a shortcut.

## Architecture and module responsibilities

- pipeline/prechunker.py converts canon/manuscript/manuscript.txt into chapter Markdown under canon/chapters/.
- pipeline/chunker.py extracts frontmatter, splits scenes, accumulates paragraph/sentence units, preserves the nearest heading, and emits chunk dictionaries. It is shared by structured analysis and semantic ingestion.
- pipeline/sync.py is the incremental structured-analysis orchestrator. Its authoritative input is canon/chapters/**/*.md, not raw canon/manuscript Markdown. It plans changed sources using hashes and pipeline versions, calls proposal_pipeline, exports canon, then invokes semantic ingestion.
- pipeline/proposal_pipeline.py is the source-derived SQLite writer around chunking and annotation. pipeline/annotator.py only calls Ollama and normalizes the expected JSON fields.
- pipeline/db.py owns SQLite access and source-derived cleanup. pipeline/canon_writer.py creates entity files and may replace only StarFur-managed fact regions.
- pipeline/ingest.py chunks all Markdown below canon/ for Chroma ingestion; this semantic scope is broader than sync's structured-analysis scope. pipeline/rag.py and pipeline/query.py provide semantic retrieval.
- starfur.py is a CLI adapter over the pipeline. There is no shared service/application layer or TUI/web adapter yet; do not invent one during focused pipeline surgery.

## Canonical source, provenance, and data invariants

- Raw manuscript text is input material; Prechunker-generated chapter files are the authoritative structured-analysis corpus. Preserve existing paths and Markdown/frontmatter formats.
- Database source identifiers are project-relative POSIX paths produced by pipeline.paths.canonical_source. Do not hand-build alternate source strings or silently mix raw and generated source paths.
- Source and chunk indexes are derived provenance, not stable identities: re-chunking can change indexes. Preserve source, scene, chunk, and evidence fields when changing pipeline code.
- Canon Markdown is human-authoritative outside StarFur-managed regions. Never overwrite human-authored summaries, notes, aliases, or other unmanaged content.
- Source cleanup may remove appearances for the source, extracted entity_facts for the source, and pending proposals for the source. It must not remove confirmed entities, aliases, confirmed facts, approved/rejected proposal history, or canon files.
- Existing cleanup runs before annotation. If annotation fails, derived records for that source can remain cleared until retry; this is a known non-transactional behavior that must be called out before a repair run.

## Versioning and invalidation

- Bump CHUNKER_VERSION in pipeline/sync.py whenever chunk boundaries, heading handling, overlap, or chunk semantics change. This forces structured re-analysis through the sync manifest.
- Bump SEMANTIC_INDEX_VERSION in pipeline/ingest.py whenever chunk content, chunk metadata, or index behavior changes. Chroma skips only when both file hash and semantic index version match; missing/stale versions force source re-embedding.
- A chunker change can require both version bumps. Do not assume a content hash alone invalidates Chroma.
- Chroma ingestion deletes a source's old chunks before upserting its replacement chunks. Treat reindexing as a destructive runtime operation and do not run it implicitly in tests or audits.

## Database and migration cautions

- Do not call pipeline/init_db.py against the working database during surgery. Its schema is not a complete migration system and may not represent every live table used by the current pipeline (including entity facts).
- Prefer isolated temporary SQLite databases and fake collections for tests. Preserve the current database schema and generated data until a repair plan is explicitly authorized.
- Do not add relationship/event extraction merely because tables exist; current annotation persistence is focused on known entities, appearances, facts, and proposals.

## Testing and focused Python surgery

- Add a regression test before changing chunk or source-discovery behavior. Keep tests deterministic and service-free; use temporary databases and fake Chroma collections.
- After code changes, run: python -m unittest discover -s tests -v.
- For chunker work, verify both a small synthetic Markdown fixture and at least one real canon/chapters file. Check that prose is not dropped, heading-only chunks are absent, and chunk sizes/overlap remain intentional.
- For sync work, test discovery and manifest planning without calling sync itself. Do not run full analysis, ingestion, or proposal review as a side effect of tests.
- Keep changes narrow: preserve existing SQLite/Markdown/Chroma formats, avoid broad refactors, and report any destructive or non-transactional behavior before executing it.
