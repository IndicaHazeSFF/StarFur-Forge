# Changelog

## 2026-07-27 — POSIX-safe targeted reanalysis test

- Purpose: make manifest-entry verification portable across Windows and WSL/Linux path separators.
- Modified: tests/test_targeted_reanalysis.py and CHANGELOG.md.
- Behavior: the test compares normalized relative paths instead of assuming backslashes; production logic is unchanged.
- Verification: python -m unittest discover -s tests -v (26 tests passed).


## 2026-07-27 — Additive memory domains

- Purpose: establish explicit personal/project namespaces without separating the StarFur Forge engine or changing existing Crown of Claws behavior.
- Modified: pipeline/domains.py, pipeline/db.py, pipeline/init_db.py, pipeline/ingest.py, pipeline/rag.py, tests/test_memory_domains.py, AGENTS.md, and CHANGELOG.md.
- Behavior: structured memory records carry a domain, defaulting to project:crown-of-claws; legacy rows migrate additively with that domain. Chroma chunks record domain metadata and retrieval can filter by domain. No assistant conversation, persona, selection model, routing, POV, or TUI was added.
- Verification: python -m unittest discover -s tests -v (26 tests passed). No production sync, SQLite mutation, or Chroma rebuild was run.


## 2026-07-27 — Targeted chapter reanalysis command

- Purpose: provide a safe manual retry path for one authoritative chapter without reprocessing unrelated sources or rebuilding semantic memory.
- Modified: pipeline/sync.py, starfur.py, tests/test_targeted_reanalysis.py, AGENTS.md, and CHANGELOG.md.
- Behavior: reanalyze-chapter accepts only Markdown files inside canon/chapters/, reuses normal source cleanup/provenance/failure behavior, updates only the target manifest entry after success, and never invokes Chroma ingestion.
- Verification: python -m unittest discover -s tests -v. No production sync or database mutation was run.


## 2026-07-27 — Conservative proposal normalization and duplicate review

- Purpose: reduce trivial duplicate proposals without silently merging semantically ambiguous names.
- Modified: pipeline/db.py, pipeline/proposal_pipeline.py, tests/test_proposal_normalization.py, AGENTS.md, and CHANGELOG.md.
- Behavior: proposal comparisons normalize case, whitespace, and punctuation; exact matches against pending proposals, confirmed entity names, and aliases are suppressed. Likely partial matches such as Meridian/Meridian Compact are surfaced for review while preserving each original name, evidence, and provenance.
- Verification: python -m unittest discover -s tests -v. No sync, production SQLite mutation, Chroma rebuild, or full analysis was run.


## 2026-07-27 — Annotation classification guidance and output ceiling

- Purpose: reduce observed fact-type and subject-attribution errors while allowing longer valid annotation responses.
- Modified: pipeline/annotator.py, tests/test_fact_classification.py, AGENTS.md, and CHANGELOG.md.
- Behavior: annotation output ceiling is now 4096 tokens. Prompt guidance restricts physical_attribute to intrinsic characteristics, requires recurring evidence for behavioral_tendency, routes transient observations to temporary_scene_state, and forbids ambiguous subject ownership. Existing five types, schema, extraction architecture, and provenance are unchanged.
- Verification: python -m unittest discover -s tests -v. No sync, production SQLite mutation, Chroma rebuild, or full analysis was run.


## 2026-07-27 — Fact durability/type classification

- Purpose: preserve extracted facts while recording whether each is durable, behavioral, physical, procedural/system, or temporary scene-state knowledge.
- Modified: pipeline/db.py, pipeline/init_db.py, pipeline/annotator.py, pipeline/proposal_pipeline.py, tests/test_fact_classification.py, AGENTS.md, and CHANGELOG.md.
- Behavior: annotation prompts require one fact_type; persistence stores it and conservatively defaults unknown/missing values to durable_fact. Existing entity_facts tables receive a non-destructive column migration; fresh schemas include the field.
- Verification: python -m unittest discover -s tests -v (16 tests passed). No sync, production SQLite mutation, Chroma rebuild, or full analysis was run.


## 2026-07-27 — Nested annotation validation and output ceiling

- Purpose: prevent valid-but-wrongly-shaped Qwen JSON from reaching extraction code and cap runaway annotation generation.
- Modified: pipeline/annotator.py and tests/test_annotator_retry.py.
- Behavior: all five annotation sections must be lists of objects; invalid nested shapes use the existing retry/source-retry path. Ollama annotation requests now set num_predict to a 2048-token ceiling. Extraction semantics are unchanged.
- Verification: python -m unittest discover -s tests -v (13 tests passed). No sync, SQLite mutation, Chroma rebuild, or full analysis was run.


## 2026-07-26 — Hardened annotation parsing

- Purpose: tolerate transient malformed or empty model output without changing extraction semantics or unnecessarily aborting later chunks.
- Modified: pipeline/annotator.py, pipeline/proposal_pipeline.py, tests/test_annotator_retry.py, and tests/test_annotation_failure_isolation.py.
- Behavior: parse-level output failures are logged and retried up to three total attempts; persistent failure is isolated, later chunks continue, and the source remains retryable through the existing sync failure path. Transport errors still propagate.
- Verification: python -m unittest discover -s tests -v (11 tests passed). No sync, SQLite mutation, Chroma rebuild, or full analysis was run.


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
