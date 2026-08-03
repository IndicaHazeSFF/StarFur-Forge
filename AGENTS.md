# StarFur Forge Development Guidance

## Working-directory and execution rules

- Run Python commands from the repository root: C:/Users/roger/Documents/Codex/StarFur Forge (or the equivalent project root in WSL).
- `ROADMAP.md` is the v3 authoritative platform roadmap; `ROADMAP.v2.md` and `ROADMAP.original.md` are preserved historical versions.
- Prefer package execution such as python -m pipeline.ingest and python -m unittest discover -s tests -v. Do not execute package modules as loose files when their imports assume the project root.
- Keep the current local-first integrations intact: Ollama provides annotation/embeddings and Chroma is an external semantic index. Unit tests must not require either service.
- Treat data/starfur.db, data/sync_manifest.json, data/perf.jsonl, and Chroma as runtime state. Inspect and back up before any repair; do not reset, reinitialize, or delete them as a shortcut.

## Architecture and module responsibilities

## Memory domains

- Shared domain identifiers live in pipeline/domains.py. Valid namespaces are personal and project:<slug>; the default remains project:crown-of-claws for existing lore behavior.
- Structured entities, appearances, entity_facts, and proposals carry a domain column. db.connect() additively migrates missing columns and assigns legacy rows to project:crown-of-claws. Domain-aware queries default to that lore domain.
- Chroma metadata carries the same domain and retrieval accepts a domain filter. Existing canon ingestion remains in the existing collection and default domain. Assistant storage/retrieval policy is not implemented yet.
- Assistant personal memory uses the separate assistant_memories table and db CRUD primitives; do not reuse fictional entity_facts for personal records. Memory types, retention, and status values are validated constants, and forget is a soft status transition preserving provenance/history.
- Valid assistant proposals may be persisted as pending only by the CLI session. Approval creates one assistant memory transactionally and links both sides with assistant_memory_proposals.approved_memory_id and assistant_memories.source_proposal_id; reviewed proposals are never deleted.
- Assistant pending proposals use deterministic normalized proposal keys and atomic reinforcement. Equivalent pending evidence increments evidence_count, records unique provenance in assistant_memory_proposal_evidence, and raises confidence by a bounded 0.05 increment without approval.
- Proposal review notifications are emitted only when the current turn creates a new proposal; stale session proposals must not be announced after list/approve/reject or unrelated turns.

- `proposal approve all` is a confirmation-gated, active-domain-only batch operation. It previews pending proposals and warnings, then requires the exact follow-up `approve all`; any other input cancels without model or cross-domain access. Each proposal retains the normal approval/provenance path and failures are reported individually.


