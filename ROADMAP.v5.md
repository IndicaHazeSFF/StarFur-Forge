# StarFur Forge Roadmap v5 — Core Continuity, Adventures, and Resident Experience

**Revision:** 2026-08-26  
**Status:** proposed successor to `ROADMAP.md` and `ROADMAP.v4.md`; it becomes authoritative only when explicitly adopted.  
**Product target:** a local-first resident companion platform with persistent adventures, replaceable intelligence providers, a lightweight apartment, and safe declarative Workshop content.

## How to read this roadmap

`ROADMAP.md` remains the current authoritative roadmap until this proposal is adopted. `ROADMAP.v4.md` is preserved as historical design context. Status claims below are based on current source and tests; intended architecture is labeled as such. A completed primitive is not the same as a completed product loop.

Status labels:

- **COMPLETED:** implemented and covered by focused tests.
- **FOUNDATION:** a bounded primitive exists, but its end-to-end product loop is incomplete.
- **ACTIVE:** next dependency-gated implementation work.
- **LATER:** ordered work with known prerequisites.
- **RESEARCH:** valuable direction that must not become an implicit product promise.

## Mission and product identity

StarFur Forge is the continuity system around replaceable models: inspectable memory, declarative personas, structured adventures, permissions, tools, perception, and presentation surfaces. It is game-adjacent rather than a general-purpose game engine. Core owns truth, permissions, state transitions, and continuity; providers supply untrusted language, analysis, or media results.

The full resident experience is a lightweight apartment/dashboard where a companion can visibly live, idle, work, sleep, react to presence, display activity, and preserve identity independently of the currently loaded model. The initial commercial target is a Steam application with safe local packages and Workshop distribution.

## Non-negotiable architecture

1. Core is authoritative for memory, adventure state, permissions, commands, package validation, and protected values.
2. Models and specialist providers are untrusted. Their output becomes a proposal or typed candidate only after Core validation.
3. Complete canonical state is separate from bounded model/UI projections. Context limits must never destroy or redefine state.
4. CLI, OpenWebUI, TUI, apartment, dashboard, phone, and Steam clients use shared application services and read models; they do not parse prose to reconstruct truth.
5. Persona and adventure packages are declarative data by default. Package content cannot grant permissions or execute code.
6. Shared user memory, persona-local continuity, roleplay scope, lore, and `adventure:<id>` state remain separate namespaces.
7. Every automatic mutation has bounded provenance, validation, policy, outcome, and correction/recovery semantics.
8. Benchmarks measure behavioral claims; unit tests alone do not establish model quality.
9. Instructions are advisory. Anything private, numeric, provenance-sensitive, or permission-sensitive is sanitized before a model sees it.
10. Zero-provider operation is a release requirement for resident identity/state, not a promise of open-ended reasoning without a provider.

## Current position

The repository is in **Stage 5A / C3 foundation**. Implemented foundations include domain-separated assistant memory and retrieval, reviewed document intake, persona runtime and visibility policy, provider/application boundaries, adventure registries and append-only event logs, recovery/locking/idempotent writes, complete structured projections with bounded replay/context selectors, resources, relationships, character knowledge, checkpoints/branches, correction/retraction, mixed explicit turn staging, adventure import review/mapping, candidate inbox/review/staging primitives, benchmark manifests, retrieval evaluation, and a privacy-bounded experiment ledger.

The next product loop is not a router or an apartment animation system. It is a safe model-backed adventure-turn coordinator: Core captures a completed turn, constructs sanitized context, invokes one task provider, validates strict candidates, checks that the world did not change during generation, presents candidates for explicit selection, and reuses the existing transaction for staging/commit.

## Ownership boundaries

