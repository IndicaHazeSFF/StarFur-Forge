# StarFur Forge Roadmap v4

**Status:** Resident Intelligence Platform with an executable Persona Runtime
**Last updated:** 2026-08-03

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

1. Add deterministic story-mode controls for starting, resuming, pausing, archiving, resetting, and ending an adventure. Natural-language story-intent detection may assist discovery, but Core-owned commands—especially `end story now` and its documented equivalents—always take precedence and cannot be delayed or reinterpreted by the narrator. Support explicit natural-language entry and resume phrases such as `Murr, let's roleplay`, `Murr, let's go on an adventure`, `Murr, resume the adventure <title>`, and `Murr, load roleplay <title>`. Resolve titles through the global adventure registry; ask for clarification on ambiguous matches and never silently create a new world when the user requested a resume.
2. Mount adventure state into context without merging it into user memory, lore memory, or persona self-memory. A resident persona may narrate inside the world while retaining a separate shared-reality identity and relationship with the user.
3. Make a validated, append-only adventure event log authoritative. Record meaningful choices, discoveries, promises, lies, relationship changes, emotional transitions, state changes, and unresolved hooks as events. Derived state and snapshots may accelerate loading but must be rebuildable from events.
4. Make stories replayable without requiring identical prose. A restart or resume should preserve an authored/replay spine: established key events, discovered facts, character knowledge and uncertainty, important choices, relationship milestones, active conflicts, promises, and unresolved hooks. The model may regenerate scene wording and connective details around that spine, but must not silently erase or contradict established events.
5. Reuse the relationship and emotion subsystems inside the adventure namespace. NPC relationships are scoped to the adventure and character pair; repeated lies, broken promises, help, betrayal, repair, and elapsed time update bounded trust, familiarity, suspicion, affection, concern, or resentment through evidence-backed events. Adventure emotions are temporary derived state and influence presentation without becoming permanent facts on every memory.
6. Represent character knowledge, beliefs, lies, and uncertainty per character. An NPC's mistaken belief is not world truth, and discovered information must be recorded as a knowledge event before it changes that character's behavior.
7. End or interrupt story turns transactionally: commit only completed validated events, never partial generated narration or unverified inferred state; unmount adventure-only recent context when returning to normal companion mode.
8. Add replay, branching, long-session persistence, relationship consistency, event-recovery, and cross-boundary regression benchmarks before treating the subsystem as production-ready. Shared-reality memories such as “Roger enjoyed Quiet Ember” may enter normal memory only through ordinary assistant proposal and approval rules.

### Stage 6 - Tools, perception, and resident environment

1. Add structured tool registry and permission engine with allow-once, always-allow, deny, and confirmation-required policies.
2. **IN PROGRESS:** Add document intake for large external files: OpenWebUI/API upload -> bounded validation -> Prechunker/Mr. Chonker chunking -> optional annotation/indexing -> provenance-aware retrieval. **COMPLETED INITIAL VERTICAL SLICE:** bounded text preparation, provider-backed annotation, re-annotation-stable candidate provenance, explicit single/batch review handoff, normal proposal approval, deterministic retrieval of approved document memories with safe origin labels, read-only review-scoped lexical source-context packets, explicit API chat-time source-context binding, and an optional OpenWebUI Filter artifact for one authenticated UTF-8 text upload per turn. The Filter disables OpenWebUI's built-in RAG only for the attached StarFur model, routes the source through StarFur annotation/review, binds only the resulting review ID to chat, and exposes exact Core-owned review/approve/reject commands for its short-lived candidates. Remaining: richer visual review controls, canonical manuscript-path integration, multi-file/non-text ingestion, and semantic indexing. Integrate or intercept external UI RAG so uploaded source text remains distinct from the user request, StarFur command routing remains reliable, and the canonical chunk/annotation/provenance pipeline owns document context before release. Do not inject entire documents into every assistant prompt; retain source identity, chunk identity, and domain.
3. Add one-shot VisionProvider screen/window/region/image/PDF inspection.
4. Add image, speech, and media provider interfaces and explicit capability routing.
5. Build the low-resource apartment as a state visualization: workbench for active projects, bookshelf for installed models, newspaper for feeds, calendar for schedule, window for permissioned desktop state, and frames for artwork.
6. Keep generated/procedural placeholder assets replaceable by commissioned art through stable asset IDs.

### Stage 7 - Resident intelligence and Crown of Claws writing mode

1. Add scheduler/watchers with explicit permissions and bounded resource targets.
2. Add workshop packaging for personas, interests, skills, apartments, voices, animation, and tools.
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

Extend this into an append-only local experiment ledger with versioned structured events and aggregate reports. Every run should identify an experiment/run ID, benchmark case, configuration and policy hashes, provider/model versions, hardware profile, random seed, timestamps, outcome, and failure category. Store raw prompts/responses only when explicitly enabled and privacy-approved; aggregate metrics must remain useful without retaining unrestricted conversation content.

Required tools include deterministic benchmark suites, router decision traces, reproducible run manifests, comparison reports, and exportable research summaries. Metrics must be bounded, privacy-aware, and tied to a decision or hypothesis. This instrumentation should be reusable by routing, retrieval, Persona Runtime, autonomous learning, and the discussion sandbox.
## Future research

- Temporal and multi-hop associations after one-hop retrieval is benchmarked.
- State decay and emotional inference with explicit explanations.
- Retrieval compression only after long-duration prompt metrics justify it.
- Autonomous learning and replayable companion regression benchmarks.
- Proactive assistance and scheduling with permission.
- Native media generation and perception.
- Licensing, workshop distribution, and companion packaging.

## End state

StarFur is an operating environment for persistent AI companions. Users do not open a chatbot; they sit down at a computer where an intelligent resident already lives, remembers responsibly, develops verified interests and skills, responds through a coherent evolving personality, and remains transparent and user-controlled.