- pipeline/prechunker.py converts canon/manuscript/manuscript.txt into chapter Markdown under canon/chapters/.
- pipeline/chunker.py extracts frontmatter, splits scenes, accumulates paragraph/sentence units, preserves the nearest heading, and emits chunk dictionaries. It is shared by structured analysis and semantic ingestion.
- pipeline/sync.py is the incremental structured-analysis orchestrator. Its authoritative input is canon/chapters/**/*.md, not raw canon/manuscript Markdown. It plans changed sources using hashes and pipeline versions, calls proposal_pipeline, exports canon, then invokes semantic ingestion.
- pipeline/proposal_pipeline.py is the source-derived SQLite writer around chunking and annotation. pipeline/annotator.py only calls Ollama and normalizes the expected JSON fields.
- pipeline/db.py owns SQLite access and source-derived cleanup. pipeline/canon_writer.py creates entity files and may replace only StarFur-managed fact regions.
- pipeline/ingest.py chunks all Markdown below canon/ for Chroma ingestion; this semantic scope is broader than sync's structured-analysis scope. pipeline/rag.py and pipeline/query.py provide semantic retrieval.
- starfur.py is a CLI adapter over the pipeline. `python starfur.py serve` now exposes a narrow local OpenAI-compatible `/v1` adapter around one AssistantSession for external UIs; it exposes health/models/chat only and must not expose SQLite, Chroma, or raw internal commands. Keep the adapter dependency-free and preserve the eventual shared service/application boundary.
- pipeline/assistant.py is the narrow Stage 2 conversational loop: it loads persona/config files, reads active structured assistant memories explicitly, keeps only a bounded in-memory session window, and never writes memories automatically.
- pipeline/providers.py owns the narrow runtime `ChatProvider` protocol plus the Ollama and legacy-callable adapters. `AssistantSession` must invoke chat through this boundary; legacy `chat=` injection remains supported only through `CallableChatProvider` for tests and existing integrations.
- pipeline/context.py owns deterministic, read-only `ContextPlan` assembly for normal chat and provenance-safe introspection. It receives already selected data and emits exact model messages plus section/token accounting; it must not retrieve, call providers, or mutate session/database/Chroma state. `pipeline/assistant.py` remains responsible for retrieval, turn state, diagnostics, streaming, and proposal flow.
- Assistant prompt assembly must keep the engine-owned config/assistant_policy.md grounding policy separate from replaceable persona text. Policy governs direct answers and factual use of retrieved context; persona governs tone/presentation and must not replace grounding.
- `pipeline/context.py` injects both a selected assistant memory's summary and non-empty details as factual context. Do not reduce prompt context to summaries alone: details can hold the actual correction or answer. When selected memory directly answers a question, engine policy requires the fact first; persona style may follow but must not reinterpret or substitute generic advice.
- The grounding policy should answer factual questions first but permit brief persona warmth/style afterward; it must not make the assistant sterile or suppress appropriate presentation.
- Stage 3 assistant controls support explicit remember/forget and memory list/search commands. Conservative proposals are validated and held for review in session memory; automatic persistence remains disabled.
- pipeline/retrieval_debug.py provides opt-in off/summary/verbose/trace tracing for assistant commands, structured memory lookup, context assembly, model requests, and responses. Use starfur.py assistant --debug verbose (or trace) when diagnosing retrieval/grounding. Full prompt/content output is sensitive and disabled by default.
- Proposal generation must emit debug events for proposal_request, proposal_response, proposal_validation, and proposal_error. Proposal failures remain non-fatal and automatic proposals remain non-persistent until review workflow exists.
- Proposal extraction treats only the user message as factual evidence; assistant responses are non-authoritative context. Prompts enumerate canonical memory types/retentions, while domain and source are engine-owned. Invalid proposals receive at most one constrained repair attempt.

## Canonical source, provenance, and data invariants

- Raw manuscript text is input material; Prechunker-generated chapter files are the authoritative structured-analysis corpus. Preserve existing paths and Markdown/frontmatter formats.
- Database source identifiers are project-relative POSIX paths produced by pipeline.paths.canonical_source. Do not hand-build alternate source strings or silently mix raw and generated source paths.
- Source and chunk indexes are derived provenance, not stable identities: re-chunking can change indexes. Preserve source, scene, chunk, and evidence fields when changing pipeline code.
- Canon Markdown is human-authoritative outside StarFur-managed regions. Never overwrite human-authored summaries, notes, aliases, or other unmanaged content.
- Source cleanup may remove appearances for the source, extracted entity_facts for the source, and pending proposals for the source. It must not remove confirmed entities, aliases, confirmed facts, approved/rejected proposal history, or canon files.
- Proposal names are compared using conservative case/whitespace/punctuation normalization. Exact normalized matches to pending proposals, confirmed entities, or aliases are suppressed; ambiguous containment matches remain separate and are surfaced for human review. Original proposed names and evidence are preserved.
- Existing cleanup runs before annotation. If annotation fails, derived records for that source can remain cleared until retry; this is a known non-transactional behavior that must be called out before a repair run.

## Versioning and invalidation

- Bump CHUNKER_VERSION in pipeline/sync.py whenever chunk boundaries, heading handling, overlap, or chunk semantics change. This forces structured re-analysis through the sync manifest.
- Bump SEMANTIC_INDEX_VERSION in pipeline/ingest.py whenever chunk content, chunk metadata, or index behavior changes. Chroma skips only when both file hash and semantic index version match; missing/stale versions force source re-embedding.
- A chunker change can require both version bumps. Do not assume a content hash alone invalidates Chroma.
- Chroma ingestion deletes a source's old chunks before upserting its replacement chunks. Treat reindexing as a destructive runtime operation and do not run it implicitly in tests or audits.

## Annotation failure handling
- Annotation JSON must be an object whose five extraction sections are lists of objects; wrong nested types are retryable parse failures rather than values to coerce or silently drop.
- Annotation requests set ANNOTATION_MAX_OUTPUT_TOKENS through Ollama's num_predict option. Raise the ceiling only with explicit reasoning and regression coverage; runaway outputs are a reliability failure, not a quality signal.
- Fact classification is conservative: physical_attribute is intrinsic body/appearance only; behavioral_tendency needs recurring evidence; temporary_scene_state covers transient actions and conditions. Attach facts only when subject/ownership is explicit; omit ambiguous ownership.

