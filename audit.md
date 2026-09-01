# StarFur Forge Architectural Audit

**Audit date:** 2026-08-08  
**Method:** Read-only static inspection of the current repository and its documentation. No models, tests, databases, Chroma collections, network services, or production workflows were run. Line references describe the inspected snapshot and may move as the repository changes.

## Executive summary

StarFur Forge has moved beyond its original manuscript-analysis role and now has a credible foundation for a local-first resident-assistant platform. Its strongest implemented areas are structured assistant memory, conservative proposal review, provenance, deterministic retrieval, prompt/context assembly, persona/policy separation, interactive and OpenAI-compatible presentation surfaces, and an initial external-document intake path. The architectural direction in `ROADMAP.md` is generally consistent with the code.

The repository is not yet a finished multi-client platform. The most consequential current risk is that the HTTP server owns one shared, stateful `AssistantSession`. The API accepts only the most recent user message from each request while the server-side session retains conversation history, selected memories, active model, and pending confirmation state. This works for a single experimental user, but separate OpenWebUI chats or clients can influence one another. Serialization through `AssistantApplication` prevents concurrent mutation, not cross-conversation contamination (`pipeline/application.py:22-38`, `pipeline/application.py:60-64`, `pipeline/api.py:49-64`, `pipeline/api.py:183-200`). This should be corrected before broader external testing.

The memory system is substantially more mature than the presentation and document layers. Assistant memories and durable proposals are domain-scoped and provenance-aware; forgetting is soft; proposal approval is linked bidirectionally; exact evidence is idempotent; and normal assistant retrieval is deterministic and explainable (`pipeline/db.py:182-236`, `pipeline/db.py:745-1002`, `pipeline/db.py:1150-1201`). Production assistant chat does **not** yet use semantic or hybrid retrieval. Those adapters exist for controlled evaluation, which is the conservative and correct current boundary (`pipeline/retrieval.py`, `pipeline/retrieval_eval.py:24-96`).

External-document intake is a useful initial vertical slice, not complete RAG. It validates and chunks uploaded text, asks a model for bounded structured candidates, stores a short-lived server-side review, and hands selected candidates into the normal pending-proposal workflow. Approved candidates then become ordinary structured assistant memories. It does not yet persist source documents, index them into production semantic memory, intercept OpenWebUI attachments, provide durable/batch review, or support selective source retrieval (`pipeline/document_intake.py`, `pipeline/document_annotation.py`, `pipeline/document_review.py`, `pipeline/api.py:78-180`).

The immediate architectural objective should be a reliable single-user prototype loop with explicit conversation isolation, a usable document-review boundary, and measurable retrieval/answer behavior. Provider routing, tools, vision, emotional state, autonomous interests, and the apartment should remain downstream of those controls. No broad rewrite is warranted.

## Current architecture

### 1. Presentation and entry points

- `starfur.py` is the command-line entry point for lore commands, interactive assistant mode, diagnostics/evaluation commands, factory operations, document-related surfaces, and the HTTP server.
- `pipeline/assistant.py` implements the interactive assistant loop and the stateful `AssistantSession`.
- `pipeline/api.py` exposes OpenAI-compatible model/chat endpoints plus StarFur diagnostics and document endpoints. It uses `ThreadingHTTPServer`, but requests enter a shared application/session (`pipeline/api.py:229-350`).
- `pipeline/application.py` is a deliberately thin, presentation-neutral facade. It centralizes access to one `AssistantSession`, capability metadata, document annotation, proposal handoff, and diagnostics. Its lock makes access serialized and stream-writer restoration safe (`pipeline/application.py:1-6`, `pipeline/application.py:22-64`).
- OpenWebUI works through the OpenAI-compatible API, but StarFur does not own OpenWebUI's attachment/RAG preprocessing. Raw UI-provided RAG material can therefore arrive outside StarFur's document trust boundary.

The application facade is the correct place for CLI, HTTP, future TUI, and dashboard surfaces to converge. It is currently a facade over a monolithic session rather than a complete service layer, which is acceptable for the prototype if new presentation logic continues to enter through it.

### 2. Assistant orchestration

`AssistantSession` currently owns or coordinates:

- active provider and model;
- persona, dynamic persona state, and policy;
- bounded recent conversation history;
- deterministic structured-memory retrieval;
- association enrichment;
- capability selection;
- context planning;
- streaming and interruption rollback;
- commands and deterministic command help;
- memory/proposal CRUD callbacks;
- conversational memory introspection;
- last-selected memory references;
- bulk-approval confirmation state;
- lifecycle and most-recent-turn diagnostics.

This creates a productive vertical slice, but also makes `pipeline/assistant.py` the main coupling center. The injected callbacks and provider protocol provide seams for incremental extraction. The code should be decomposed only when a concrete second consumer needs a stable primitive.

One brittle seam is the retrieval selection in `AssistantSession`: it uses an identity comparison against the built-in memory loader to decide whether to invoke deterministic ranked retrieval, while custom loaders follow a simpler compatibility path (`pipeline/assistant.py:370-426`). This preserves tests and extensibility today but bypasses the formal `MemoryRetriever` strategy boundary.

### 3. Provider and lifecycle layer

`pipeline/providers.py` defines a small `ChatProvider` protocol and Ollama/callable implementations. This keeps direct Ollama client calls out of the main assistant generation path and supports deterministic fakes (`pipeline/providers.py:17-68`).

`pipeline/provider_state.py` defines lifecycle states including disconnected, connecting, loading, ready, idle, generating, streaming, cooling, unloading, and error. The current state machine is valuable for diagnostics and future avatar behavior, but most transitions represent application-observed generation phases rather than independently probed backend/model residency.

Only chat is implemented as a generalized provider capability. Vision, images, embeddings, speech, and task routing remain roadmap work. Some legacy lore paths still call Ollama or Chroma directly, so the provider boundary is not yet repository-wide.

### 4. Persona, policy, capabilities, and context

- `pipeline/persona.py` loads persona presentation instructions and supplies a neutral fallback.
- `pipeline/persona_state.py` defines bounded dynamic traits, momentary state, persona state, and a derived behavior context. The structures exist, but the current runtime does not yet implement a persistent emotional or autonomous-interest engine.
- `config/assistant_policy.md` owns factual grounding and behavioral constraints separately from persona style (`config/assistant_policy.md:4-15`).
- `pipeline/capabilities.py` provides immutable, structured capability definitions and selective capability-manifest injection. Personas can explain currently available StarFur features without hardcoding those features into persona files.
- `pipeline/command_help.py` provides deterministic, core-owned command syntax for direct help questions, avoiding model-invented commands.
- `pipeline/context.py` contains a deterministic, read-only `ContextManager`. It assembles persona, policy, capabilities, behavior context, retrieved memory, recent conversation, introspection payloads, and the current user message, while recording section sizes and estimated tokens (`pipeline/context.py:60-170`).

This separation is sound: identity/style belongs to persona, factual and safety invariants belong to policy/core, capability truth belongs to the registry, and final prompt construction belongs to the context layer.

### 5. Structured assistant memory

`pipeline/domains.py` validates the `personal` namespace and `project:<slug>` project domains, with lore defaulting to `project:crown-of-claws` (`pipeline/domains.py:4-12`).

`pipeline/db.py` additively maintains assistant-oriented tables for:

- canonical assistant memories;
- durable assistant-memory proposals;
- proposal evidence;
- domain-scoped memory associations;
- bidirectional proposal-to-approved-memory provenance.

The schema and APIs support validated memory types, retention/status values, confidence, importance, source metadata, soft forgetting, corrections, proposal review, evidence inspection, and approval idempotency (`pipeline/db.py:182-236`, `pipeline/db.py:745-1201`). Approved proposal evidence is linked to the resulting memory, and `source_proposal_id` prevents a proposal from creating multiple memories.

The assistant schema remains separate from fictional `entity_facts`, preserving the lore contract. Existing legacy rows can remain valid without destructive rewriting.

### 6. Retrieval, associations, and introspection

Normal assistant retrieval is a deterministic structured-memory ranker. It considers meaningful token/phrase overlap, confidence, importance, status, domain, and one-hop association support. Results retain scoring reasons and are deterministically ordered (`pipeline/db.py:905-1002`). Only active canonical memories are eligible for normal answer context.

