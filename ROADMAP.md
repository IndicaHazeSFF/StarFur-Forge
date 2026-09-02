# StarFur Forge Roadmap v4

**Status:** Resident Intelligence Platform with an executable Persona Runtime
**Last updated:** 2026-08-22

`ROADMAP.md` is authoritative. `ROADMAP.v3.md`, `ROADMAP.v2.md`, and `ROADMAP.original.md` are preserved historical versions.

## Mission

StarFur Forge is a local-first Resident Intelligence Platform: a persistent environment where one or more companions remember responsibly, develop bounded interests and skills, perceive the user's world with permission, and assist through transparent state, tools, and providers.

The language model is a replaceable reasoning provider. The companion is the continuity system around it. A persona is not a giant prompt; it is a validated runtime whose current state is rendered into model context.

## Core architecture

```text
Shared environment
        |
StarFur Core
  |-- memory, provenance, retrieval, associations
  |-- Persona Runtime
  |     |-- static identity
  |     |-- dynamic personality
  |     |-- momentary state
  |     |-- behavior and attention rules
  |     |-- context renderer
  |-- providers and capability routing
  |-- tools, permissions, scheduler, learning sandbox
  |-- vision, media, resident apartment state
        |
Presentation clients
  |-- terminal / OpenWebUI / API
  |-- future TUI / dashboard / desktop apartment / phone / Steam
```

## Architectural invariants

- Persona, memory, policy, retrieval, providers, tools, and presentation remain separate concerns.
- Persona configuration is declarative and validated by default; user-provided files do not execute arbitrary code.
- Static identity is stable and user-controlled. Dynamic traits change slowly through explicit, explainable transitions. Momentary state can change per turn and decays or expires.
- State never silently rewrites canonical memories. Learning records observations, evidence, outcomes, and confidence separately from source memories.
- Only bounded, relevant state is rendered into model context. The model never receives an unbounded internal database or hidden chain of thought.
- Behavior rules may shape tone, attention, initiative, examples, and interaction style; engine policy still controls factual grounding, safety, provenance, and permissions.
- Autonomous work requires a sandbox, resource limits, logs, and user-visible outcomes. No background task may change production files, memories, or external systems without permission.
- Shared core memory can serve multiple personas. Persona-specific state is namespaced and does not alter shared factual truth.
- Tests use temporary SQLite, fake providers, fake collections, and deterministic clocks where possible.

## Completed foundation

### Manuscript and Crown of Claws

- **COMPLETED:** Prechunker-generated `canon/chapters/**/*.md` is the authoritative structured-analysis corpus.
- **COMPLETED:** Prechunker -> Mr. Chonker -> Mr. Annotator with defensive chunking, nested validation, bounded output, retries, and failure isolation.
- **COMPLETED:** Source cleanup, provenance preservation, fact durability classification, conservative ownership, semantic index invalidation, and targeted chapter reanalysis.
- **COMPLETED:** Crown of Claws structured entities, appearances, facts, proposals, aliases, canon export, and existing incremental sync behavior.

### Shared memory and retrieval

- **COMPLETED:** Additive domains, separate lore/assistant memory, assistant CRUD, validated types/retention/status, provenance, soft forgetting, correction, and compact public references.
- **COMPLETED:** Durable proposals with review lifecycle, evidence, approval linkage, exact-evidence identity, reinforcement, duplicate-evidence idempotency, inspection, and bulk approval confirmation.
- **COMPLETED:** Domain-scoped association graph with explainable one-hop retrieval context.
- **COMPLETED:** Deterministic retrieval, diagnostics, benchmark fixtures, lexical/semantic/no-match tier metrics, executable fixture-only deterministic/semantic/hybrid comparisons, and measured semantic cutoff plus ambiguity-margin calibration using temporary SQLite/Chroma state.
- **COMPLETED:** Conversational memory introspection limited to active canonical memories and approved provenance.

### Runtime and presentation

- **COMPLETED:** File-backed persona layer with neutral fallback and separate engine policy.
- **COMPLETED:** Read-only ContextManager, bounded session context, streaming, clean interruption rollback, context statistics, phase timing diagnostics, and runtime model selection.
- **COMPLETED:** Validated Ollama generation options, user-observation-only proposal provenance, and speculative-statement safeguards.
- **COMPLETED:** Ollama `ChatProvider` boundary with legacy fake-client compatibility.
- **COMPLETED:** Local OpenAI-compatible API and functional OpenWebUI integration.
- **COMPLETED:** Confirmation-gated factory reset/restore with backup safeguards and lore/assistant separation.

## Versioned benchmark foundation (begin early and grow continuously)

StarFur must maintain a reproducible behavioral benchmark layer above unit and integration tests. Begin the harness during the shared application/provider foundation, before routing and resident-environment work, so every later architectural change can be compared against accumulated evidence.

Each benchmark run records, when available: benchmark/schema version, git commit, provider/model/quantization, context size, hardware and resource profile, test case and expected result, actual result, pass/fail, retrieval IDs/scores/reasons, latency and time-to-first-token, and bounded CPU/RAM/VRAM/temperature metrics. Preserve real failures as permanent regression cases whenever practical.

Initial benchmark families:

1. Memory retrieval accuracy: Recall@K, Precision@K, false positives, and explicit no-match cases.
2. Retrieval success separately from model answer/use success.
3. Long-document RAG accuracy across increasing document sizes and chunk counts.
4. Annotation/proposal extraction accuracy and false-positive rate.
5. Context/RAG boundary isolation and prompt-contamination regressions.
6. Persona and instruction adherence.
7. Provider/model portability.
8. Latency, TTFT, and resource utilization.
9. Long-session, restart, persistence, and recovery behavior.

Add a small-model scaling benchmark that holds the surrounding StarFur architecture constant while varying model size/quantization. Report memory/retrieval performance separately from reasoning, instruction following, persona quality, and prose quality; the goal is to identify the minimum viable model capacity for reliable resident-assistant behavior.

Later add ablation runs that disable individual cognition components and compare full StarFur against those configurations and a raw-model baseline. Benchmark outputs should support local regression checks, technical validation, grant applications, and a public engineering portfolio without retaining unrestricted private conversations by default.
## The Persona Runtime

The current persona file is a compatibility input. The target architecture is a runtime that computes behavior context from three state layers:

### 1. Static identity

Slow-changing, explicitly configured facts such as name, species, core values, ethics, boundaries, relationship framing, and stable speech identity. Static identity is not rewritten by ordinary conversation.

### 2. Dynamic personality

Slowly changing traits such as interests, habits, relationship familiarity, trust, skill confidence, preferences, curiosity, and communication tendencies. Every change requires a source, reason, timestamp, bounded rate of change, and inspectable history.

### 3. Momentary state

Short-lived state such as mood, energy, attention, current activity, focus, urgency, social availability, and emotional response. Momentary state is derived from recent events and context, decays, and must not become permanent memory without an explicit observation/proposal path.

The runtime produces a `BehaviorContext`, not a final answer:

```text
identity + dynamic traits + momentary state + active memories
        |
attention selection and behavior rules
        |
compact model context packet
        |
ContextManager -> provider
```

Behavior rules may select warmth, verbosity, humor, curiosity, interruption style, examples, and clarifying-question behavior. They must not override engine policy, invent facts, expose private state, or mutate canonical memory.

## Revised implementation order

### Stage 1 - Persona Runtime compatibility foundation

1. **COMPLETED:** Defined validated, immutable `PersonaState`, `DynamicTraits`, `MomentaryState`, and `BehaviorContext` structures without changing prompt or runtime behavior.
2. **COMPLETED:** Load the current persona file into static identity with neutral compatibility trait/state defaults while preserving its rendered prompt exactly.
3. **COMPLETED:** Added deterministic optional state-to-context rendering behind `ContextManager`.
4. **COMPLETED:** Added bounded state snapshots and read-only `persona inspect` diagnostics.
5. **COMPLETED:** Migrated normal AssistantSession chat to include the current bounded BehaviorContext while preserving static persona identity, engine-policy precedence, deterministic retrieval, and provenance-scoped introspection behavior.

### Stage 2 - Shared application boundary