| Layer | Owns | Must not own |
|---|---|---|
| Core/application | canonical memory/adventure state, projections, permissions, command precedence, route policy, package validation, read models | persona prose or provider-specific authority |
| Persona package/runtime | identity, bounded traits, declared interests, presentation defaults, asset references | Core memory truth, permissions, credentials, executable behavior |
| Adventure workspace | isolated event history, scenario catalog, state/relationship/knowledge/resource projections, replay | shared personal memory or real-world relationships |
| Provider adapter | protocol translation and bounded health/model metadata | commands, state writes, memory approval, permissions, hidden routing |
| Router | resolve/execute an eligible provider for a typed task and return bounded outcome | staging, committing, retrieval policy, persona selection, UI state |
| Presentation client | input, rendering, accessibility, confirmation surfaces | database mutation or canonical reconstruction |
| Workshop installer | quarantine, manifest validation, compatibility, safe extraction | trusting paths/scripts or granting permissions |

## Stage A — Adventure integrity and authoritative projections (FOUNDATION; mostly implemented)

### A1. Complete projections versus bounded context — COMPLETED FOUNDATION

`pipeline/adventure_state.py`, `adventure_relationship.py`, `adventure_knowledge.py`, and `adventure_resource_state.py` rebuild complete latest-value projections from validated active history. Separate selectors bound replay/context/UI output. Tests prove over-limit state survives reload and prompt limits.

### A2. Event-log integrity and recovery — FOUNDATION with core slices completed

The event log is append-only, validates every stored line and sequence, supports schema-v1/v2 compatibility, request-ID idempotency, OS advisory write locking, pending-log recovery, manifest reconciliation, catalog-validated resource events, corrections, retractions, and verified checkpoint prefixes. Remaining work is broader failure injection, registry-orphan reconciliation, and restart/process-boundary coverage.

### A3. Typed mutation envelopes — FOUNDATION

Schema-v2 typed mutation validation exists, while Core continues writing schema-v1-compatible records until migration policy is explicit. Narrative summary/details remain separate from typed state, relationship, knowledge, and resource operations. No provider output may bypass the typed policy.

### A4. Mixed turn transaction — FOUNDATION

`AdventureTurnTransaction` stages ordinary drafts and explicit typed mutations together and commits atomically. Abort, mount changes, and interruption must discard staging. Generated orchestration must never make partial narration canonical.

### A5. Command precedence — COMPLETED FOUNDATION

The reserved `adventure` namespace dispatches exact Core commands and fails closed for malformed forms. It never falls through to model generation, proposal extraction, stale document extensions, or implicit writes.

## Stage B — Generic adventure state (FOUNDATION; continue only as needed by C3)

Scenario packages may declare generic resource catalogs, bounds, visibility, enums, and permitted operations. Values are event-backed and rebuilt through a pure reducer. Public resource context is bounded; hidden values and free-form resource summaries never enter ordinary model prompts. Inventory, currency, health, ammo, and similar names remain package data rather than Core-coded game rules.

Remaining B work: strengthen relationship/knowledge consistency fixtures, restart/branch behavior, and explicit participant projections. Do not expand into a full game engine before the generic contracts are stable.

## Stage C — Safe narrative-to-state loop (ACTIVE)

### C1. Reviewed adventure document import — FOUNDATION

External documents are prepared, prechunked, annotated, reviewed, mapped, and explicitly committed into an isolated adventure. Source/chunk provenance remains auditable; imports are not automatically shared personal memory. Multi-file bundles, asynchronous progress, long-document optimization, and OpenWebUI resilience remain follow-up work.

### C2. Completed-turn source boundary — ACTIVE

Define exactly what qualifies as a completed user/narrator turn. Partial streaming output, arbitrary uploaded text, and model chain-of-thought do not qualify. The source is bounded and labeled untrusted; Core context is separately typed and sanitized.

### C3. Generated ordinary-event candidates — ACTIVE NEXT GATE

Existing primitives:

- `AdventureTurnGenerationRequest` bounds context and source text and renders a closed JSON contract.
- `ChatAdventureTurnCandidateProvider` is an injectable strict-JSON adapter.
- candidate parsing bounds count/fields and excludes typed mutations from the ordinary contract;
- the session-local candidate inbox supports exact inspection, stale-count checking, and explicit staging;
- the transaction commits only through the existing explicit all-or-nothing path.