`pipeline/retrieval.py` defines `MemoryRetriever`, deterministic, semantic, and hybrid strategies. Semantic and hybrid modes accept injected collections and embedders. `pipeline/retrieval_eval.py` uses temporary fixture-only Chroma collections when semantic evaluation is explicitly requested (`pipeline/retrieval_eval.py:24-96`). These adapters are experimental evaluation infrastructure, not production assistant semantic recall.

Conversational introspection exposes controlled memory content, confidence/importance, approved evidence, proposal provenance, and retrieval reasons. It deliberately excludes rejected/superseded proposals, raw database access, unrestricted history, and hidden reasoning. `AssistantSession` tracks the memories used in the previous completed response so follow-up provenance questions can resolve their target.

Associations are currently an explainable, domain-scoped, one-hop graph. This is useful foundational behavior, but it is not yet a learned multi-hop cognitive graph or a full bridge to assistant semantic memory.

### 7. Proposal generation and provenance

Automatic proposal extraction uses the completed **user** observation as its factual source. Assistant prose is contextual at most and is not independently promoted into canonical user memory. Application code validates the model's structured output before persistence. Exact normalized observation evidence can reinforce an existing proposal or become an idempotent no-op, preserving the first stored summary rather than allowing later paraphrases to rewrite identity.

Durable proposal status is pending, approved, or rejected. Rejection and forgetting preserve history. Approval creates an active assistant memory and links proposal, memory, and evidence in one SQLite transaction (`pipeline/db.py:1150-1164`). Broad semantic duplicate detection and contradiction resolution are intentionally not implemented.

### 8. External-document intake and review

The current document path is:

```text
trusted API request
  -> size/type/domain validation
  -> deterministic content hash and source identity
  -> shared text/Markdown chunking
  -> per-chunk annotation with bounded retry
  -> engine validation and engine-owned provenance
  -> short-lived in-memory review record
  -> explicit candidate handoff confirmation
  -> normal durable pending assistant proposal
  -> ordinary human approval
  -> active structured assistant memory
  -> deterministic assistant retrieval
```

`pipeline/document_intake.py` accepts Markdown/plain text up to its configured bound, generates content-addressed source/chunk identifiers, and reuses shared chunking. `pipeline/document_annotation.py` treats the document as untrusted data, asks for JSON-only memory candidates, tolerates limited wrapper/prose failures, and uses bounded output. `pipeline/document_review.py` holds at most a bounded number of reviews for a limited time. The API only hands off the server-stored candidate, not arbitrary client-supplied proposal fields (`pipeline/api.py:78-180`).

This design conservatively protects proposal validation and provenance. Its current limitations are material for usability:

- reviews disappear on restart and expire quickly;
- handoff is candidate-by-candidate rather than a convenient reviewed batch;
- external source documents/chunks are not durable source records;
- candidate identity incorporates output ordinal, which may change if a model reorders candidates on a repeated annotation;
- the active chat provider/model also performs document extraction; there is no task-specific annotation profile yet;
- approved facts enter structured memory, but the source document is not indexed for selective semantic RAG;
- OpenWebUI uploads are not automatically routed through this path.

### 9. Lore/manuscript pipeline

The legacy writing/lore subsystem remains functional and conservatively separated:

- `pipeline/prechunker.py` prepares chapter Markdown;
- `canon/chapters/**/*.md` is the authoritative manuscript-analysis corpus (`pipeline/sync.py:103-117`);
- chunking/index version changes can invalidate unchanged-source fast paths (`pipeline/sync.py:120-159`);
- lore annotation writes derived appearances/facts/proposals with source provenance (`pipeline/proposal_pipeline.py`);
- `pipeline/ingest.py` maintains the canon Chroma collection and semantic index version;
- `pipeline/rag.py` performs domain-aware lore retrieval.

The cleanup-before-analysis design allows a failed reanalysis to leave that source's derived memory temporarily absent until a successful retry. Failures are recorded and later chunks continue, but cleanup plus repopulation is not one atomic source transaction (`pipeline/proposal_pipeline.py:79-109`, `pipeline/proposal_pipeline.py:294-301`). This is acceptable for the current manual repair workflow but should be revisited before unattended production ingestion.