1. **COMPLETED:** Define the thin `AssistantApplication` service primitive for stateful chat/commands, retrieval, introspection, proposals, context diagnostics, and model selection through the existing `AssistantSession` orchestration.
2. **COMPLETED:** Define a core-owned structured capability registry and immutable manifest, attach it through `AssistantApplication`, and inject selected entries through `ContextManager` only for explicit capability/help questions.
3. **COMPLETED:** CLI Assistant Mode and the OpenWebUI-compatible API now construct/use the shared `AssistantApplication` facade; future Textual TUI and dashboard surfaces should use the same factory rather than duplicate orchestration.
4. **COMPLETED:** Add bounded explicit API conversation isolation: independent in-memory `AssistantSession` state for clients supplying a stable conversation key, per-session request serialization, pinned in-flight sessions during LRU eviction, and legacy default-session compatibility. Shared canonical memory remains domain-scoped; conversation keys are not authentication or authorization.
5. **COMPLETED:** Added a read-only shared diagnostics snapshot/API endpoint, explicit generation/streaming lifecycle transitions, and an opt-in provider health probe. Normal diagnostics remain passive; `?probe=provider` records only bounded availability metadata. Richer resource metrics remain future work.
6. **COMPLETED FOUNDATION:** Added a shared provider/model lifecycle state machine with bounded disconnected, connecting, loading, ready/idle, generating, streaming, cooling, unloading, and error states. Provider adapters own observed generation transitions; exact load/unload state remains conservatively unavailable when a backend does not expose it. The application facade exposes the snapshot to API consumers without making persona behavior depend on parsed response text.
7. Preserve the local-first `ChatProvider` boundary and fake-provider tests.
8. **COMPLETED:** Make deterministic assistant-memory retrieval an explicit injected dependency of `AssistantSession`/`AssistantApplication`, preserving current ranking, diagnostics, custom-loader compatibility, and API/CLI behavior. Future semantic/hybrid chat retrieval requires an explicit policy and benchmark-backed opt-in.
9. **COMPLETED:** Add declarative task/provider profiles for current chat, proposal, and document-annotation workloads plus future task names. Profiles are validated configuration only; they preserve the active session model, reject unavailable provider declarations, and intentionally stop short of automatic routing/fallback execution.

### Persona-local memory architecture

Each persona eventually receives a lazily initialized, strictly namespaced memory view alongside StarFur Core memory. The first implementation should reuse shared storage infrastructure with a `persona:<id>` namespace; separate physical databases or Chroma collections remain an optional packaging/scale optimization.

```text
persona:<id>
├── specific memory       structured lessons, experiences, concepts, and self-observations
├── semantic memory       embeddings of persona-learned material and approved references
└── associative memory    links among interests, skills, lessons, outcomes, and context
```

Persona-local memory is not user memory. User facts remain in the human-controlled assistant memory domain and are never silently created by a persona. Persona self-memory may be written only when its configured learning policy permits it, with bounded confidence thresholds, provenance, timestamps, source experiments, outcomes, and soft-forget/supersession behavior. High-impact or uncertain self-memories should remain reviewable.

A persona may learn incrementally through verified tasks: interest signal -> bounded experiment -> sandboxed result -> lesson/evidence -> conservative skill update -> associative links. Failed experiments remain useful evidence and must not be converted into claimed expertise. Persona-local semantic indexing must remain filterable by persona namespace and must never contaminate Crown of Claws or shared user-memory retrieval.

### Stage 3 - Interests, attention, and verified learning

1. **COMPLETED FOUNDATION:** Added immutable, persona-namespaced interest and verified-skill state with bounded sub-1.0 confidence, evidence counts, recency, and deterministic half-life decay. The first slice is in-memory/test-only: it does not infer interests from chat, alter prompts, persist data, or claim expertise. Future verified-learning and persona-local storage work will own those decisions.
2. **COMPLETED INITIAL SLICE:** Added deterministic, bounded attention selection for explicitly supplied persona interests. Only direct lexical matches are exposed as optional presentation cues for examples, analogies, and follow-ups; skills are excluded, unmatched interests are absent, and attention cannot redirect a request, claim expertise, create a memory, or persist state.
3. **COMPLETED FOUNDATION:** Added immutable, persona-namespaced explicit learning records separate from canonical memories. Records capture bounded source, hypothesis, isolated attempt, result, verification evidence, timestamp, and optional target skill. Only an explicit `verified_success` record with evidence can conservatively reinforce a skill; failed/inconclusive attempts remain inspectable but never establish expertise. The slice remains in-memory/test-only and does not execute tasks, infer learning from chat, persist data, or change prompts.
4. **COMPLETED FOUNDATION:** Added immutable, persona-namespaced RSS/reference intake records as bounded explicit event inputs. A supplied reference can raise one declared interest/curiosity signal, but cannot create a skill, execute work, fetch a network resource, persist data, write user memory, or alter prompts. Future fetching/scheduling requires explicit permissions, rate limits, source policy, and user-visible controls; reading a reference never establishes expertise.
5. **COMPLETED FOUNDATION:** Added a pre-execution local learning-sandbox contract for bounded declarative exercises, temporary text-only workspaces, timeout/resource policy, and user-visible reports. The default backend denies execution; a normal subprocess must never be presented as filesystem/network isolation. Future container/VM/isolated backends must independently enforce policy before compilation/tests can run. Sandbox output alone never changes skills or production state.
6. Never allow background learning to modify production projects or claim skill without verification.

### Stage 4 - Derived emotion, relationships, and behavior

1. **COMPLETED FOUNDATION:** Added deterministic, explainable momentary-state derivation from explicit caller-authorized interaction/system/approved-context signals. It is ephemeral and bounded: no ordinary-chat inference, persistence, canonical-memory writes, durable trait mutation, or direct chat behavior change. Future interaction, relationship, and association systems must supply validated signals rather than treating memories as arbitrary emotion weights.
2. **COMPLETED FOUNDATION:** Added bounded, explainable in-memory momentary-state transition snapshots. Each transition decays a supplied prior state toward neutral, applies a caller-supplied candidate only beyond a hysteresis threshold, and rate-limits larger changes. It has no clock, ordinary-chat inference, persistence, memory weighting, or prompt mutation.
3. **COMPLETED FOUNDATION:** Added deterministic, inspectable real-world relationship-state derivation for familiarity, trust, and evidence confidence. It accepts only explicit authorized signals, applies conservative asymptotic bounded changes, preserves its immutable baseline, and records per-signal contributions. It does not inspect ordinary chat, persist data, write canonical facts, change prompts, or mix with adventure relationships.
4. **COMPLETED INITIAL SLICE:** Added a deterministic, read-only behavior mapper from existing `BehaviorContext` into bounded presentation controls for warmth, directness, humor, initiative, patience, verbosity, clarification threshold, and interruption tolerance. `ContextManager` renders only this Core-provided guidance; it cannot change state, facts, policy, commands, permissions, or capabilities. Future emotion/relationship derivations may feed validated state into this mapper.
5. **COMPLETED FOUNDATION:** Added deterministic half-life decay, hysteresis, and per-field rate limits for momentary-state transitions. The transition report identifies decayed retention plus applied/held fields so behavior can be inspected without claiming the persona's inner state as fact. Future state storage must preserve these boundaries and remain separate from canonical memory.
6. **FUTURE CONFIGURATION REQUIREMENT:** Add validated, versioned stat-evolution profiles for dynamic traits, relationship familiarity/trust, and momentary state. Each profile must define permitted signal types, baseline, bounded gain/loss formula, decay/asymptote, hysteresis, and per-turn/per-time rate limits. Core—not the language model—must calculate transitions and emit an inspectable change explanation. Persona setup UX may select or edit safe profiles, but it must not permit arbitrary code or silent rewrites of canonical memory.

### Stage 5 - Multiple personas and discussion sandbox

1. **COMPLETED FOUNDATION:** Added a deterministic declarative persona-package registry with validated static prompt/initial-state consistency, stable lookup, duplicate prevention, and safe fallback loading. Packages expose only public identity metadata and own no executable code, provider configuration, tools, permissions, Core memory, or active-session switching. Future explicit session-scoped selection will share Core services rather than copying data into persona packages.
   **COMPLETED INITIAL SLICE:** Added explicit session-scoped active-persona controls (`persona list`, `persona current`, and `persona use <persona-id>`). A selection changes only later prompt/runtime state for that session and clears its recent conversation context; shared memory, providers, tools, permissions, configuration, and other conversations remain untouched.