- annotator.py retries only malformed, empty, or non-object model output. The current bound is three total attempts; extraction prompts, schema fields, temperature, and interpretation semantics are unchanged.
- Transport/Ollama errors are not converted into parse retries and continue to propagate.
- After parse retries are exhausted, AnnotationParseError identifies the failed chunk. proposal_pipeline.py records the chunk failure, continues later chunks in the same document, and raises DocumentAnalysisError after the document so sync keeps the source dirty for retry.
- Do not treat a partially processed document as successful or manually mark its manifest entry clean.

## Fact classification

- entity_facts.fact_type classifies each extracted fact as durable_fact, behavioral_tendency, physical_attribute, procedural_system_rule, or temporary_scene_state.
- Missing or unknown classifications normalize to durable_fact so facts are preserved conservatively; temporary scene-state facts are stored, not discarded.
- Existing entity_facts tables gain only the missing fact_type column with a durable_fact default; migration is non-destructive and does not rewrite provenance.

## Database and migration cautions

- Do not call pipeline/init_db.py against the working database during surgery. Its schema is not a complete migration system and may not represent every live table used by the current pipeline (including entity facts).
- Prefer isolated temporary SQLite databases and fake collections for tests. Preserve the current database schema and generated data until a repair plan is explicitly authorized.
- Do not add relationship/event extraction merely because tables exist; current annotation persistence is focused on known entities, appearances, facts, and proposals.

## Testing and focused Python surgery

Assistant proposal persistence receives the original user observation when available. Its normalized domain/subject/type/observation identity survives model summary paraphrases; repeated identical evidence is a no-op, while legacy callers without observations retain summary-based identity.

- Add a regression test before changing chunk or source-discovery behavior. Keep tests deterministic and service-free; use temporary databases and fake Chroma collections.
- After code changes, run: python -m unittest discover -s tests -v.
- For chunker work, verify both a small synthetic Markdown fixture and at least one real canon/chapters file. Check that prose is not dropped, heading-only chunks are absent, and chunk sizes/overlap remain intentional.
- For sync work, test discovery and manifest planning without calling sync itself. Do not run full analysis, ingestion, or proposal review as a side effect of tests.
- reanalyze-chapter force-analyzes exactly one Markdown file under canon/chapters/, updates only that file's manifest hash after success, and never runs Chroma ingestion. Invalid paths are rejected before analysis; failures leave the target manifest entry dirty for normal retry.
- Keep changes narrow: preserve existing SQLite/Markdown/Chroma formats, avoid broad refactors, and report any destructive or non-transactional behavior before executing it.

- `proposal inspect <id>` is read-only and domain-scoped; it displays proposal identity, lifecycle, and oldest-first evidence. Legacy proposals show unavailable identity/provenance placeholders.

- Approved assistant proposal evidence is linked to the resulting memory via nullable evidence.memory_id; `memory inspect <id>` is read-only and legacy memories may have no provenance.

- Assistant retrieval uses deterministic ranking over active canonical assistant memories only; `assistant-context` exposes selected records and reasons before chat injection. Proposals are not prompt context by default.

- `assistant-context --explain` exposes selected and excluded deterministic retrieval candidates; keep scoring explainable before adding embeddings.

- Retrieval benchmarks use checked-in stable fixture keys and a temporary SQLite database; never use production memory IDs or production DB for evaluation.

- Retrieval strategy implementations live behind `MemoryRetriever`; semantic/hybrid retrievers require explicitly injected temporary collections and are not wired into assistant chat or production Chroma.

- `FixtureChromaAdapter` owns a temporary PersistentClient and only ingests checked-in retrieval fixtures; it must never receive production paths or collections.

- Conversational memory introspection exposes only active canonical memory plus approved evidence in a structured prompt payload; no rejected proposals, raw DB, or hidden reasoning. Session tracks only prior selected memory IDs for follow-up why/provenance questions.

- Interactive assistant chat uses optional Ollama streaming; chunks are rendered immediately but accumulated before session history/proposal extraction. Stream failures do not commit partial assistant state.

- Ollama typed streaming chunks must read only `chunk.message.content`; never stringify chunks or expose `message.thinking` in terminal output.

- Hidden `factory-reset` is destructive and confirmation-gated; it backs up SQLite, requires an explicit scope, and never touches lore tables. Semantic reset requires an injected/configured Chroma client before any SQLite deletion.