Some legacy lore query/index paths still bypass the newer provider/application boundaries. `pipeline/query.py` and `pipeline/rag.py` are also not fully consistent in domain filtering. These are contained writing-mode debts, not reasons to refactor the working assistant core now.

### 10. Diagnostics and benchmarking

Most-recent-turn context diagnostics expose provider/model, generation options, persona/policy/recent-conversation sizes, retrieved public memory IDs, scores/reasons, estimated prompt/completion tokens, response size, latency/TTFT, phase timings, proposal outcome, and completion/interruption state. Only bounded diagnostic state is retained; the command is read-only.

`pipeline/benchmark.py` defines a versioned benchmark manifest with architecture fingerprint, git commit, seed, model/provider/quantization/context profile, hardware metadata, and scaling-plan structures (`pipeline/benchmark.py:8-60`). `pipeline/retrieval_eval.py` provides a controlled retrieval fixture runner with Top-1/Top-3, Recall@K, Precision@K, irrelevant-result counts, and repeatability. This is a good foundation, but there is not yet a complete experiment runner or append-only result ledger joining retrieval, answer use, annotation, contamination, provider portability, latency, and resource metrics.

## Roadmap status against implementation

### Implemented

- Additive memory domains and separation of lore from assistant memory.
- Assistant-memory CRUD, validation, retention/status, soft forgetting, correction, and provenance.
- Durable proposal lifecycle, approval linkage, evidence, exact-evidence idempotency, inspection, and bulk approval confirmation.
- Deterministic assistant retrieval with scoring diagnostics and controlled conversational introspection.
- Domain-scoped one-hop associations.
- Persona configuration/fallback, policy separation, capability manifest, deterministic command help, and context assembly.
- Interactive CLI, streaming/interruption handling, runtime model listing/switching, OpenAI-compatible HTTP chat, and bounded diagnostics.
- Chat provider protocol with Ollama and test-callable implementations.
- Initial external-document prepare/annotate/review/proposal-handoff vertical slice.
- Versioned benchmark metadata and retrieval evaluation fixtures, including fixture-only semantic/hybrid comparisons.
- Existing lore synchronization, annotation, export, and canon semantic retrieval foundation.

These items correspond chiefly to the completed foundation and Stage 1 sections of `ROADMAP.md:48-72` and `ROADMAP.md:127-133`.

### Partially implemented

- **Stage 2 runtime diagnostics/provider lifecycle:** diagnostics and a lifecycle state model exist, but backend health/model residency/resource probing remain limited (`ROADMAP.md:135-142`).
- **Shared application/service primitives:** `AssistantApplication` is a correct facade, but it still owns one session and delegates substantial orchestration to `AssistantSession`.
- **External-document/RAG flow:** structured extraction and approved-memory retrieval work; durable source storage, semantic document indexing, batch review, attachment interception, and selective source context do not.
- **Provider abstraction:** generalized chat exists; embeddings, vision, image generation, speech, routing, and task profiles do not.
- **Benchmarking:** schemas and retrieval evaluation exist; reproducible end-to-end behavioral runs and a result ledger do not.
- **Persona runtime:** capability-aware persona prompting and bounded state structures exist; autonomous interests, persona-local memory, learning, and derived emotional behavior remain future work.
- **Associative cognition:** one-hop explicit links exist; learned/temporal/emotional associations and multi-hop controls do not.
- **Writing partner:** the lore foundation exists; POV/perspective tracking and a unified modern writing-partner service remain future work.

### Not started in a product-capable form

- Automatic model/capability router and specialist task profiles.
- Permissioned tool framework and sandboxed autonomous work.
- Vision, image generation, TTS/STT, and continuous perception.
- Multi-persona runtimes with persona-local structured/semantic/associative memory.
- Persistent emotional-state inference and autonomous interest/research loops.
- Discussion sandbox and long-duration agent simulation.
- Apartment/avatar resident environment and system-monitoring presentation.
- Production-ready multi-client authentication, session management, deployment, and recovery.
- Full benchmark experiment ledger, ablations, and grant/publication-quality results.

### Roadmap/code ambiguities