2. **COMPLETED INITIAL SLICE:** Added a typed, in-memory persona runtime registry keyed by persona ID. Dynamic/momentary state, persona-local development (interests, skills, and verified learning records), and explicitly supplied real-world relationship snapshots now remain isolated when sessions switch personas or when the application creates separate presentation sessions. A bounded structured public snapshot can supply future UI/TUI/apartment views without exposing prompts, raw evidence, relationship subjects, or user-memory content. The registry is deliberately restart-ephemeral and has no ordinary-chat inference, user-memory access, persistence, prompt injection, relationship inference, or apartment-state payloads. Adventure relationships remain separately namespaced. Future apartment slices must add validated typed state to this boundary.
3. **COMPLETED INITIAL SLICE:** Added deterministic, explainable per-persona shared-memory visibility. Persona packages may declaratively set an inclusive `minimum_shared_memory_confidence`; after the active session's injected retriever ranks same-domain active records, Core filters them against that policy while preserving the order/scores of visible records. Bounded decisions appear in `context stats`; introspection uses the same policy. Stock packages remain at the backward-compatible default `0.0`. This does not rewrite shared truth, alter domains, persist persona knowledge, or enable automatic learning.
   **FUTURE UX REQUIREMENT:** Persona setup must make shared-memory onboarding configurable. A new persona should default to a restricted/familiarity-aware access profile, while users who want a drop-in replacement may explicitly choose to inherit the established persona's visibility behavior. The UX must expose the choice clearly, write only validated persona configuration, and preserve the distinction between memory confidence, persona familiarity, memory scopes, and explicit disclosure permission.
   **COMPLETED INITIAL SCOPE SLICE:** Persona packages validate an optional `allowed_memory_scopes` allowlist against conservative scopes derived only from existing assistant-memory types: personal, preference, project, relationship, and routine. Core combines that decision with confidence visibility after ranking; both must allow a record before it reaches the active persona or introspection. Stock packages remain unrestricted. This does not classify legacy memory from prose or provide sensitive/custom categories.
   **COMPLETED METADATA FOUNDATION:** Assistant memories and proposals carry nullable explicit `visibility_scope` metadata. Existing rows preserve their type-derived fallback unchanged; an explicit `roleplay` scope can be preserved through approval and takes precedence only when a trusted/user-controlled workflow assigns it. No model extraction or automatic prose classification assigns scope in this phase. Remaining: explicit review/editor controls and future UX disclosure/access configuration.
   **COMPLETED EXPLICIT EDITOR SLICE:** Core-owned `memory scope` and pending-only `proposal scope` commands let a user assign or clear validated scope metadata without model calls or prose inference. Approval retains the reviewed proposal scope. Future dashboard controls must use this same Core path rather than write database rows directly.
   **COMPLETED PRE-ADVENTURE SESSION SLICE:** Added bounded, session-ephemeral `roleplay begin/end/status` controls plus a deliberately small set of clear natural-language start phrases. Entering/leaving clears recent chat context; while active, Core—not the model—tags otherwise eligible user-memory proposals and explicit remembers with `roleplay` scope. This has no adventure namespace, story database, event log, title lookup, replay, automatic roleplay classification, or durable story state.
4. Build a deterministic discussion sandbox with temporary shared memory, seeded events, multiple personas, replay, metrics, and bounded turns.

### Stage 5A - Persistent CYOA adventure workspaces

Create-your-own-adventure sessions are isolated, mountable story worlds rather than another form of personal memory. Each adventure receives a lazily created `adventure:<id>` namespace and a small workspace under `adventures/<stable-id>/`, with a metadata manifest, adventure database, semantic index, and bounded transcript/snapshot data. A global registry stores only enough metadata to resolve and mount an adventure without scanning every story database.

**COMPLETED REGISTRY FOUNDATION:** Added a deterministic local adventure registry that creates only a validated global metadata entry and an `adventures/<stable-id>/manifest.json` workspace marker. Title resolution is exact and normalized; a duplicate title is rejected rather than silently creating a second world. This slice does not mount a story, create an event log/database/index, call a model, or access shared memory.

**COMPLETED REGISTRY COMMAND SLICE:** Added exact Core controls to list registered workspaces, create a named metadata-only workspace, and inspect an exact title. The commands deliberately cannot start, resume, mount, or replay a story yet; they are a safe smoke-test surface for the isolated registry.

**COMPLETED SESSION-MOUNT FOUNDATION:** A user may now explicitly load or unload a resolved workspace in one conversation. The mount contains only registry metadata, clears that session's recent context on transitions, and renders a boundary stating that there are no events, characters, relationships, replay history, or hidden narration to resume. It does not activate roleplay or write story data.

**COMPLETED EVENT-LOG FOUNDATION:** Added an isolated, lazily created `events.jsonl` primitive beneath a registry-owned adventure workspace. It accepts only a closed, validated set of continuity-critical Core-authored event types, validates every stored record and sequence on read, and remains append-only. This storage primitive has no user command, model extraction, narration capture, shared-memory integration, prompt mount, snapshot, relationship calculation, or automatic event creation yet.

**COMPLETED READ-ONLY EVENT MOUNT:** Loading an adventure now reads only its validated event log and supplies at most eight recent summary-only event facts as bounded replay context. `adventure events` is a Core-owned read-only inspection control. This does not create events, expose event details, capture narration, start roleplay, build a replay engine, or merge adventure facts into shared memory.

**COMPLETED EXPLICIT EVENT-AUTHORING SLICE:** `adventure record <event-type>: <summary>` is a loaded-workspace-only Core command that appends one validated continuity event. It is deliberate rather than model-driven: ordinary narration and chat cannot create events. The command refreshes only the bounded mounted replay view; it does not create a proposal, touch shared memory, infer facts, capture details, start roleplay, or implement automatic salience.

**COMPLETED INITIAL REPLAY-SPINE SELECTION:** Adventure mounting now deterministically rebuilds a small chronological replay spine from its authoritative event log. It preserves the initial event, latest high-value continuity categories, and remaining recency within the prompt budget. This is read-only selection, not a stored snapshot, branch model, prose replay, or semantic importance inference.

**COMPLETED INITIAL LIFECYCLE CONTROLS:** Exact `adventure resume <title>`, `adventure pause`, `adventure end`, and `end story now` give Core—not the narrator—control of story-session transitions. Resume is an explicit load alias; pause/end preserve the event log while cleanly unmounting and ending active roleplay. No archive/reset/delete workflow or natural-language title resolution was added.

**COMPLETED INITIAL STRUCTURED-STATE SLICE:** `adventure state set <key>: <value>` appends a validated explicit `state_change` record; `adventure state` and mounted prompt context deterministically project the latest bounded values from the event log. State is event-backed and rebuildable, not extracted from narration or model output. This does not add inventory/relationship databases, automatic state capture, snapshots, branching, or simulation.

**COMPLETED INITIAL QUALITATIVE-RELATIONSHIP SLICE:** `adventure relationship set <character> <dimension>: <value>` appends a validated explicit `relationship_change` record; `adventure relationships` and mounted prompt context deterministically project the latest bounded qualitative values per character/dimension. This remains isolated to the adventure event log, with no numeric meters, automatic relationship inference, emotion derivation, or real-world persona relationship interaction.

**COMPLETED FICTIONAL-METER PRESENTATION BOUNDARY:** During explicit roleplay or a mounted adventure, Core redacts numeric relationship-meter wording from retrieved `relationship_context` records before prompt assembly unless the user explicitly requests a meter/score/internal diagnostic. Stored memories, retrieval ranking, diagnostics, and non-relationship numeric facts remain unchanged.

**COMPLETED INITIAL CHARACTER-KNOWLEDGE SLICE:** `adventure knowledge set <character> <knows|believes|uncertain>: <fact>` appends a validated explicit `character_knowledge` record; `adventure knowledge` and mounted prompt context project the latest bounded stance per character/fact. Character beliefs and uncertainty are distinct from objective world state. No automatic extraction, lie-reasoning, hidden-information simulation, or shared-memory interaction was added.

**COMPLETED INITIAL TURN-TRANSACTION SLICE:** Core can explicitly begin, stage, commit, or abort a bounded batch of ordinary adventure event drafts. Staged drafts are session-local and invisible to the model/log until one all-or-nothing commit; workspace transitions discard them. Existing state, relationship, and knowledge commands remain immediate in this initial slice. Future generated-turn orchestration must abort on interruption/failure before partial output can become canonical.

**COMPLETED INITIAL WRITE-COORDINATION SLICE:** Adventure event writes now acquire a workspace-scoped OS advisory lock that fails closed for live concurrent writers and is released when its owner exits; the persistent lock file therefore cannot itself become a stale ownership claim. Staged-turn commits retain a validated opaque request ID on their appended event batch. Repeating the same completed batch request returns the original events without duplication; reusing its ID for different drafts fails. A fully written, validated `.pending` replacement is recovered only when it extends the authoritative log; malformed or conflicting artifacts fail closed without overwriting it. A valid nonempty event log repairs its stale `not_created` manifest marker, while a manifest claiming a missing log fails closed. Remaining: broader cross-process failure injection.

**COMPLETED TYPED-MUTATION ENVELOPE FOUNDATION:** Added pure schema-v2 envelope validation for explicit Core-authored state, qualitative relationship, character-knowledge, and generic resource-operation mutations. Each envelope carries event identity, timestamp, source, optional request ID, optional supersession reference, and one typed payload kept separate from narrative summary/details. The event-log adapter now reads and preserves validated v2 entries alongside existing v1 records, projecting typed facts through the established readers without prose parsing; Core still writes v1 by default. No command, model extraction, automatic prose-to-mutation path, or migration of existing logs changed in this slice.

**COMPLETED MIXED-TURN STAGING FOUNDATION:** One session-local adventure turn can now retain ordinary event drafts and validated typed state, qualitative relationship, and character-knowledge mutations together under one request ID. Typed mutations produce compatible schema-v1 structured drafts in session staging; the only event-log write remains the explicit all-or-nothing commit path, preserving current storage policy while preventing a future generated turn from splitting its narrative continuity from its structured facts.

**COMPLETED INITIAL A4 CORE-WIRING SLICE:** Exact `adventure turn stage state`, `adventure turn stage relationship`, and `adventure turn stage knowledge` controls now validate and stage their structured facts with ordinary drafts. The complete mixed batch remains invisible to projections, prompt context, and the log until Core commit. Existing direct state/relationship/knowledge controls remain intentional immediate-write alternatives. Remaining: generated-turn interruption/retry orchestration and later schema-v2 writer migration.

