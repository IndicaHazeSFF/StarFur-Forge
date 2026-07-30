# Changelog

## 2026-07-30 - Idempotent Chroma deletion

- Factory reset now treats both ?not found? and ?does not exist? Chroma deletion responses as an already-empty collection.
- Extended reset regression coverage.


## 2026-07-30 - Idempotent Chroma reset

- Treat an already-absent semantic collection as empty during factory-reset, allowing SQLite cleanup and backup to complete safely.
- Added regression coverage.


## 2026-07-30 - Separate status reporting for assistant memory

- Added independent assistant-memory totals, active-memory totals, and pending-proposal totals to `starfur.py status`; lore counts remain unchanged.
- Added regression coverage for the separated counters.


## 2026-07-30 - Assistant startup command help

- Expanded the interactive assistant banner to advertise proposal review and memory inspection commands.


## 2026-07-30 - Assistant memory command documentation

- Documented interactive proposal listing, inspection, approval, rejection, and active-memory commands in docs/COMMANDS.md.


## 2026-07-30 - Factory CLI parser fix

- Removed duplicate hidden factory-reset subcommand registration that caused CLI startup to fail with an argparse conflict.
- Verification: full unittest suite (62 tests) passed.


## 2026-07-30 - Factory restore

- Added timestamped backup discovery and confirmation-gated SQLite restore with automatic pre-restore safety backup.


## 2026-07-30 - Confirmation-gated factory reset

- Added hidden scoped `factory-reset` with exact confirmation, SQLite backup, assistant-table cleanup, and explicit Chroma deletion injection.


## 2026-07-30 - Ollama typed stream handling

- Fixed interactive streaming to consume typed ChatResponse message content and suppress internal thinking/repr output.


## 2026-07-30 - Streaming assistant output

- Added compatible streamed Ollama response handling for interactive chat, preserving complete-response history and deterministic tests.


## 2026-07-30 - Conversational memory introspection

- Added provenance-safe explain-memory intent handling, prior selected-memory tracking, direct memory recall questions, and custom-loader compatibility tests.


## 2026-07-30 - Fixture-only semantic retrieval adapter

- Added temporary Chroma fixture lifecycle, stable-key ingestion, fixed embedding injection, and expanded retrieval benchmark coverage to 15 cases.


## 2026-07-30 - Retrieval strategy boundary

- Added MemoryRetriever protocol plus deterministic, injected semantic, and transparent hybrid implementations. Semantic/hybrid evaluation requires an explicit temporary collection and remains isolated from chat.


## 2026-07-30 - Retrieval benchmark corpus

- Added stable-key retrieval fixtures, temporary SQLite benchmark execution, malformed-fixture validation, and `retrieval-eval` metrics/reporting.


## 2026-07-30 - Retrieval quality diagnostics

- Added `assistant-context --explain`, exclusion reasons, and a small retrieval evaluation helper for top-1/top-3 and irrelevant-result metrics.


## 2026-07-30 - Deterministic assistant retrieval

- Added ranked canonical-memory retrieval, explainable context selection, and `assistant-context` CLI output. Wired relevant memories into assistant prompts.
- Modified: pipeline/db.py, pipeline/assistant.py, starfur.py, tests/test_assistant_retrieval.py, AGENTS.md, and CHANGELOG.md.


## 2026-07-29 - Approved memory evidence linkage

- Approval now links proposal evidence to the canonical assistant memory; repeated approval is idempotent. Added domain-scoped read-only `memory inspect <id>`.
- Modified: pipeline/db.py, pipeline/assistant.py, tests/test_assistant_proposals.py, AGENTS.md, CHANGELOG.md, and docs/COMMANDS.md.


## 2026-07-29 - Assistant proposal inspection

- Added read-only `proposal inspect <id>` inspection of proposal state, identity, and evidence provenance.
- Modified: pipeline/db.py, pipeline/assistant.py, tests/test_assistant_proposal_inspection.py, AGENTS.md, and CHANGELOG.md.
- Verification: full unittest suite passed; no production data or Chroma mutation.


## 2026-07-29 - Exact assistant evidence reinforcement

- Purpose: keep repeated identical user evidence on one pending proposal despite extractor paraphrases.
- Modified: pipeline/db.py, pipeline/assistant.py, tests/test_assistant_proposal_idempotency.py, and AGENTS.md.
- Behavior: observation-aware identity reinforces pending proposals, duplicate evidence is idempotent, and first summary/details are preserved.
- Verification: full unittest suite run; no production sync or database/Chroma mutation.

## 2026-07-28 — Deterministic assistant proposal idempotency

- Purpose: prevent duplicate pending assistant proposals while preserving repeated evidence and provenance.
- Modified: pipeline/db.py, pipeline/assistant.py, tests/test_assistant_proposal_idempotency.py, AGENTS.md, and CHANGELOG.md.
- Behavior: normalized domain/subject/type/summary identities reinforce pending proposals atomically; evidence_count increments, unique evidence rows preserve source references, and confidence increases by at most 0.05 per repeated observation. Reviewed proposals are not reopened or merged.
- Verification: python -m unittest discover -s tests -q (46 tests passed). No production sync, memory mutation, Chroma rebuild, or full analysis was run.


## 2026-07-28 — Fix stale assistant proposal notifications

- Purpose: prevent previously created proposals from being announced after unrelated commands or turns.
- Modified: pipeline/assistant.py, tests/test_assistant.py, AGENTS.md, and CHANGELOG.md.
- Behavior: review notices now appear only when the current turn creates a new proposal.
- Verification: python -m unittest discover -s tests -q (43 tests passed).


## 2026-07-28 — Durable assistant proposal storage foundation