- Hidden `factory-restore` lists timestamped backup directories, requires exact `StarFur Factory Restore` confirmation, and creates a pre-restore safety backup before replacing SQLite.

### Status memory separation

`starfur.py status` reports Crown-of-Claws lore tables separately from assistant memory tables. Factory reset and assistant testing must be verified using the assistant-memory counts; lore entities, facts, and proposals are intentionally independent.

Factory reset treats a missing Chroma collection as an already-empty semantic store and records an empty snapshot when backups are requested.

Assistant chat uses compact public record references (`M-###` and `P-###`) while SQLite numeric IDs remain internal provenance identifiers. Numeric references remain accepted for backward compatibility.

### Persona layer

Assistant persona presentation is loaded through `pipeline.persona.Persona` and `render_prompt()`. Persona configuration controls style only; retrieval, provenance, policy, safety, commands, and proposals remain in assistant/engine code. Missing or invalid persona files use the neutral fallback.

Assistant automatic proposal extraction is user-observation-only by default. Assistant responses, general knowledge answers, questions, and requests are not canonical evidence. Any future assistant-self memory must use a separate explicit provenance type and opt-in path.

Interactive assistant Ctrl+C during generation raises internal `GenerationInterrupted` control flow; the turn is rolled back, partial output is not saved, and no proposal is generated. Ctrl+C at input exits cleanly.

Assistant proposal classification uses the existing eight stored memory types only (`preference`, `personal_fact`, `experience`, `project_context`, `relationship_context`, `ongoing_situation`, `goal`, `routine`). Corrections use the corrected fact's underlying type; ambiguous observations must return `store=false`. No migration is required and legacy rows remain valid.

Assistant Ollama generation options are configuration-owned in `config/assistant.json` under `ollama_options`. The narrow validated surface is `temperature`, `top_k`, `top_p`, and `seed`; omitted options preserve provider defaults. The same options apply to normal chat, proposal extraction, and proposal repair. A future-facing statement becomes a proposal only when the user explicitly states their own intent, plan, or goal; playful/hypothetical assistant-capability framing is not canonical evidence.

Interactive `context stats` renders only the latest bounded `AssistantSession` turn snapshot. It must remain read-only: never call a model, rerun retrieval, access SQLite/Chroma, generate proposals, or retain raw prompt/conversation content. Token figures are provider-independent estimates; selected memory IDs, existing retrieval scores/reasons, response latency, first streamed-token timing, and proposal outcomes are captured during the original turn. Phase timings are also captured in the bounded latest-turn snapshot: prompt build, deterministic retrieval, association expansion, proposal processing, provider generation, and total turn time. These are read-only diagnostics and must never trigger another model call or data-store access.
Interactive Assistant Mode keeps `config/assistant.json` `chat_model` as the startup default and stores later `model use <name>` selections only in `AssistantSession.active_model`. `model list` calls the Ollama Python client model-list API; `model current` and `model use` never invoke chat, create proposals, change history, or touch SQLite/Chroma. All chat, proposal, and proposal-repair calls use the active session model. Per-turn context diagnostics capture the model used at the turn start, so later switching does not rewrite historical stats.
Chat providers own provider-specific completion and model-list calls. Assistant orchestration owns session state, streaming accumulation, interruption rollback, prompting, proposals, and diagnostics. Do not add provider-specific conditionals back into `AssistantSession`; introduce a provider adapter instead.
Assistant memory associations are additive, domain-scoped, undirected SQLite edges between two distinct assistant memories. SQLite memory rows remain authoritative; association rows carry type, bounded strength, source provenance, soft status, and timestamps. Deterministic retrieval may add one-hop active association context only from directly matched active memories, using the fixed `ASSOCIATION_RETRIEVAL_WEIGHT` multiplier and an explainable ranking reason. Retrieval never creates, updates, or deactivates associations, and inactive/cross-domain associations must not influence context.
Deterministic assistant retrieval strips common question scaffolding from both query and memory token matching and ignores one leading/trailing one-word vocative (for example, Murr in What GPU do I have, Murr?). It does not use synonym expansion or semantic fallback in production chat. Diagnostics must label overlap as meaningful keyword overlap; a query with no meaningful terms returns no deterministic matches.
When a deterministic query has a direct multi-term match, weaker direct one-term matches are excluded before association expansion. This prevents generic partial overlap from filling context, while preserving single-term recall when no stronger lexical match exists.