**COMPLETED AUTHORITATIVE-PROJECTION SLICE:** State, qualitative relationship, and character-knowledge projections now rebuild completely from the validated event log. Separate deterministic selectors retain at most twelve facts of each kind for prompt context; they do not truncate the authoritative projection. Inspection, reload, and diagnostics expose total authoritative counts alongside selected bounded-context counts. Future selector quality may improve, but context-budget changes must never lose canonical adventure state.

**COMPLETED INITIAL A5 CORE-DISPATCH SLICE:** The `adventure` command namespace now remains Core-owned after exact documented controls are evaluated. Malformed, unknown, and near-miss `adventure ...` input returns deterministic guidance instead of reaching natural-language/model generation. This initial boundary preserves command isolation: no provider call, memory proposal, chat-history mutation, or adventure event write occurs. The OpenAI-compatible API now has focused coverage proving exact Core staging and malformed-command isolation survive the adapter, and it ignores stale OpenWebUI document-context/review extensions whenever the actual user message is an `adventure` command. Remaining: a live OpenWebUI smoke check only.

**COMPLETED INITIAL ADVENTURE-EVALUATION SLICE:** `adventure-integrity-v1` supplied checked-in deterministic fixtures for latest structured projections, replay-spine selection, bounded-context separation, and repeatability. **COMPLETED RESOURCE FIXTURE SLICE:** `adventure-integrity-v2` additionally evaluates generic resource projection, public-only context selection, resource-summary replay isolation, and invalid authoritative resource-operation rejection. **COMPLETED BRANCH FIXTURE SLICE:** `adventure-integrity-v3` compares a complete source stream with a declared checkpoint-derived child prefix, proving later source facts do not enter the child projection or bounded replay. `python starfur.py adventure-eval` runs them entirely in memory with no provider, production memory, runtime workspace, or ledger write. Remaining: command/lifecycle, corruption/recovery, relationship consistency, restart, and result-ledger compatibility through a dedicated bounded adventure-result schema.

**COMPLETED INITIAL B1 RESOURCE-DEFINITION SLICE:** Added a pure scenario-declared resource catalog with closed generic kinds (`flag`, `enum`, bounded integer/decimal, inventory, equipment, objective, location, and clock), stable IDs/labels, public-or-hidden visibility, bounds or enum values where applicable, and validated permitted-operation metadata. This is definition-only: no workspace manifests, resource values, event types, commands, prompt context, game rules, or provider authority changed. Remaining B1 work must introduce resource state and event-backed operations only after validating them against this catalog.

**COMPLETED INITIAL B1 RESOURCE-VALUE SLICE:** Added a pure immutable resource-state reducer for declared catalogs. It establishes deterministic defaults and validates generic `set`, arithmetic, inventory, equipment, objective, location, clock, and flag operations before producing a replacement state; unknown resources, unsupported operations, illegal transitions, and out-of-bound values fail without mutating the prior state. At this slice, it was in-memory only: no adventure manifest storage, event records, commands, prompt/UI projection, or provider/model authority changed. Remaining B1 work is authoritative resource-operation events and complete-vs-bounded projections.

**COMPLETED INITIAL B1 CATALOG-PERSISTENCE SLICE:** A workspace manifest may now receive one validated, JSON-safe declared resource catalog before an event log exists. The catalog is immutable thereafter (identical setup is idempotent); legacy workspaces safely read as having no declared resources. This is an internal package/Core setup boundary only: it creates no runtime values, commands, event types, prompt context, UI behavior, model authority, or game-specific schema. Remaining B1 work is authoritative catalog-validated resource-operation events and projections.

**COMPLETED INITIAL B1 RESOURCE-EVENT SLICE:** Added a closed `resource_change` schema-v1 event representation. The event log replays existing resource operations through the workspace's immutable catalog before reading or appending, so undeclared resources, invalid operations, malformed values, inventory underflow, and bounds violations fail before a log mutation. The pure reducer can rebuild full values from these validated events. There is no user-facing resource command, mounted-session/prompt/UI projection, provider extraction, or game-specific behavior yet. Remaining B1 work is complete-vs-bounded mounted resource projection and explicit Core controls.

**COMPLETED INITIAL B1 RESOURCE-PROJECTION SLICE:** Mounted adventure sessions now retain the complete event-backed resource projection while exposing at most twelve declared `public` values to normal prompt context and the read-only `adventure resources` control. Hidden values remain in the authoritative projection but are not shown to the model or normal inspection. No resource mutation command, package-configuration UI, provider extraction, simulation, or game-specific mechanics were added. Remaining B1 work was explicit Core mutation/staging controls and resource benchmark fixtures.

**COMPLETED INITIAL B1 RESOURCE-CONTROL SLICE:** Exact Core commands now append or stage generic catalog-validated `resource_change` operations: `adventure resource <resource-id> <operation>[: <value>]` and `adventure turn stage resource ...`. Core parses only the narrow command payload, validates against the complete authoritative state plus earlier staged resource drafts, and the event log repeats validation under its write lock. Public values remain separately bounded for context; hidden resource values and free-form resource-event summaries are excluded from normal prompt context. Core commands continue to write schema-v1; schema-v2 resource envelopes are read-compatible for correction history only. Remaining B1 work is fixture/benchmark coverage and later package-driven setup UX.

**COMPLETED INITIAL B2 ACTIVITY-PROJECTION FOUNDATION:** Added a pure active-event resolver for the existing schema-v2 optional supersession reference. It keeps every append-only historical event inspectable while deterministically identifying the active tip of each valid correction chain. Unknown, forward, duplicate-target, or self supersession fails closed. This foundation does not yet write corrections, change existing state/relationship/knowledge/resource projections, infer retractions or contradictions, expose a command, or grant model authority.

**COMPLETED INITIAL B2 STATE-PROJECTION INTEGRATION:** The complete current-story-state projection now consumes active event semantics. A superseded schema-v2 state event remains in the append-only audit history, while its explicit replacement alone determines the current state fact. Relationship, character-knowledge, resource, retraction, contradiction, correction-writing, and command behavior remain unchanged for later B2 slices.

**COMPLETED INITIAL B2 RELATIONSHIP-PROJECTION INTEGRATION:** The complete qualitative relationship projection now consumes active event semantics. A superseded schema-v2 relationship event remains in the append-only audit history, while its explicit replacement alone determines the current relationship fact. Character-knowledge, resource, retraction, contradiction, correction-writing, and command behavior remain staged for later B2 slices.

**COMPLETED INITIAL B2 KNOWLEDGE-PROJECTION INTEGRATION:** The complete character-knowledge projection now consumes active event semantics. A superseded schema-v2 knowledge event remains in the append-only audit history, while its explicit replacement alone determines the current character perspective. Resource, retraction, contradiction, correction-writing, and command behavior remain staged for later B2 slices.

**COMPLETED INITIAL B2 RESOURCE-PROJECTION INTEGRATION:** Schema-v2 envelopes now represent a generic resource operation so corrected resource history can be read without changing current Core writers. The complete resource projection resolves active persisted events before applying catalog validation; sequence-free drafts remain outside supersession while an atomic batch is being validated. A superseded resource event remains in the append-only audit history, while its replacement alone determines current resource values and provenance. Retraction, contradiction, correction-writing, and command behavior remain staged for later B2 slices.

**COMPLETED INITIAL B2 CORRECTION-INSPECTION SLICE:** Exact `adventure corrections` now renders a read-only audit of the active/superseded event IDs involved in valid correction chains. It reads the append-only log directly, calls no provider, does not mutate session context, and never writes a correction, retraction, or contradiction.

**COMPLETED INITIAL B2 CORRECTION-WRITER SLICE:** Exact `adventure correct state|relationship|knowledge|resource` controls append one explicit schema-v2 typed replacement for a currently active event. The writer uses the same workspace lock, append-only replacement, catalog validation, and mount refresh path as other authoritative writes; it rejects missing, inactive, or type-mismatched targets and never edits/deletes the original record or allows a forked correction chain. It does not correct ordinary narrative events, infer edits from model prose, support turn staging, retractions, or contradiction resolution. Remaining B2 work is distinct retraction/dispute semantics.

**COMPLETED INITIAL B2 RETRACTION SLICE:** Exact `adventure retract <AE-######>: <reason>` appends one Core-owned schema-v2 audit event that supersedes one currently active event without substituting a new fact. Complete state, relationship, knowledge, and resource projections rebuild without the retracted event while the full audit history remains intact. Retractions are excluded from bounded replay context, cannot be drafted, cannot retract a retraction, and cannot fork an inactive chain. Contradiction/dispute semantics remain later B2 work.

**COMPLETED INITIAL B3 CHECKPOINT-REFERENCE SLICE:** Exact `adventure checkpoint <label>` records a named immutable reference to the current authoritative event-log prefix under the existing workspace write lock. Each reference stores a bounded label, event count/last ID, and deterministic prefix fingerprint; it remains verifiable after later append-only events. `adventure checkpoints` is read-only. This is not yet a snapshot, rewind, restore, fork, branch, archive, or provider feature.