Before model-backed smoke, complete these gates:

1. Export one shared immutable ordinary-event whitelist for prompt, parser, help, fixtures, and telemetry. Do not let `DRAFT_EVENT_TYPES` silently widen it.
2. Add a raw response-size limit before JSON parsing; reject empty, fenced, prefixed, suffixed, oversized, wrong-version, unknown-field, and over-count output.
3. Carry a Core-generated `generation_id`, adventure ID, and original event-count or event-prefix fingerprint through provider latency. Re-read the authoritative origin before replacing the inbox.
4. Make candidate identity `(generation_id, candidate_id)` so two batches containing `TC-001` cannot collide.
5. Build a typed `AdventureTurnContextView` from Core projections. It must redact hidden resources, numeric relationship meters, raw evidence, and unsanitized document text before provider assembly.
6. Add one presentation-neutral coordinator: capture source, build context, resolve task, call provider, validate, check origin, replace inbox, and emit bounded diagnostics. It must not stage or commit.
7. Define retry, interruption, timeout, empty-output, and failed-regeneration semantics. Failed generation creates no write and cannot abort unrelated manual staging.
8. Preserve bounded candidate/task/provider provenance through explicit selection and canonical commit, either on events or an adjacent append-only decision record.

**COMPLETED INITIAL C3 POLICY SLICE:** The ordinary generated-event whitelist is
now one immutable Core policy constant shared by candidate parsing, generation
prompt construction, and fixtures. It remains narrower than the event-log
write set; adding a generated type requires an explicit policy change.

**COMPLETED INITIAL C3 NO-CHANGE SLICE:** A strict ordinary-candidate envelope
may explicitly contain zero candidates. Core renders that as a bounded,
untrusted no-durable-change outcome; it cannot stage or commit an event.

**COMPLETED INITIAL C3 ORCHESTRATION-EVAL SLICE:** A deterministic temporary-
workspace benchmark now verifies ordinary candidate generation/validation,
explicit staging and append-only commit, explicit no-change output, invalid
envelope rejection, and stale-origin rejection as separately bounded outcomes.

### C3 typed proposals — LATER C3 extension

State, relationship, character-knowledge, and resource proposals get separate schemas and policies. They are never added by widening the ordinary parser. Resource proposals validate against the immutable catalog before review/staging. Generated corrections/retractions are separate proposal types and must target an active exact event ID.

### C4 replayable adventure continuity — FOUNDATION / LATER

An adventure remains replayable through authoritative events, key discoveries, state, relationships, character perspectives, unresolved hooks, and scenario definitions while allowing regenerated prose. Full story documents are source material, not canonical events until explicitly mapped/committed. A portable adventure package may contain a manifest plus `details.md`, summary/transcript, and optional assets; imported state and event history remain separate from shared user memory.

## Stage D — Behavioral evaluation (START ALONGSIDE C3)

Benchmarking begins before real-model generated turns and grows continuously. Every run records benchmark version, git commit, architecture fingerprint, provider/model/quantization, context/output budgets, hardware, seed, case, expected/actual bounded result, pass/fail, retrieval/candidate scores, latency/TTFT, and available resource metrics. Raw prompts/responses remain opt-in and privacy-approved only.

First behavioral families:

- candidate JSON validity, precision/recall, false positives, no-event cases, and Core-use success;
- stale-origin, duplicate-batch, retry, interruption, abort, commit, correction, and retraction integrity;
- protected-value/prompt-contamination regressions;
- long-document RAG and annotation quality across chunk counts/sizes;
- persona/instruction adherence and command precedence;
- provider/model portability and small-model scaling with architecture held constant;
- latency, TTFT, load/unload, and resource utilization;
- long-session, LRU, restart, WSL/Windows, and recovery behavior.