- The roadmap describes provider lifecycle work as in progress while the repository already has a lifecycle state machine. The missing distinction is **observed application state versus probed provider/model state**.
- Numbering in the Stage 2 provider/runtime section is inconsistent, making completion marks less precise.
- “Semantic memory separable by domain” is true for lore metadata and fixture adapters, but production assistant semantic writing/retrieval is not implemented. The roadmap should keep that distinction explicit.
- “External document intake” can mean structured proposal extraction or source-level RAG. Only the former initial path is implemented.
- The capability registry describes currently supported features, but there is not yet a permissions/tool registry from which future operational capabilities can be generated.

## Architectural debt and coupling

### High severity

#### Shared state across HTTP conversations

**Files:** `pipeline/api.py`, `pipeline/application.py`, `pipeline/assistant.py`  
**Why it matters:** One HTTP server owns one mutable session. The API discards client-supplied history except for the latest user message, while the server session retains its own history, model selection, last referenced memory IDs, and confirmation state. Separate OpenWebUI chats or clients can cross-contaminate one another. The lock prevents races but does not provide isolation.  
**Minimal mitigation:** Add a bounded application-level session registry keyed by an explicit, validated conversation identifier. Preserve a legacy/default local session for CLI and simple clients. Do not duplicate database connections or memory stores per chat; isolate only ephemeral conversation/runtime state.

#### External UI RAG bypasses StarFur's trust and context boundary

**Files:** `pipeline/api.py`, `pipeline/context.py`, `pipeline/document_intake.py`, `pipeline/document_annotation.py`  
**Why it matters:** OpenWebUI can prepend retrieved attachment content to the user's message. StarFur cannot reliably distinguish command/help intent, user observation, and third-party document text after that transformation. This has already manifested as prompt/persona/command contamination risk.  
**Minimal mitigation:** Define an explicit source-part contract for API messages and a StarFur-owned attachment intake route. Mark external content as untrusted context, not user assertion, and prevent it from entering proposal extraction unless the document-review path is used.

#### Domain consistency is incomplete in legacy semantic paths

**Files:** `pipeline/ingest.py`, `pipeline/rag.py`, `pipeline/query.py`  
**Why it matters:** Lore RAG supports domain filters, but legacy query behavior and some source-deletion operations are source-name-oriented rather than consistently domain-and-source-oriented. Future multiple projects could collide if they reuse source paths.  
**Minimal mitigation:** Add domain-aware regression tests first, then include domain in every query/deletion predicate without rebuilding production collections until an explicit migration/reindex is authorized.

### Medium severity

#### `AssistantSession` is the orchestration nexus

**Files:** `pipeline/assistant.py`, `pipeline/application.py`  
**Why it matters:** Commands, retrieval, context, generation, proposals, streaming, lifecycle, and diagnostics change together. This increases regression risk as routing, tools, and multiple personas arrive.  
**Minimal mitigation:** Continue extracting narrow immutable/request-scoped primitives behind `AssistantApplication`; avoid a general service rewrite. Session isolation and retriever injection are the next useful seams.

#### Retriever abstraction is not the production injection point

**Files:** `pipeline/assistant.py`, `pipeline/retrieval.py`  
**Why it matters:** The formal strategy protocol exists, but normal chat selects retrieval through a built-in-loader identity check. This makes controlled deterministic/semantic/hybrid comparisons harder and custom loader behavior qualitatively different.  
**Minimal mitigation:** Inject a `MemoryRetriever` with deterministic default and a compatibility adapter for custom loaders. Snapshot existing result/message behavior before changing it.

#### Document reviews are ephemeral and candidate identity depends on ordinal

**Files:** `pipeline/document_review.py`, `pipeline/document_intake.py`, `pipeline/db.py`, `pipeline/api.py`  
**Why it matters:** Restart/expiry loses a completed, potentially slow annotation. Long documents require repetitive handoff calls. A repeated annotation that reorders candidates can change source references and weaken idempotency.  
**Minimal mitigation:** Introduce a content-derived candidate fingerprint from normalized subject/type/observation span, retain the ordinal only for display, and add a bounded reviewed-batch handoff. If reviews become durable, store only validated bounded payloads and explicit expiration/status.

#### Document extraction uses the active chat model without a task profile