**COMPLETED INITIAL B3 CHECKPOINT-INSPECTION SLICE:** Exact `adventure checkpoint inspect <checkpoint-id|label>` resolves a verified prefix and recomputes only its complete derived state/relationship/character-knowledge counts. It is read-only and does not alter the mount, event log, active branch, or model context. Restore/fork semantics remain separate later B3 work.

**COMPLETED INITIAL B3 FRESH-RESTART SLICE:** Exact `adventure restart fresh <new title>` creates and mounts a wholly separate adventure workspace while preserving any previously loaded one unchanged. It carries no event/state/checkpoint/history/roleplay context forward and deliberately does not claim established-premise restart, restore, rewind, clone, or branch semantics. Checkpoint-backed branching remains later B3 work.

**COMPLETED INITIAL B3 ESTABLISHED-PREMISE RESTART SLICE:** Exact `adventure restart established <checkpoint-id|label>: <new title>` creates and mounts an isolated child workspace from a verified checkpoint of the currently loaded adventure. The child copies only that authoritative event prefix and immutable resource catalog, records immutable parent/checkpoint provenance, and owns all future appends; the source adventure, later source events, source checkpoints, session context, and roleplay state remain separate. This is not restore, rewind, merge, or automatic branch selection.

**COMPLETED INITIAL B3 BRANCH-INTEGRITY FIXTURE SLICE:** Provider-free `adventure-integrity-v3` evaluates source projections alongside a declared checkpoint-derived child prefix. It proves later source facts do not enter the child projection or bounded replay context and runs each fixture twice for repeatability; command/workspace I/O recovery remains covered separately.

**COMPLETED INITIAL C1 STORY-SESSION ENTRY SLICE:** Exact `adventure begin <title>` loads one existing workspace and starts the session-local roleplay boundary as one Core operation. It refuses to discard staged turn data, creates no workspace/event, and never infers story entry from ordinary prose. Natural-language discovery aliases and archive/reset lifecycle work remain later.

**COMPLETED INITIAL C1 SESSION-BINDING INSPECTION SLICE:** Exact `adventure session` reports only the current Core-owned workspace/persona/roleplay/turn-staging binding and branch origin when applicable. It is read-only, prompt-safe, and contains no event prose or private persona state; future presentation surfaces can consume the same lifecycle boundary.

**COMPLETED INITIAL GOVERNED-PARTICIPANT CONTRACT:** Added provider-free contracts for treating Murr or another persona as a bounded adventure party member, alongside NPC participant memory policies. Participant memory is adventure-namespaced and bounded; initiative is disabled or explicitly limited by triggers, action types, cooldowns, per-turn limits, and confirmation policy. This does not yet schedule autonomous turns, call providers, write events, or add voice/apartment presentation.

**COMPLETED INITIAL C2 TRANSCRIPT-CONTRACT SLICE:** Added a closed, provider-free `AdventureTranscriptRecord` for bounded user/narrator presentation text. Transcript records are structurally distinct from canonical events and typed mutations, have no storage or automatic capture yet, and may never rebuild state, replay, memory, or prompt facts. Future retention must be explicitly configurable and permissioned.

**COMPLETED INITIAL C2 TRANSCRIPT-STORE SLICE:** Added an optional append-only transcript log under one registered adventure workspace. It validates full sequence history, uses an advisory writer lock and atomic replacement, and remains entirely absent from event-log manifest reconciliation because transcript is not story truth. No command, automatic chat capture, prompt injection, provider call, retention policy, or event extraction was added.

**COMPLETED INITIAL C2 TRANSCRIPT-CONTROL SLICE:** Exact `adventure transcript` and `adventure transcript record <user|narrator>: <text>` now expose bounded manual inspection/recording without model generation. Transcript entries remain optional presentation history only: they do not establish events, state, replay facts, memories, or prompt context. Automatic capture, retention settings, and narrative extraction remain separate future boundaries.

**COMPLETED INITIAL C4 IMPORT-STAGING SLICE:** `pipeline.adventure_import` can append an explicit selection of already reviewed document candidates plus source/chunk provenance under a registered adventure workspace. `POST /v1/starfur/documents/adventure-import` requires the existing adventure title, original server-side review IDs, and exact confirmation; matching retry is idempotent. The isolated staging log is non-canonical: it creates no event, state, replay fact, prompt context, assistant memory, or extraction result. UI wiring and the later typed import-review/commit policy remain separate.

**COMPLETED INITIAL C4 IMPORT-INSPECTION SLICE:** Exact `adventure imports` and `adventure import inspect <AI-######>` expose only bounded staged candidate metadata from the loaded workspace. These are read-only Core controls with no provider call, event write, state mutation, prompt injection, or memory write. Typed import review and canonical event/state commit remain separate.

**COMPLETED INITIAL C4 IMPORT-MAPPING SLICE:** Exact `adventure import map <AI-######> <C-###> <premise|state|relationship|knowledge|resource|exclude>` records an explicit user-authored destination plan for one staged candidate, while `adventure import mappings <AI-######>` exposes the latest plan. The append-only planning record remains non-canonical: it creates no event, state, replay fact, prompt context, memory, or model request. A later typed, validation-gated commit boundary alone may turn a mapped candidate into adventure truth.

**COMPLETED INITIAL C4 PREMISE-COMMIT SLICE:** Exact `adventure import commit premise <AI-######> <C-###>` can turn only a currently `premise`-mapped reviewed candidate into one idempotent, auditable canonical `premise` event. It uses only the staged candidate's bounded reviewed summary/details and cannot infer structure or commit state, relationship, knowledge, resource, or excluded mappings. Those destinations remain planning-only until their own typed validation/commit boundaries exist.

**COMPLETED INITIAL C4 STATE-COMMIT SLICE:** Exact `adventure import commit state <AI-######> <C-###> <key>: <value>` requires a current `state` mapping and an explicit user-supplied, normal-validator-approved key/value. The reviewed candidate is bounded audit provenance, not authority to extract or infer a mutation; mapping-keyed retries are idempotent. Relationship, knowledge, resource, and excluded mappings remain planning-only.

**COMPLETED INITIAL C4 RELATIONSHIP-COMMIT SLICE:** Exact `adventure import commit relationship <AI-######> <C-###> <character> <dimension>: <value>` requires a current `relationship` mapping plus explicit qualitative Core-validated values. A reviewed document cannot infer a relationship, create a numeric meter, or touch real-world persona relationships; it provides only bounded audit provenance. Knowledge, resource, and excluded mappings remain planning-only.

**COMPLETED INITIAL C4 KNOWLEDGE-COMMIT SLICE:** Exact `adventure import commit knowledge <AI-######> <C-###> <character> <knows|believes|uncertain>: <fact>` requires a current `knowledge` mapping and an explicit character-specific, normal-validator-approved perspective. The reviewed document cannot infer the claim or turn belief/uncertainty into objective truth; it is bounded audit provenance only. Resource and excluded mappings remain planning-only.

**COMPLETED INITIAL C4 RESOURCE-COMMIT SLICE:** Exact `adventure import commit resource <AI-######> <C-###> <resource-id> <operation>[: <value>]` requires a current `resource` mapping plus an operation permitted by the loaded adventure's immutable resource catalog. Core validates bounds and transitions through the event log; documents cannot invent resources, bypass rules, or expose hidden values. Excluded mappings remain planning-only.

**COMPLETED INITIAL C4 IMPORT-AUDIT SLICE:** Exact `adventure import status <AI-######>` provides a read-only per-candidate view of the latest import plan and mapping-keyed canonical event history. `exclude` remains an explicit plan-only choice: it never deletes, retracts, or hides an already committed event. Explicit correction/retraction controls remain the sole canonical-history writers.

**COMPLETED INITIAL C4 MULTI-SOURCE BUNDLE SLICE:** Exact `adventure import bundle create <title>: <AI-######> <AI-######> [... ]` records one append-only, non-canonical grouping of two or more staged reviewed sources for a workspace. `adventure import bundles` and `adventure import bundle inspect <AB-######>` provide bounded inspection. This supports a `details.md` plus exported conversation workflow without automatic prompt mounting, event extraction, or canonical import.

**COMPLETED INITIAL C4 BUNDLE-AUDIT SLICE:** Exact `adventure import bundle status <AB-######>` composes each bundled source's existing read-only mapping and canonical-history audit. It lets a user inspect progress across a `details.md` + summary/source set without changing mappings, events, state, memories, or prompt context.

**COMPLETED INITIAL C3 STAGED-TURN REVIEW SLICE:** Exact `adventure turn inspect` renders the current session-local ordinary and typed staged drafts before commit. It stays read-only, redacts hidden resource changes, and gives a future generated-turn policy a human-visible validation checkpoint without making partial narration canonical.

**COMPLETED INITIAL C3 STAGED-TURN EDIT SLICE:** Exact `adventure turn remove <staged-event-number>` discards one pre-commit draft by its inspected position while preserving the alignment of later typed mutations. It is session-local only and never deletes, rewrites, or retracts canonical event history.