**ADVENTURE-TURN LEDGER SLICE COMPLETED:** The privacy-bounded v1 ledger now accepts a bounded adventure-turn case shape and records generation completion, candidate validation, Core-use/staging, and canonical-commit outcomes separately as counts and aggregate rates. It retains no turn text, provider payload, or narrative prose. Preserve sanitized permanent regression fixtures for real failures. Keep retrieval success, candidate extraction success, Core acceptance, canonical projection, and final narration/model-use success as separate outcomes.

Failure records use only a closed operational category set (for example empty,
non-JSON, oversized, invalid-envelope, stale-origin, unavailable-profile, or
provider failures), so real regressions remain comparable without retaining a
provider response.

Later ablations compare full StarFur with retrieval, association, persona runtime, structured adventure state, or other components disabled, plus a raw-model baseline.

## Stage E — Provider registry and measured routing (LATER; after C3 coordinator)

**COMPLETED INITIAL E1 PLANNING SLICE:** `TaskRoutePlanner` now turns
declarative task profiles plus caller-supplied bounded provider-status records
into an acyclic, inspectable route decision. It can identify a primary or
configured fallback as routable, unavailable, unregistered, or
capability-incompatible without probing, constructing, or calling a provider.
It has no access to prompts, memory, adventures, permissions, or execution.
Runtime diagnostics now expose this plan as a passive preview for configured
tasks using only existing provider health/lifecycle observations.

**COMPLETED INITIAL E1 CAPABILITY-POLICY SLICE:** Provider-facing task IDs now
map through one Core-owned capability table (`chat`, `vision`, or
`image_generation`). Unknown and provider-free tasks are not guessed into a
route, preventing a profile alone from widening provider authority.

**COMPLETED INITIAL E1 ADAPTER/EXECUTOR SLICE:** Core can now register already-
constructed chat adapters by stable ID and explicitly execute one preplanned
route. It does not construct adapters from config, probe health, retry after a
failure, silently call a fallback after a request starts, persist telemetry, or
yet replace the existing session provider path. Session integration is the next
separate smoke-tested gate.

**COMPLETED INITIAL E1 SESSION-ROUTING SLICE:** Normal assistant chat,
proposal extraction, and explicit generated-adventure-turn calls now resolve
their bounded route before exactly one request reaches the injected adapter.
An explicitly unavailable provider is rejected before a call, and a submitted
request never silently retries or switches provider. The current runtime still
has one adapter; document annotation retains its separately bounded
single-provider path pending annotation-specific routing benchmarks.

**COMPLETED INITIAL ANNOTATION RELIABILITY SLICE:** The separate document
annotation path now permits one explicit bounded content-validation failover:
two primary attempts followed by one `document_annotation_fallback` attempt.
An explicit privacy-bounded annotation reliability observation can be written to
the existing experiment ledger with chunk/candidate/failure counts, model and
attempt metadata, fallback use, and optional latency only. It never retains
source text, review IDs, candidates, prompts, or raw provider responses.
The local CLI can render a read-only aggregate comparison by primary model from
those ledger observations, exposing only reliability counts, bounded attempt
metadata, fallback configuration/use, and optional latency.
Live annotation responses now provide a single bounded extraction elapsed-time
value for optional ledger recording; structural preparation and raw provider
details remain outside the public result.
Checked-in quality contracts can score saved standard annotation responses by
expected-fact recall, candidate precision, false positives, and missed targets.
Only aggregate counts enter the ledger; source text and candidate wording stay
out of it. More fixtures and an evidence-based acceptance policy remain later work.
The read-only report renders reliability and extraction-quality aggregates
separately so schema-valid empty output cannot be mistaken for useful recall.
An explicit CLI benchmark runner can invoke one selected installed model against
a checked-in public fixture while bypassing reviews and all persistence; it
records aggregate counts and elapsed time only.
The stock local profile is Phi-4 Mini primary and Qwen3 8B fallback. It is not
general provider routing: it neither probes, constructs adapters, persists raw
output, retries indefinitely, nor grants provider output authority before the
existing review boundary.