**Files:** `pipeline/application.py`, `pipeline/document_annotation.py`, `pipeline/assistant.py`  
**Why it matters:** A model chosen for persona/prose may be slow or unreliable at JSON extraction. Annotation options and reproducibility differ from chat configuration.  
**Minimal mitigation:** Add an explicit annotation model/profile through the existing provider interface before building an automatic router.

#### Database module and migration path are broad

**Files:** `pipeline/db.py`  
**Why it matters:** Lore schema, assistant schema, migrations, CRUD, retrieval, associations, and proposals share one module. Schema checks run when connecting, including read-oriented call paths. This is manageable now but will complicate more memory dimensions and persona-local stores.  
**Minimal mitigation:** Do not split the database immediately. First separate schema-version/migration functions and define repository-style interfaces at call sites that need alternate stores.

#### Lore reanalysis cleanup is not source-transactional

**Files:** `pipeline/proposal_pipeline.py`, `pipeline/sync.py`  
**Why it matters:** A failed model run after stale-source cleanup can leave that chapter's derived facts absent until retry, although authoritative Markdown and confirmed entities remain intact.  
**Minimal mitigation:** Eventually stage derived records under a run/source revision and swap them only after the source completes. Preserve the current conservative retry manifest until that work is specifically authorized.

#### Benchmark metadata is not yet a result system

**Files:** `pipeline/benchmark.py`, `pipeline/retrieval_eval.py`, `tests/fixtures/retrieval_cases.json`  
**Why it matters:** The repository can describe a run and evaluate retrieval fixtures, but cannot yet reproduce and compare complete resident-assistant behavior across commits/models. Architectural claims therefore remain partly anecdotal.  
**Minimal mitigation:** Add a versioned append-only result schema and deterministic runner before routing changes create many new variables.

### Low severity or intentionally deferred

- Token counts are deliberately approximate (`pipeline/context.py`); provider-reported counts can be added when consistently available.
- Deterministic retrieval scans bounded sets of active memories and associations; index/FTS optimization can wait for measured scale problems.
- Inferred provider lifecycle states are sufficient for current diagnostics; true loading/warm/cooling state requires provider-specific observation.
- API authentication is a single optional bearer token. This is acceptable only for explicitly local experimentation; binding to non-loopback without a key should receive a stronger runtime warning or refusal before release.
- Context summarization, dynamic budgeting, semantic chat retrieval, contradiction resolution, emotion, and autonomy are correctly deferred.

## Approved document flow assessment

The implemented flow is conservative in the important places:

1. The engine validates type, size, domain, and content before annotation.
2. Source and chunk identifiers derive from content and are not accepted from the model.
3. Annotation output is treated as untrusted and validated against existing memory enums/domain rules.
4. Invalid chunks retry in isolation and do not crash the entire document unnecessarily.
5. A review token references server-held candidates; the handoff endpoint does not accept arbitrary proposal content.
6. Handoff creates an ordinary pending proposal rather than an active memory.
7. Human approval remains the only normal route to canonical active memory.
8. Approved document memories preserve source/chunk evidence and participate in deterministic retrieval.

The remaining gap is that this is a **fact-extraction workflow**, not yet a document knowledge base. A question whose answer was not selected into an approved structured memory cannot be answered from the document through StarFur-owned RAG. Adding source-level semantic retrieval before session/source isolation would repeat the OpenWebUI contamination problem inside StarFur. The safer order is: isolate conversations, formalize trusted source parts, make review usable/durable, then index selected source chunks with explicit domain/source filters.

## Prototype readiness