**COMPLETED INITIAL C3 UNTRUSTED-CANDIDATE SLICE:** `pipeline/adventure_turn_candidates.py` now validates a bounded, decoded provider candidate envelope for ordinary story events only. The output has deterministic candidate IDs but no authority to stage, write, prompt-inject, or commit; candidate confidence is metadata, not trust. Typed state, relationship, knowledge, and resource proposals remain deliberately excluded until their dedicated policy boundary exists.

**COMPLETED INITIAL C3 CANDIDATE-REVIEW SLICE:** Core can deterministically render validated ordinary candidates with their bounded details and an explicit untrusted/non-staged warning. This remains a presentation seam only: no provider, session candidate queue, staging action, or event-log write was added.

**COMPLETED INITIAL C3 EXPLICIT-CANDIDATE-STAGING SLICE:** An active turn may now stage exactly one caller-selected, already validated ordinary candidate through its normal session-local transaction. The helper has no selection policy and cannot access a provider, candidate batch, or event log; only the existing explicit commit can persist the resulting draft.

**COMPLETED INITIAL C3 CANDIDATE-INBOX SLICE:** A bounded session-local inbox can hold one validated candidate batch for exactly one adventure workspace and return an exact user/Core-selected `TC-###` candidate without changing it. It remains noncanonical and disconnected from provider calls, prompt context, commands, staging, and persistence; later lifecycle wiring must clear it on mount transitions.

**COMPLETED INITIAL C3 CANDIDATE-INBOX LIFECYCLE SLICE:** `AssistantSession` now has programmatic-only present/select seams for a prevalidated candidate batch on its currently mounted workspace. Mount/unmount transitions clear the inbox with staged turns and recent chat context, preventing cross-adventure reuse. No chat command, provider adapter, prompt injection, automatic selection, staging, or event write was added.

**COMPLETED INITIAL C3 IDEMPOTENT-CANDIDATE-STAGING SLICE:** Staged transactions now retain the originating `TC-###` alongside its draft. Repeating selection of the same candidate is a no-op, while removing that draft releases it for a deliberate restage. This protects future retry/UI behavior without changing manual-draft semantics or creating a write path.

**COMPLETED INITIAL C3 CANDIDATE-STALE-GUARD SLICE:** Candidate inboxes now record the authoritative event count they were generated against. Exact selection fails closed if that count changed after an intervening story write, preventing stale generated proposals from being staged against a newer world state. This is still provider-free and noncanonical.

**COMPLETED INITIAL C3 EXPLICIT-CANDIDATE COMMAND SLICE:** Exact `adventure turn candidates` displays the bounded untrusted inbox, while `adventure turn stage candidate <TC-###>` stages one selected ordinary candidate into an active transaction. Review is read-only and staging is idempotent; neither creates candidates, calls a provider, or persists anything before normal commit.

**COMPLETED INITIAL C3 GENERATION-REQUEST SLICE:** `AdventureTurnGenerationRequest` renders bounded authoritative adventure context and explicitly untrusted user/narrator text into a closed ordinary-candidate JSON contract for a future task-specific provider. It has no provider call, output parsing, inbox, staging, or write authority.

**COMPLETED INITIAL C3 TASK-PROVIDER ADAPTER SLICE:** A dormant injected chat-provider adapter can explicitly submit the bounded generation request and accept only strict JSON before the separate ordinary-candidate validator runs. It has no session, command, prompt, inbox, staging, or event-log integration; provider and malformed-output failures yield no partial candidate batch.

**COMPLETED INITIAL C3 SHARED-POLICY SLICE:** The ordinary generated-event
whitelist is now one immutable Core policy constant shared by candidate parsing,
generation prompt construction, and fixtures. It remains narrower than the
event-log write set; adding a generated type requires an explicit policy change.

**COMPLETED INITIAL C3 NO-CHANGE SLICE:** A strict ordinary-candidate envelope
may explicitly contain zero candidates. Core renders that as a bounded,
untrusted no-durable-change outcome; it cannot stage or commit an event.

**COMPLETED INITIAL C3 ORCHESTRATION-EVAL SLICE:** A deterministic temporary-
workspace benchmark now verifies ordinary candidate generation/validation,
explicit staging and append-only commit, explicit no-change output, invalid
envelope rejection, and stale-origin rejection as separately bounded outcomes.

### Current dependency-ordered execution path

The older numbered stages above preserve the project history. Active implementation now follows this dependency order so an adventure-import prototype and a read-only Murr apartment arrive early without bypassing safety boundaries:

1. **Finish adventure integrity:** apply active-event semantics to relationship, character-knowledge, and resource projections; add explicit correction/retraction inspection and a later Core-owned correction writer; preserve every original event for audit.
2. **Finish replay/restart fundamentals:** define established-premise restart, fresh restart, checkpoint/branch isolation, and deterministic recovery benchmarks before automated narration changes state.
3. **Bind one explicit story loop:** one loaded adventure + active persona/party member + roleplay session + branch. Persona/NPC initiative remains proposal-only until Core validates its typed consequences.
4. **Deliver reviewed adventure import before automatic extraction:** route large documents, `details.md`, and exported conversations through canonical prechunking, provenance, review, and an explicit adventure-scoped handoff. This creates a usable “import, load, and continue” path without silently producing personal memories or trusting model prose as state.
5. **COMPLETED INITIAL H0/H1 SLICE:** A versioned, authenticated, conversation-aware `ResidentSnapshot` now composes only bounded public persona/runtime/provider/adventure/roleplay/staging/candidate summaries plus passive aggregate host metrics under the normal application lock. The initial host sampler reports logical CPU count, available/total RAM where exposed, and workspace-disk capacity without subprocesses; GPU/VRAM/temperature remain honestly unavailable pending an explicit adapter. A generic asset-slot mapper derives presentation states such as idle, thinking, reviewing, and adventuring without inspecting prompts or loading assets. `/starfur/apartment` is a dependency-free static, read-only local prototype shell; it embeds no token/runtime data and obtains the snapshot only after the local user supplies a token in browser memory. The fixed human-authored `Assets/Murr/Murr_S_Idle.png` placeholder is exposed through one allowlisted art route, not a generic filesystem server. Explicit persona-local ResidentAction controls and authored apartment cues remain available with no provider, while the provider card still reports unavailability honestly. Remaining: validated human-authored sprite/theme package slots, richer deterministic action scheduling, and a richer desktop client.
6. **Add provider registry and measured routing, then the tool/permission engine:** task/profile configuration becomes actual provider selection only after benchmarks; filesystem, screen, process, network, and external services remain separately permissioned.

**COMPLETED INITIAL PROVIDER-ROUTE PLANNING SLICE:** A pure `TaskRoutePlanner`
can now evaluate declarative task profiles and caller-supplied bounded provider
statuses into an acyclic inspectable primary/fallback plan. It neither probes,
constructs, nor calls providers and cannot access prompts, memory, adventures,
permissions, or execution. Runtime diagnostics expose a passive preview of
configured task routes from existing provider health/lifecycle observations.

**COMPLETED INITIAL ROUTE-CAPABILITY SLICE:** Core now maps provider-facing
task IDs through one explicit capability table (`chat`, `vision`, or
`image_generation`). Unknown/provider-free work cannot be guessed into a route
merely because a task profile exists.

**COMPLETED INITIAL ROUTED-CHAT EXECUTOR SLICE:** Explicit Core-injected chat
adapters can be registered by stable ID and one preplanned route can invoke one
selected adapter. It does not construct providers from config, probe, retry,
silently switch after a failure, persist telemetry, or yet alter the existing
session provider path; that integration requires its own smoke-tested slice.

**COMPLETED INITIAL SESSION-ROUTING SLICE:** Normal assistant chat, proposal
extraction, and explicit generated-adventure-turn calls now plan before one
provider request through the injected adapter registry. An explicitly
unavailable provider fails before receiving a request; a request failure never
silently retries or switches providers. This preserves the present one-adapter
runtime and leaves document annotation on its separately bounded current path
until annotation-specific routing and benchmarks are ready.
7. **Add vision, image, and speech adapters:** one-shot vision first; then image generation, STT, TTS, voice-activity detection, transcript confidence, and interruption/barge-in behavior behind the same provider/permission boundaries.
8. **Harden resident continuity before polish/release:** durable persona-local continuity, zero-provider resident behavior, deterministic `ResidentAction` presentation, restart/recovery, package validation, and Workshop/Steam release engineering.

NPC and party-member memory are not arbitrary hidden chat buffers. Their normal context is a bounded derived view of authoritative adventure events, their own character-knowledge facts, allowed relationship facts, and permitted public resources. Any later participant-local salience cache must be inspectable, adventure-scoped, rebuildable or provenance-backed, and never silently become shared user memory.