1. Preserve the existing stable task IDs, beginning with `adventure_turn_generation` and `adventure_turn_mutation_generation`, in declarative profiles; add new IDs only through the same validation boundary.
2. Add a provider/capability registry and pure route planner returning a bounded route decision, profile, budgets, and finite fallback candidates.
3. Keep Core responsible for sanitized input, validation, permissions, candidate selection, staging, commits, memory, and persona continuity.
4. Distinguish configured, unprobed, unavailable, unsupported, failed, degraded, and fallback states.
5. Add loop-free fallback, user overrides, route telemetry, provider portability benchmarks, and model/context budgets.
6. Keep lifecycle reporting descriptive; add model load/unload/residency management only as a separate explicit capability with leases/cancellation/resource observations.

The router chooses and executes a task. It does not become a second application layer or a hidden game director.

## Stage F — Tools and permissions (LATER; routing stable first)

Typed tool registry, explicit scopes, read-only versus mutating tools, confirmation/revocation, bounded audit events, and a genuinely isolated sandbox backend. No provider or Workshop package receives ambient filesystem, network, process, or account authority.

## Stage G — Perception and media (LATER)

Permissioned one-shot screen/window/image/PDF inspection, TTS/STT, image generation, notifications, and presence signals through the provider registry. Media is bounded and provenance-bearing; generated images are noncanonical. Voice uses explicit push-to-talk/always-listen settings, confidence, cancellation, and interruption policy. Continuous surveillance is never the default.

## Stage H — Apartment/dashboard prototype (LATER; read-only first)

### H0. ResidentSnapshot contract — COMPLETED INITIAL SLICE

Compose a versioned presentation-neutral `ResidentSnapshot` under the application/session lock. It should include active persona public state, provider/model lifecycle, capability availability, selected conversation/storage class, loaded adventure summary, authoritative/context counts, roleplay and staging state, candidate-inbox status, and explicit current activity. It must not include prompts, raw evidence, hidden resources, private memory content, relationship subjects, or provider payloads.

**COMPLETED INITIAL SLICE:** `AssistantApplication` exposes the snapshot through authenticated `GET /v1/starfur/resident-snapshot`; the dependency-free local `/starfur/apartment` shell polls it only after the local user supplies a token in browser memory. A pure mapper supplies generic stable visual/animation slots from the public activity, without asset loading or state authority. CLI, OpenWebUI, TUI, dashboard, and future Steam clients consume this read model rather than parsing chat prose. Polling is sufficient for the first shell; event streaming can follow.

### H1. Read-only apartment

Use placeholder/human-authored assets and show identity, activity, provider state, adventure state, safe diagnostics, and permissions. The surface may display or request Core actions but cannot infer or mutate canonical state.

**COMPLETED DECLARATIVE-ASSET FOUNDATION:** Persona packages may now carry a typed manifest of stable visual-state slots and safe package-relative PNG/WebP references. This metadata remains inert until a later installer/package resolver validates and materializes assets; it does not open files, serve paths, or let package content choose activity.

### H2/H3 presentation and ambient features — LATER

Stable sprite/animation slots, accessibility fallbacks, TTS/STT, notifications, and an opt-in cached idle adventure scene display. “Murr is thinking” must come from lifecycle/activity state, not text parsing. An idle image is an illustration, never an event.

## Cross-cutting zero-provider resident runtime (LATER; release gate)

With chat, embedding, vision, image, speech, and hosted providers disabled, Core must still boot the selected persona, restore allowed durable resident state, run deterministic activities/reactions, render human-authored assets, and expose inspection/settings. Open-ended reasoning and generated media are optional enhancements.