| Area | Readiness | Evidence-based assessment |
|---|---:|---|
| Structured personal memory | Strong prototype | Validated CRUD, provenance, proposals, soft forgetting, deterministic retrieval, public IDs, and inspection are implemented. |
| Persona/policy/context | Strong prototype | Dedicated layers exist and capability/command truth is core-owned. Dynamic state remains mostly foundational. |
| CLI assistant | Usable single-user prototype | Streaming, interruption handling, commands, model switching, memory, and diagnostics are present. |
| OpenWebUI/API | Experimental single-session prototype | Chat works, but one shared session and external RAG ambiguity prevent safe multi-chat/multi-client claims. |
| External documents | Initial vertical slice | Explicit API extraction-to-proposal works; source RAG, native upload interception, durable/batch review, and failure UX remain. |
| Assistant semantic memory | Evaluation only | Fixture Chroma adapters exist; production chat remains deterministic structured retrieval. |
| Lore/writing memory | Functional legacy subsystem | Corpus contract, annotation, provenance, sync, export, and Chroma RAG exist; modern service integration and POV remain. |
| Provider portability/routing | Foundation only | Chat protocol and model switching exist; automatic routing and non-chat providers do not. |
| Benchmarking | Foundation only | Metadata and retrieval fixtures exist; full repeatable behavioral/result framework does not. |
| Tools/vision/apartment | Roadmap | Permissioned tools, vision, avatar environment, and automation are not implemented. |

The current system is ready for controlled, single-user local testing with temporary or deliberately reviewed data. It is not ready for untrusted multi-user exposure, unattended autonomous work, or product claims about semantic personal memory, long-session isolation, or small-model equivalence.

## Five prioritized recommendations

### 1. Isolate ephemeral assistant sessions at the application/API boundary

**Objective:** Ensure each CLI session, OpenWebUI conversation, future TUI window, and dashboard client has independent conversation/runtime state while sharing the same domain-scoped canonical memory services.  
**Affected modules:** `pipeline/api.py`, `pipeline/application.py`, `pipeline/assistant.py`, API/application tests.  
**Expected benefit:** Eliminates cross-chat history, model, introspection target, interruption, and confirmation contamination; establishes the correct multi-frontend service boundary.  
**Tests/verification:** Two conversation IDs with interleaved requests; independent recent history, model choice, last-memory IDs, and bulk-approval confirmation; bounded session eviction; legacy/default session compatibility; concurrent request serialization per session; no database duplication.  
**Why now:** Every OpenWebUI and future frontend test otherwise builds on ambiguous state. This is a correctness boundary, not polish.  
**What should wait:** Multi-persona runtimes, account systems, distributed session stores, and general web authentication.

### 2. Complete the reviewed external-document prototype loop

**Objective:** Make explicit uploads usable without allowing raw UI RAG to masquerade as user memory: durable-enough review identity, content-derived candidate identity, batch handoff, and an explicit source-part/API contract.  
**Affected modules:** `pipeline/document_intake.py`, `pipeline/document_annotation.py`, `pipeline/document_review.py`, `pipeline/api.py`, `pipeline/db.py`, document/API tests and command documentation.  
**Expected benefit:** A user can upload, annotate, review, create pending proposals, approve, and later retrieve facts without repeating long model work or issuing dozens of handoff calls. Provenance and human approval remain intact.  
**Tests/verification:** Restart/expiry policy, deterministic candidate fingerprints despite reordered extraction, batch partial failure, idempotent resubmission, domain isolation, prompt-injection documents, oversized/invalid files, no direct active-memory writes, and OpenWebUI/source-part separation.  
**Why now:** Document memory/RAG is the user's immediate prototype goal and currently has the largest usability gap after session isolation.  
**What should wait:** Automatic source trust, automatic approval, unrestricted file types, and production semantic indexing of every upload.

### 3. Make retrieval a first-class injected application primitive

**Objective:** Route assistant retrieval through the existing `MemoryRetriever` boundary with deterministic retrieval as the unchanged default, then add explicitly selected structured/semantic/hybrid profiles only under evaluation or configuration.  
**Affected modules:** `pipeline/retrieval.py`, `pipeline/assistant.py`, `pipeline/application.py`, `pipeline/context.py`, retrieval/context tests.  
**Expected benefit:** Removes loader-identity coupling, keeps custom loaders testable, supports fair strategy comparisons, and prepares selective external-document source retrieval without silently changing chat behavior.  
**Tests/verification:** Snapshot-equivalent deterministic messages and selected IDs; custom loader adapter; no-match behavior; domain/source filters; deterministic repeatability; identical diagnostics shape; semantic adapter unavailable unless explicitly injected; no Chroma mutation.  
**Why now:** The strategy classes already exist, and document/source retrieval will otherwise create a second parallel retrieval path.  
**What should wait:** Learned ranking, multi-hop graph search, automatic semantic fallback, and contradiction resolution.