- Purpose: persist validated assistant proposals for restart-safe review without changing lore proposals or auto-approving memories.
- Modified: pipeline/db.py, pipeline/init_db.py, pipeline/assistant.py, tests/test_assistant_proposals.py, AGENTS.md, and CHANGELOG.md.
- Behavior: assistant_memory_proposals supports pending/approved/rejected lifecycle; CLI-generated store=true proposals become pending. Approval transactionally creates assistant_memories and links source_proposal_id/approved_memory_id; rejection preserves audit history.
- Verification: python -m unittest discover -s tests -q (42 tests passed). No production sync, memory mutation, Chroma rebuild, or full analysis was run.


## 2026-07-28 — Grounded assistant memory proposal extraction

- Purpose: improve proposal quality without weakening validation or allowing assistant roleplay to become user memory.
- Modified: pipeline/assistant.py, tests/test_assistant.py, AGENTS.md, and CHANGELOG.md.
- Behavior: proposal prompts use user-only factual evidence, enumerate canonical enums, require numeric scores, and assign domain/source in engine code. Invalid output gets one bounded repair attempt, then remains safely rejected.
- Verification: python -m unittest discover -s tests -q (40 tests passed). No production sync, memory mutation, Chroma rebuild, or full analysis was run.


## 2026-07-28 — Proposal-path retrieval diagnostics

- Purpose: expose why conservative assistant memory proposals are accepted, rejected, empty, or unavailable without changing persistence behavior.
- Modified: pipeline/assistant.py, tests/test_assistant.py, AGENTS.md, and CHANGELOG.md.
- Behavior: verbose/trace debugging now reports proposal request, raw response status, validation result, and non-fatal validation/model errors. Automatic proposals remain session-only and are never silently persisted.
- Verification: python -m unittest discover -s tests -q (40 tests passed). No production sync, memory mutation, Chroma rebuild, or full analysis was run.


## 2026-07-28 — Balance grounded answers with persona expression

- Purpose: preserve the successful factual grounding fix without suppressing natural persona warmth.
- Modified: config/assistant_policy.md, tests/test_assistant.py, AGENTS.md, and CHANGELOG.md.
- Behavior: the engine answers accurately first, then permits brief affectionate/persona expression when appropriate; persona still cannot contradict or overwhelm factual grounding.
- Verification: python -m unittest discover -s tests -q (40 tests passed).


## 2026-07-28 — Engine-owned assistant grounding policy

- Purpose: ensure replaceable personas cannot override factual grounding or replace direct answers with unrelated roleplay.
- Modified: pipeline/assistant.py, config/assistant.json, config/assistant_policy.md, tests/test_assistant.py, AGENTS.md, and CHANGELOG.md.
- Behavior: assistant prompts now include a separate engine policy after persona text, explicitly prioritizing the user question and retrieved factual context. Persona remains presentation-only.
- Verification: python -m unittest discover -s tests -q (39 tests passed). No production sync, memory mutation, Chroma rebuild, or full analysis was run.


## 2026-07-28 — Retrieval debugging and observability

- Purpose: make assistant retrieval, context assembly, commands, and model grounding inspectable before further memory-quality changes.
- Modified: pipeline/retrieval_debug.py, pipeline/assistant.py, starfur.py, config/assistant.json, tests/test_assistant.py, AGENTS.md, and CHANGELOG.md.
- Behavior: assistant supports --debug off, summary, verbose, and trace. Verbose shows full memory/context/model payloads; trace adds elapsed timing. Debugging is opt-in and does not alter memory persistence or retrieval behavior.
- Verification: python -m unittest discover -s tests -v (38 tests passed). No production sync, memory mutation, Chroma rebuild, or full analysis was run.


## 2026-07-27 — Stage 3 explicit memory controls and proposals

- Purpose: add user-controlled assistant memory commands and conservative review-only proposals.
- Modified: pipeline/assistant.py, config/assistant.json, tests/test_assistant.py, AGENTS.md, and CHANGELOG.md.
- Behavior: remember this/forget this and memory list/search operate in the selected domain using validated CRUD; forget is soft. Completed normal turns may produce validated in-session proposals under off/conservative policy, but no automatic memory persistence or personal Chroma writing occurs.
- Verification: python -m unittest discover -s tests -v (36 tests passed). No production sync, memory mutation, Chroma rebuild, or full analysis was run.


## 2026-07-27 — Stage 2 conversational Assistant Mode

- Purpose: provide the first usable local chat loop while keeping persona, memory storage, routing, and future services separate.
- Modified: pipeline/assistant.py, starfur.py, config/assistant.json, persona/default.md, tests/test_assistant.py, AGENTS.md, and CHANGELOG.md.
- Behavior: python starfur.py assistant loads file-backed persona/configuration, reads active assistant memories from the selected domain for context, maintains a bounded recent-session window, supports quit/exit, and leaves memory unchanged. Ollama failures or empty responses do not commit session state.
- Verification: python -m unittest discover -s tests -v (33 tests passed). No production sync, memory mutation, Chroma rebuild, or full analysis was run.


## 2026-07-27 — Assistant structured memory foundation

- Purpose: add Sprint Stage 1.2 personal assistant memory storage without coupling it to fictional lore entities/facts.
- Modified: pipeline/db.py, pipeline/init_db.py, tests/test_assistant_memory.py, AGENTS.md, and CHANGELOG.md.
- Behavior: additive assistant_memories schema and domain-aware CRUD support preferences, facts, experiences, projects, relationships, situations, goals, and routines with session/short_term/long_term retention. Validation rejects unknown types/retentions/statuses; forget marks memories forgotten instead of deleting provenance.
- Verification: python -m unittest discover -s tests -v (29 tests passed). No production sync, SQLite/Chroma mutation, or rebuild was run.


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