**COMPLETED FOUNDATION SLICE:** Core now owns a closed-vocabulary, persona-local, restart-ephemeral `ResidentAction` with exact `resident status`, `resident action <kind>`, and `resident action clear` controls. The read-only apartment reports authored activity labels/cues and keeps explicit actions visible even when no provider is configured, while still reporting provider unavailability honestly. Provider output, ordinary chat, and dashboard rendering cannot create or mutate actions. Remaining: deterministic finite-state/utility/schedule/event behavior for richer actions (animation, expression, movement, duration, priority), durable continuity policy, package assets, and the full no-provider resident test matrix.

## Persona and NPC participation (C3/C4 dependency; then later autonomy)

An active persona becomes an adventure participant only through an explicit adventure-local roster binding. Persona runtime supplies identity/presentation; adventure state supplies role, knowledge, relationships, resources, inventory, initiative, and cooldowns. NPCs do not receive full assistant-memory databases: important facts are event-backed character knowledge/relationship records, with optional bounded rebuildable salience caches.

Add a typed `AdventureParticipantView` keyed by exact adventure and participant IDs. It contains only bounded perspective-appropriate facts. Initiative is disabled or explicitly trigger/action/cooldown limited by default; a provider may propose an action, but Core validates and commits it. Fictional relationships never alter real-world persona relationships.

## Stage I — Workshop and Steam productization (LATER)

Define safe declarative manifests for personas, sprites, apartment themes, and adventures: stable IDs, versions, compatibility, attribution, dependencies, hashes, bounded sizes, asset slots, and migration metadata. Validate archives in quarantine; reject traversal, symlinks, executables, oversized content, incompatible schemas, and implicit remote dependencies. Keep installed package content immutable and user saves/persona continuity/adventure logs separate.

The first Workshop milestone is a distributable adventure archive containing a manifest plus `details.md` and/or a structured summary/transcript, optionally with assets. Import uses the canonical prechunk/annotation/provenance path and never silently writes shared personal memory. Steam is only a distribution/presentation adapter over the same local validator.

Release engineering includes installer/setup, backups/migrations, offline behavior, accessibility, controller input, provider discovery, crash recovery, save choices, package rollback, and clean-install/update tests.

## Stage J — Research and autonomy (RESEARCH)

Permissioned idle work, verified persona learning, deterministic offline adventure simulation, multi-persona Council Mode, procedural/generated adventures, composited visuals, RPG-engine integration, and Crown of Claws continuity tooling remain research until permissions, benchmarks, persistence, and package boundaries pass their gates.

## Dependency-ordered execution sequence

1. C3 safety gates: shared whitelist, response ceiling, generation origin/fingerprint, generation IDs, typed sanitized context.
2. C3 Core coordinator with fake-provider failure and stale-state tests.
3. C3 candidate provenance and bounded behavioral benchmark/ledger adapter.
4. First explicit model-backed ordinary-event smoke; preserve sanitized failures.
5. C3 typed proposal families and replay/correction integration.
6. C4 reviewed import/replay continuity and participant views.
7. H0/H1 read-only `ResidentSnapshot` and apartment shell using placeholder assets.
8. Stage E registry, route planner, finite fallback, and telemetry.
9. Stage F permissions, then Stage G one-shot perception/media/voice.
10. Durable persona-local continuity and zero-provider `ResidentAction` runtime.
11. Workshop/Steam packaging, migrations, accessibility, and release validation.
12. Research autonomy, idle simulation, procedural content, and deeper game integrations.

Every slice updates focused tests and user-facing documentation when its surface changes. A slice is marked complete only after its acceptance tests pass in the authoritative environment and its benchmark/reproducibility implications are recorded.

## End state

StarFur is a trustworthy resident continuity engine, not merely a chatbot embedded in a game. Models, personas, voices, art, interfaces, and fictional worlds can be swapped around stable Core identity and state. Adventures are replayable and distributable; the apartment is an honest read-only view before it becomes interactive; providers improve capability without becoming authority; and small-model claims are supported by reproducible evidence.