**ADVENTURE-OWNED NARRATIVE MEMORY (PLANNED):** Adventure continuity must use a separate automatically maintained `adventure:<id>` event/state store rather than the conservative shared assistant-memory proposal workflow. A bounded salience layer may persist meaningful choices, discoveries, promises, lies, relationship changes, character knowledge, inventory, locations, unresolved hooks, and other continuity-critical state without interrupting immersion. Decorative prose and ordinary dialogue should not become durable events. Adventure state remains isolated from shared user memory, lore memory, and persona self-memory; it is replayable, inspectable, resettable, size-bounded, and never silently promoted to real-world memory. Importing an external `details.md` file remains a reviewed document/context path until this authoritative event/state layer exists.

1. **COMPLETED INITIAL EXACT-CONTROL SLICE:** Add deterministic Core controls for resume, pause, and end; `end story now` cannot be delayed or reinterpreted by the narrator. Remaining: explicit start that binds workspace + roleplay, archive/reset workflows, natural-language resume/load phrases, ambiguity handling, and documented equivalents beyond the initial exact alias. Natural-language story-intent detection may later assist discovery but must never silently create a new world when the user requested a resume.
2. **COMPLETED INITIAL READ-ONLY SLICE:** Mount bounded, validated summary-only adventure event context without merging it into user memory, lore memory, or persona self-memory. A resident persona may narrate inside the world while retaining a separate shared-reality identity and relationship with the user. Remaining: derived state, event-authoring workflow, and replay/spine policy.
3. Make a validated, append-only adventure event log authoritative. Record meaningful choices, discoveries, promises, lies, relationship changes, emotional transitions, state changes, and unresolved hooks as events. Derived state and snapshots may accelerate loading but must be rebuildable from events.
4. **COMPLETED INITIAL SPINE SELECTION:** Rebuild a deterministic bounded chronology from the authoritative event log, retaining initial setup, latest high-value continuity categories, and recency. Remaining: branches, richer derived state, user-facing reset/restart semantics, and narrative contradiction/replay benchmarks. Stories should eventually replay without requiring identical prose: the model may regenerate scene wording and connective details around established events, but must not silently erase or contradict them.
5. Reuse the relationship and emotion subsystems inside the adventure namespace. NPC relationships are scoped to the adventure and character pair; repeated lies, broken promises, help, betrayal, repair, and elapsed time update bounded trust, familiarity, suspicion, affection, concern, or resentment through evidence-backed events. Adventure emotions are temporary derived state and influence presentation without becoming permanent facts on every memory.
6. Represent character knowledge, beliefs, lies, and uncertainty per character. An NPC's mistaken belief is not world truth, and discovered information must be recorded as a knowledge event before it changes that character's behavior.
7. End or interrupt story turns transactionally: commit only completed validated events, never partial generated narration or unverified inferred state; unmount adventure-only recent context when returning to normal companion mode.
8. Add replay, branching, long-session persistence, relationship consistency, event-recovery, and cross-boundary regression benchmarks before treating the subsystem as production-ready. Shared-reality memories such as “Roger enjoyed Quiet Ember” may enter normal memory only through ordinary assistant proposal and approval rules.

#### Persistent adventure simulation (future)

Adventures may eventually continue bounded, deterministic activity while the user is away. The language model must not
simulate every elapsed minute. Core simulation logic advances approved activities, resources, timers, and state, then
wakes a provider only for meaningful decisions, novel events, relationship interpretation, reflection, or significant
narration. Simulation results become structured evidence first; the active persona presents them later.

Keep these layers distinct: transcript (what was narrated), an append-only canonical event log (what happened),
authoritative current state (money, inventory, health, location, activity, resources, equipment, and world flags),
derived memory (salient history), and optional rebuildable snapshots. Volatile state must never be reconstructed from
semantic memory retrieval or stale recalled facts. Simulation must use explicit time boundaries, resource limits,
reproducible seeds/manifests, pause/resume/recovery behavior, and transactional commits that never persist partial
narration or unverified inferred state. Activity selection may use persona interests, energy, mood, skills, goals,
resources, relationship context, and repetition penalties, but formulas remain Core-owned, inspectable, and permissioned.
Events stay inside `adventure:<id>` and cannot silently become real-world user memories or persona claims. On return,
Core filters event salience before asking the persona for a concise recap; exact state remains available through
structured inspection. A later apartment surface may show location, activity, and artifacts while resident and
adventure state remain separate. Add simulation, offline-catch-up, recap, and boundary benchmarks before production.

### Stage 6 - Tools, perception, and resident environment

#### Synchronized media companionship (future)

Support an explicit, opt-in `MediaSession` for watching a movie, episode, or
other time-based media with the active persona. Prefer player/browser metadata,
OS media-session information, subtitle timing, or a dedicated integration to
identify the work and playback position; vision should be an occasional fallback
verifier rather than continuous surveillance. Core owns the verified timestamp
and spoiler boundary, exposing only media events that have already occurred to a
provider or persona. Pause, seek, rewind, skip, uncertain identity, and provider
failure must fail safely and quietly. Persona initiative determines whether to
remain silent, animate, or make an occasional comment. Apartment presentation
may expose a bounded `watching_media` activity, but cannot infer content or
mutate canonical state.

Implement this as small vertical slices: a title/position fixture, spoiler-safe
timeline projection, pause/seek handling, resident activity cues, metadata
integration, optional vision verification, and finally explicit user-approved
shared-experience memory. Keep it separate from adventure history; an adventure
may later consume the same bounded media-session context.

#### Synchronized reading companionship (future)

Add an explicit, opt-in `ReadingSession` for reading a novel, ebook, PDF, or
browser document alongside the active persona. Prefer reader/browser metadata,
accessibility text, DOM anchors, page/scroll position, and selections; use vision
or OCR only as a fallback. Core keeps the source document stable and indexed and
exposes only the current passage plus bounded read-so-far continuity and a
spoiler boundary. It must not reprocess the entire book on every page turn.

Each book should have an isolated `reading:<book-id>` persona notebook for
bounded plot/character notes, themes, reactions, questions, continuity
observations, and prior comments. A narrowly configured activity policy may let
Core automatically accept low-risk book-local persona notes without interrupting
the user; this is not model self-approval and cannot create user facts, alter
real-world relationships, grant permissions, or escape the book namespace.
User-approved shared-experience memories may record that the user and persona
read a work together. Initiative and quiet-mode rules decide whether a page turn
gets silence, an expression/animation, or an occasional comment.

Implement as small vertical slices: reader-neutral identity/position fixture,
bounded passage projection, page/scroll/selection events, persona reading
notebook, quiet/commentary behavior, browser or ebook bridge, optional vision/OCR
fallback, and explicit cross-book preference/recommendation support. Keep reader
state separate from canonical manuscript truth, adventure history, and
unrestricted assistant memory.