### 4. Connect benchmark manifests to a versioned behavioral result ledger

**Objective:** Turn the current benchmark metadata and retrieval fixtures into a reproducible runner that records expected/actual outcomes, retrieval-versus-answer-use success, latency/TTFT, configuration, commit, and optional hardware/resource data.  
**Affected modules:** `pipeline/benchmark.py`, `pipeline/retrieval_eval.py`, new bounded benchmark fixtures/results schema, CLI wrapper, tests.  
**Expected benefit:** Creates a baseline before routing and model-profile changes; converts observed failures into permanent cases; supports small-model scaling studies, grant evidence, and public engineering reports.  
**Tests/verification:** Stable schemas/versioning, deterministic fixture replay, dirty-worktree labeling, unavailable metric handling, no-match cases, prompt-contamination cases, annotation false positives, provider portability, and raw-model/full-stack comparison boundaries.  
**Why now:** Architecture is stable enough to measure, while forthcoming routing will multiply variables. Data accumulated now becomes more valuable over time.  
**What should wait:** Publication claims, large automated sweeps, learned evaluators, and full ablations until the initial runner is trustworthy.

### 5. Add explicit task profiles and provider/router observability before tools or vision

**Objective:** Define provider/model profiles for chat, proposal extraction, document annotation, embeddings, and later vision; record selection/fallback reasons and lifecycle/resource metrics before automatic routing is enabled.  
**Affected modules:** `pipeline/providers.py`, `pipeline/provider_state.py`, `pipeline/application.py`, configuration, diagnostics, benchmark runner, provider tests.  
**Expected benefit:** Faster and more reliable structured extraction, measurable small-versus-large-model tradeoffs, safe LM Studio/provider additions, and a stable foundation for tools, vision, speech, and the apartment.  
**Tests/verification:** Fake provider registry, explicit task selection, timeout/empty-output fallback, model availability, fixed generation options, lifecycle transitions, diagnostic attribution, and unchanged default Ollama chat.  
**Why now:** Do this after recommendations 1-4 so routing decisions are isolated, reviewable, and benchmarked rather than hidden heuristics.  
**What should wait:** Automatic autonomous routing, GPU model load/unload orchestration, vision monitoring, image generation, TTS, and permissioned tools. A permission engine must precede operational PC control.

## Deferred refactors

The following may eventually be valuable, but doing them now would increase risk without unlocking the immediate prototype:

- Splitting `pipeline/db.py` into many repositories or separate physical databases.
- Rewriting `AssistantSession` into a large service hierarchy.
- Replacing deterministic retrieval with production Chroma retrieval.
- Migrating or rebuilding production SQLite/Chroma solely for architectural cleanliness.
- Unifying the entire lore pipeline with assistant memory in one schema.
- Implementing multi-hop associations, temporal memory, contradiction truth maintenance, or emotion weights on every memory.
- Building a custom web UI before the OpenAI-compatible API/session/source contracts are reliable.
- Adding vision/image/TTS providers before provider profiles, permissions, and benchmark instrumentation.
- Building the apartment before lifecycle, session, source, and tool-state events are dependable.
- Creating persona-local databases before the core single-persona runtime and retrieval evaluation are stable.

## Audit limitations

- This was static repository inspection only. No authoritative WSL test suite, Ollama request, HTTP smoke test, SQLite migration, Chroma query, sync, annotation, or production-data operation was run.
- Test files and `CHANGELOG.md` provide evidence of intended and previously reported verification, but they are not proof that the current dirty working tree passes today. Recent changelog entries record focused document/retrieval/context tests; this audit does not restate those as independently reproduced results (`CHANGELOG.md:614-641`).
- Runtime behavior can vary by Ollama/client versions, model templates, quantization, OpenWebUI preprocessing, and local configuration. The code does not yet capture all of those inputs in an experiment ledger.
- Performance and model-quality claims require controlled measurements. No claim is made here that small models equal larger models, that semantic retrieval improves production assistant chat, or that the system is production-scale.
- Line references are navigation aids for the inspected snapshot, not permanent identifiers.
- The repository contained pre-existing modified and untracked files during inspection. This audit intentionally did not alter, stage, clean, or reinterpret those changes.