1. Add structured tool registry and permission engine with allow-once, always-allow, deny, and confirmation-required policies.
2. **IN PROGRESS:** Add document intake for large external files: OpenWebUI/API upload -> bounded validation -> Prechunker/Mr. Chonker chunking -> optional annotation/indexing -> provenance-aware retrieval. **COMPLETED INITIAL VERTICAL SLICE:** bounded text preparation, provider-backed annotation, re-annotation-stable candidate provenance, explicit single/batch review handoff, normal proposal approval, deterministic retrieval of approved document memories with safe origin labels, read-only review-scoped lexical source-context packets, explicit API chat-time source-context binding, and an optional OpenWebUI Filter artifact for one authenticated UTF-8 text upload per turn. The Filter disables OpenWebUI's built-in RAG only for the attached StarFur model, routes the source through StarFur annotation/review, binds only the resulting review ID to chat, and exposes exact Core-owned review/approve/reject commands for its short-lived candidates. Remaining: richer visual review controls, canonical manuscript-path integration, multi-file/non-text ingestion, and semantic indexing. Integrate or intercept external UI RAG so uploaded source text remains distinct from the user request, StarFur command routing remains reliable, and the canonical chunk/annotation/provenance pipeline owns document context before release. Do not inject entire documents into every assistant prompt; retain source identity, chunk identity, and domain.

   **COMPLETED STRUCTURAL PRECHUNK SLICE:** Added deterministic, model-free document profiles before external annotation. Legacy `assistant_note` behavior remains stable; `technical_document` and `adventure_state` preserve heading/state boundaries before bounded chunking, and the OpenWebUI bridge can safely select `auto` from explicit structure. This improves large narrative-document throughput without changing review, proposal approval, shared memory, or source-context boundaries. Remaining: selective/query-driven annotation, asynchronous or pollable processing, multi-file intake, and semantic document indexing.

   **COMPLETED TERMINAL OBSERVABILITY SLICE:** Terminal callers may opt into a bounded completed-chunk progress bar while annotation runs, followed by the normal final review JSON. The standard JSON endpoint remains unchanged for OpenWebUI and future clients; later asynchronous/pollable or structured UI progress must be a separate transport contract.

   **COMPLETED SMALL-MODEL RELIABILITY SLICE:** Document annotation now uses a bounded content-validation sequence when an explicit fallback profile is configured: two primary-model attempts followed by one declared fallback-model attempt. The stock local profile is Qwen3 8B primary-only after the first checked-in quality fixture showed Phi-4 Mini could return schema-valid empty results with zero expected-fact recall. Phi remains an explicit benchmark candidate rather than an automatic intake fallback until more public quality evidence supports a bounded role. Without a configured fallback, all three attempts stay on the configured primary. Only invalid/empty/model-malformed outputs consume this sequence; valid empty results end normally, no retry is unbounded, and all candidates remain review-only. The response exposes bounded model labels/attempt counts and fallback use, never raw model output. Remaining: repeated model-quality benchmarks, per-model latency comparison, and a separately benchmarked multi-provider routing path for annotation.
   **COMPLETED ANNOTATION-LEDGER SLICE:** Explicit local annotation observations can now be appended to the existing privacy-bounded experiment ledger with only chunk/candidate/failure counts, model labels, attempt counts, optional latency, and fallback use. Source text, review IDs, candidate content, prompts, and raw provider outputs are excluded. This measures transport/schema reliability; reviewed fact quality remains a separate benchmark family.
   **COMPLETED ANNOTATION-COMPARISON SLICE:** The local CLI can now produce a read-only aggregate comparison of recorded annotation observations by primary model, including pass rate, failed chunks, candidate count, bounded attempts/fallback use, configured fallback labels, and optional mean latency. It remains a reliability report only; it does not reopen source documents or score extraction quality.
   **COMPLETED ANNOTATION-TIMING SLICE:** Successful or partially failed live annotation responses now expose only end-to-end extraction elapsed time alongside existing bounded model/attempt metadata. The timer covers candidate extraction/validation after document preparation and never retains source text, prompts, provider output, or per-chunk timings.
   **COMPLETED ANNOTATION-QUALITY CONTRACT SLICE:** Checked-in model-comparison contracts can now score a saved standard annotation response by expected fact recall, candidate precision, false positives, and missed targets. The scorer and ledger keep aggregate counts only; it never records source text, candidate wording, review IDs, prompts, or raw provider output. Remaining: more diverse public fixtures, repeated runs, and a threshold policy based on accumulated results.
   **COMPLETED ANNOTATION-QUALITY REPORT SLICE:** The read-only annotation report now renders reliability and extraction-quality aggregates separately by primary model. This makes valid-empty responses visible as reliability successes but quality-recall failures rather than conflating transport/schema conformance with useful fact extraction.
   **COMPLETED PUBLIC ANNOTATION-RUNNER SLICE:** An explicit CLI runner now evaluates one selected installed model against a checked-in public annotation fixture and records only aggregate quality/reliability counts plus elapsed time. It bypasses reviews and persistence entirely; it is benchmarking infrastructure, not an alternate intake route.
3. Add one-shot VisionProvider screen/window/region/image/PDF inspection.
4. Add image, speech, and media provider interfaces and explicit capability routing.
5. Build the low-resource apartment as a state visualization: workbench for active projects, bookshelf for installed models, newspaper for feeds, calendar for schedule, window for permissioned desktop state, and frames for artwork.
6. Keep generated/procedural placeholder assets replaceable by commissioned art through stable asset IDs.
7. Add an opt-in idle adventure scene display after structured adventure state and image generation exist. When permissioned user inactivity exceeds a configurable delay and an adventure remains active, Core may summarize the current structured scene and generate a cached illustrative image for an apartment frame/overlay. It must debounce generation, respect privacy/resource modes, react immediately to user activity, and never treat the image as canon or invoke an LLM for every idle tick.

8. **PLANNED:** Define a portable, data-only adventure package for sharing and Steam Workshop distribution. A package should be able to contain a validated manifest plus an entry `details.md`/structured state file and optionally an imported conversation or transcript, with room for bounded assets later. Import must route every document through the canonical prechunk/annotation/provenance pipeline, preserve adventure namespace boundaries, and require explicit review or adventure-scoped handoff rather than silently creating personal memories. Packages must be versioned, replayable, portable across compatible Core versions, and safe to reject or partially import when files, schemas, or assets are invalid; no package may execute code or imply permissions.

### Stage 7 - Resident intelligence and Crown of Claws writing mode

1. Add scheduler/watchers with explicit permissions and bounded resource targets.
2. Add workshop packaging for personas, interests, skills, apartments, voices, animation, and tools.
   **ADVENTURE PACKAGE SUBSLICE:** Prefer a small `.starfur-adventure` archive (manifest + `details.md` or equivalent structured state, optional downloaded conversation/transcript, optional assets) as the first useful Workshop unit. Treat Workshop as a distribution adapter over the same local validator and adventure importer; installed content remains immutable while event/state history and user-local memory remain separate save data.
3. Add mandatory manuscript POV/perspective metadata for the three main characters, Murr, Quiet Accord, and third-party viewpoints.
4. Add character knowledge-state, revelation, timeline, contradiction, and continuity analysis.
5. Add writing-partner mode after assistant-mode and shared-service validation.

## Capability provider interfaces

```python
class ChatProvider(Protocol):
    def complete(self, messages, *, model=None, options=None, stream=False): ...

class VisionProvider(Protocol):
    def inspect(self, image, *, prompt=None, model=None, options=None): ...

class ImageProvider(Protocol):
    def generate(self, prompt, *, model=None, options=None): ...

class SpeechProvider(Protocol):
    def transcribe(self, audio, *, model=None, options=None): ...
```

Ollama is the current chat/embedding implementation. LM Studio, hosted APIs, llama.cpp, ComfyUI, Stable Diffusion, TTS, and STT should be adapters rather than special cases in the core.

## Evaluation, observability, and research instrumentation

The full instrumentation ledger and cross-system comparison reports mature after the provider registry and routing layer are functional and stable; the benchmark foundation above begins earlier and feeds this stage. Instrumentation exists to answer engineering and research questions, not to collect data for its own sake.

### Useful measurements

- routing classification accuracy, route confidence, selected capability/provider/model, fallback reason, and route stability;
- prompt and completion token estimates, time to first token, provider latency, queue/load/unload time, and total turn latency;
- CPU, RAM, VRAM, temperature, and energy estimates when available;
- success, timeout, interruption, transport error, empty-output, and retry rates;
- retrieval precision/recall, irrelevant-result rate, grounding correctness, introspection correctness, and context size;
- proposal precision, approval/rejection rate, duplicate rate, reinforcement behavior, and user-correction frequency;
- learning-task completion, compile/test success, skill-confidence changes, and sandbox resource usage;
- answer-quality and persona-consistency evaluations from deterministic benchmark cases and human review.

### Experiment ledger

**FIRST SLICE COMPLETED:** An explicit local JSONL ledger records privacy-bounded retrieval-fixture benchmark results with versioned manifests, run/commit/model/hardware metadata when supplied, expected/returned memory IDs, retrieval scores/reasons, pass/fail outcome, and aggregate metrics. It never records raw prompts or responses; fixture evaluation remains temporary-DB-only.

**ADVENTURE-TURN RESULT SLICE COMPLETED:** The same bounded ledger accepts adventure-turn benchmark cases and separates generation completion, candidate validation, Core-use/staging, and canonical-commit outcomes. It stores only bounded statuses/counts and rates, never turn text, provider payloads, or narrative prose.

Adventure-turn failures use a closed operational category set (empty, non-JSON,
oversized, invalid-envelope, stale-origin, unavailable-profile, or provider
failure) so permanent regressions remain comparable without retaining a model
response.

Extend this into an append-only local experiment ledger with versioned structured events and aggregate reports. Every run should identify an experiment/run ID, benchmark case, configuration and policy hashes, provider/model versions, hardware profile, random seed, timestamps, outcome, and failure category. Store raw prompts/responses only when explicitly enabled and privacy-approved; aggregate metrics must remain useful without retaining unrestricted conversation content.

Required tools include deterministic benchmark suites, router decision traces, reproducible run manifests, comparison reports, and exportable research summaries. Metrics must be bounded, privacy-aware, and tied to a decision or hypothesis. This instrumentation should be reusable by routing, retrieval, Persona Runtime, autonomous learning, and the discussion sandbox.
## Future research

- Temporal and multi-hop associations after one-hop retrieval is benchmarked.
- State decay and emotional inference with explicit explanations.
- Retrieval compression only after long-duration prompt metrics justify it.
- Autonomous learning and replayable companion regression benchmarks.
- Proactive assistance and scheduling with permission.
- Native media generation and perception.
- Procedural generated adventures with deterministic world generation, persona-driven meaningful decisions, persistent event/state/replay support, and generated/composited visuals of the active scene. This is post-prototype work: authoritative simulation and replay must work before visuals become part of the adventure loop.
- Idle adventure scene rendering in the apartment: a permissioned, cached “Murr is currently…” display driven by structured adventure state and stable asset/style IDs, with explicit hide/freeze/refresh controls.
- Licensing, workshop distribution, and companion packaging.

## End state

StarFur is an operating environment for persistent AI companions. Users do not open a chatbot; they sit down at a computer where an intelligent resident already lives, remembers responsibly, develops verified interests and skills, responds through a coherent evolving personality, and remains transparent and user-controlled.
