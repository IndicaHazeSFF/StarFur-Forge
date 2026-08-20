# StarFur Forge Roadmap v4 — Expanded Successor Proposal

**Status:** comparison document; not yet authoritative  
**Baseline reviewed:** `ROADMAP.md` and repository state on 2026-08-18  
**Product target:** local-first Resident Intelligence Platform with a Steam-ready companion application and declarative Workshop packages

This document does not replace `ROADMAP.md`. Although the baseline already calls itself v4, this file is the proposed expanded successor requested for comparison. Implemented status is based on current source and tests; roadmap language is treated as intent when the two disagree.

## Status legend

- **COMPLETED:** implemented and represented by focused tests in the current repository.
- **FOUNDATION:** a deliberately narrow primitive exists; product behavior is not complete.
- **ACTIVE:** the next dependency-gated work.
- **LATER:** ordered work with known prerequisites.
- **RESEARCH:** useful direction without enough evidence to commit to a product design.

## Product identity

StarFur Forge is a local-first Resident Intelligence Platform. The product is the continuity system around replaceable models: inspectable memory, personas, context, providers, permissions, tools, perception, structured fictional worlds, and presentation surfaces.

StarFur is game-adjacent, not a general-purpose game engine. Its adventure subsystem should provide generic deterministic primitives—events, facts, resources, inventory, objectives, character knowledge, relationships, time, and replay—while language models narrate and interpret only the bounded state Core supplies. Core owns truth and mutation; the model supplies untrusted candidate prose or candidate changes.

The initial commercial target is a Steam application with:

- a useful local companion even without optional media models;
- a low-resource apartment/dashboard that visualizes Core state;
- drop-in declarative personas and character sprites;
- a safe Workshop import path that cannot execute arbitrary package code;
- local saves, migration, backup, recovery, and clear user controls;
- graceful degradation when a model, provider, capability, or asset is unavailable.

## Non-negotiable architecture

1. **Core is authoritative.** Permissions, memory boundaries, commands, state transitions, adventure resources, and hidden values are enforced before model prompting.
2. **Models are untrusted providers.** Their output may become a proposal or staged mutation, never an authoritative write merely because a prompt requested compliance.
3. **Full state is not prompt context.** Canonical stores retain complete truth; deterministic selectors create bounded, labeled projections for models and UIs.
4. **Presentation is replaceable.** CLI, OpenWebUI, a future dashboard/TUI, apartment, phone surface, and Steam client use shared application services.
5. **Packages are data by default.** Persona, sprite, apartment-theme, and adventure packages are versioned declarative content. Executable extensions require a separate permissioned plugin design.
6. **Namespaces do not blur.** Shared user memory, lore, persona-local learning, roleplay-scoped memory, and `adventure:<id>` state remain independently inspectable and governed.
7. **Automatic mutation is observable.** Every automatic memory, learning, or adventure change has provenance, policy, validation, an outcome, and a correction/recovery path.
8. **Evidence precedes claims.** Unit/integration tests prove mechanics; versioned behavioral benchmarks measure model-dependent reliability.

## Ownership boundaries

| Layer | Owns | Must not own |
|---|---|---|
| StarFur Core | canonical memory, adventure state, permissions, provider routing, package validation, migrations, audit events | persona prose, UI layout, provider-specific special cases |
| Persona package/runtime | static identity, bounded behavior defaults, declared interests, asset references, presentation preferences | Core permissions, shared-memory truth, arbitrary executable code, direct provider credentials |
| Adventure package/workspace | initial world definitions, generic resource declarations, content assets, isolated event/state history | shared user memory, real-world relationship state, unrestricted tools |
| Provider adapter | provider protocol translation, supported health/model metadata | session policy, canonical writes, hidden routing decisions |
| Presentation client | input, rendering, accessibility, user confirmation surfaces | direct database mutation, duplicated command semantics, canonical state reconstruction |
| Workshop installer | manifest validation, compatibility checks, bounded extraction, asset registration | trusting package paths, scripts, or remote dependencies implicitly |

## Evidence-backed completed foundation

### Shared memory, retrieval, and provenance — COMPLETED

- Separate assistant memory and lore structures, additive domains, validated types, soft forgetting, correction, compact IDs, proposal review/approval/rejection, evidence linkage, reinforcement, and confirmation-gated bulk approval are implemented primarily through `pipeline/db.py`, `pipeline/assistant.py`, and their assistant-memory tests.
- Deterministic production retrieval is injected through `pipeline/retrieval.py`; association expansion is domain-scoped and explainable. Semantic and hybrid retrieval remain fixture/evaluation paths rather than an implicit production fallback.
- Memory introspection is bounded to active canonical memories and approved provenance.
- External document candidates become shared assistant memories only through the existing review and proposal lifecycle.

### Context, application, providers, and clients — COMPLETED/FOUNDATION

- `pipeline/context.py` owns deterministic message assembly and token estimates.
- `pipeline/application.py:AssistantApplication` supplies a shared presentation-neutral service facade, bounded per-conversation session isolation, per-session serialization, and passive diagnostics.
- `pipeline/providers.py` defines `ChatProvider`, `OllamaChatProvider`, and fake-compatible callable adaptation. `pipeline/provider_state.py` exposes bounded lifecycle state.
- Runtime model selection, streaming, clean interruption rollback, context statistics, phase timing, capability manifests, CLI operation, and the OpenAI-compatible API are implemented.
- `pipeline/task_profiles.py` provides declarative workload configuration. It is not yet an automatic router or fallback engine.

### Document intake and reviewed RAG — FOUNDATION/IN PROGRESS

- Bounded text preparation, structural prechunk profiles, provider-backed per-chunk annotation, resilient failures, stable candidate identity, in-memory review sessions, explicit proposal handoff, source-scoped context packets, and an OpenWebUI Filter bridge exist in `pipeline/document_*` and `integrations/openwebui/`.
- Current limits remain: one supported text attachment in the Filter path, ephemeral review storage, synchronous long-document processing, no canonical multi-file workspace, and no production semantic document index.

### Benchmarks and experiment evidence — FOUNDATION

- `pipeline/retrieval_eval.py` runs versioned temporary-fixture deterministic/semantic/hybrid retrieval evaluation.
- `pipeline/benchmark.py` defines bounded run manifests and model-scaling plans.
- `pipeline/experiment_ledger.py` appends privacy-bounded benchmark results without raw prompts/responses.
- Behavioral suites for answer grounding, persona adherence, long-session recovery, routing, adventure replay, and resource use remain to be built.

### Persona Runtime — FOUNDATION

- Typed persona state, behavior context, persona selection, namespaced runtime snapshots, shared-memory visibility/scope policy, bounded attention, explicit learning/reference records, emotion derivation, relationship derivation, state transitions, and a deny-by-default sandbox contract are present across `pipeline/persona_*`, `pipeline/behavior.py`, `pipeline/emotion.py`, `pipeline/relationship.py`, `pipeline/momentary_state.py`, and `pipeline/sandbox.py`.
- Most development, emotion, relationship, and learning state remains restart-ephemeral and explicit-input-only. Autonomous inference, durable persona-local memory, and safe execution are not product-ready.
- Restart-ephemeral state is the current implementation status, not the desired permanent end state. Future work must distinguish durable persona-local continuity, reconstructable/transient state, and session-ephemeral generation state rather than treating all runtime state as uniformly persistent or uniformly disposable.

### Stage 5A adventure/CYOA — ACTIVE FOUNDATION

Current source and `tests/test_adventure*.py` verify:

- exact-title workspace registry and metadata manifests;
- session-local load/resume/pause/end/unload controls;
- a validated logical append-only `events.jsonl` history;
- bounded deterministic replay-spine selection;
- explicit event, state, qualitative relationship, and character-knowledge commands;
- derived latest-value projections from the event log;
- pre-prompt numeric fictional-meter redaction for retrieved relationship memories;
- session-local turn staging with explicit commit/abort of ordinary event drafts.

This is a functional prototype, not yet a durable simulation system. The implementation does not yet provide an `adventure:<id>` database/semantic namespace, complete unbounded world-state projection, cross-process write coordination, correction/supersession semantics, transcript storage, branching, generic typed resources, automatic narrative extraction, or crash recovery.

## Baseline discrepancies to carry forward explicitly

1. `ROADMAP.md` describes each adventure as eventually having an adventure database and semantic index, but `pipeline/adventure_registry.py` records both as `not_created`; only the registry, manifest, and event log currently exist.
2. The roadmap speaks of `adventure:<id>` namespaces, while current shared-memory retrieval still uses the assistant session domain. Roleplay scope is not an adventure ID and must not substitute for one.
3. `derive_adventure_state`, `derive_adventure_relationships`, and `derive_adventure_knowledge` apply 12-item limits while constructing what the session calls current state. Complete authoritative projections and bounded model projections are not separate yet.
4. `AdventureEventLog.append_many()` atomically replaces the event-log file in the ordinary success path, but manifest update, concurrent-writer coordination, idempotency, and crash recovery are not one durable transaction.
5. Existing structured state/relationship/knowledge commands write immediately; the current turn transaction stages only ordinary `AdventureEventDraft` values.
6. All stock persona packages currently have unrestricted shared-memory settings in `config/assistant.json`; restricted onboarding remains a future UX policy rather than current behavior.
7. Provider task profiles exist, but automatic routing, fallback, specialist-provider selection, and resource-aware unload policies do not.

## Dependency-ordered implementation roadmap

### Stage A — Adventure integrity and authoritative projections (ACTIVE; A2 next)

#### A1. Separate full projections from bounded context selectors (COMPLETED INITIAL SLICE)

- Complete rebuildable projections for world state, relationships, and character knowledge now use the entire validated event history.
- Prompt/UI limits now apply in separate selector functions and never truncate the authoritative projection itself.
- Diagnostics report both total projection counts and selected context counts.

**Acceptance:** more than twelve distinct state keys remain inspectable and survive reload, while only a deterministic bounded subset enters the prompt.  
**Tests:** over-limit state/relationship/knowledge fixtures, deterministic selection, restart rebuild, no state loss when prompt limits change.

#### A2. Harden workspace writes and recovery

- Add a workspace-scoped writer guard usable across independent application conversations and processes.
- Make registry, manifest, and event-log metadata updates recoverable and idempotent.
- Detect and safely handle stale `.pending` files, partial manifests, duplicate retries, and orphan workspaces.
- Add a durable commit/request ID before any automatic turn writer exists.

**Acceptance:** injected failures before/after replacement have one documented recoverable outcome; concurrent writers cannot lose or duplicate events.  
**Tests:** failure injection, two-writer races, retry idempotency, stale temporary recovery, malformed-tail failure, registry-orphan reconciliation.

**Completed initial slice:** workspace writes now use a fail-closed cross-process OS advisory lock that releases automatically if its owner exits, so a persistent lock file cannot itself become a stale ownership claim. Staged turn commits persist a validated request ID on their event batch. Matching retries are idempotent; conflicting request-ID reuse fails. Under the lock, a valid `.pending` replacement is recovered only when it extends the authoritative log; exact/redundant artifacts are removed, while malformed or divergent pending data fails closed. A valid nonempty log repairs only its stale `not_created` manifest marker; a manifest that claims an absent log remains an error. Broader failure-injection coverage remains before A2 is complete.

**Completed A3 foundation:** `pipeline.adventure_mutation` now validates and serializes pure schema-v2 envelopes carrying identity, timestamp, Core source, request ID, optional supersession, narrative summary/details, and one typed state/relationship/knowledge mutation. `pipeline.adventure_events` reads and preserves those validated v2 entries beside schema-v1 records, exposing their typed facts through existing projections. Core continues writing v1 until an explicit migration policy is validated.

**Completed A4 staging foundation:** `AdventureTurnTransaction` can retain ordinary drafts and typed state/relationship/knowledge mutations together under one request ID. Its explicit commit path writes compatible schema-v1 structured drafts, maintaining storage compatibility while establishing one all-or-nothing transaction boundary.

**Completed initial A4 Core-wiring slice:** exact `adventure turn stage state`, `adventure turn stage relationship`, and `adventure turn stage knowledge` commands validate typed structured facts and stage their schema-v1-compatible drafts beside ordinary events. Nothing reaches authoritative projections, prompt context, or the event log until the one Core commit. Existing direct state, relationship, and knowledge controls remain intentionally immediate.

#### A3. Introduce a typed mutation envelope

- Evolve the event schema incrementally so an event envelope carries identity, time, source, turn/request ID, and optional supersession reference while typed mutations carry state changes.
- Preserve reading of schema-v1 events.
- Keep narrative summary/details separate from mutation payloads.

**Acceptance:** old logs replay unchanged; new events expose provenance and typed mutations without parsing prose.  
**Tests:** v1 compatibility, v2 validation, unknown mutation rejection, round-trip serialization, no model-authored authority.

#### A4. Extend turn transactions to all structured changes

- Stage ordinary events, state changes, relationship changes, knowledge changes, and future resource operations in one transaction.
- Commit only after the complete turn succeeds and validates; interruption, empty output, provider error, cancellation, and workspace transition abort everything.
- Keep explicit immediate commands only if their immediate semantics are clear and separately documented.

**Acceptance:** one story turn cannot commit narration continuity while losing its associated state changes.  
**Tests:** mixed staged batch, interrupted generation seam, failed validation, abort, duplicate commit, workspace switch, restart after commit.

#### A5. Fail closed inside Core command namespaces

- Once input begins with a reserved mutating namespace such as `adventure turn`, malformed syntax returns Core help/error rather than falling through to model generation.
- Preserve narrow documented typo aliases only for non-mutating inspection.

**Acceptance:** malformed adventure mutations never call a provider or create a proposal.  
**Tests:** malformed prefixes, near-miss verbs, unknown event types, command precedence through CLI/API/OpenWebUI.

**Completed initial slice:** after exact documented adventure controls are considered, the reserved `adventure` namespace now returns deterministic Core guidance for every malformed or unknown `adventure ...` form. It does not call a provider, create a proposal, mutate chat history, or write the event log. Focused OpenAI-compatible API coverage now proves both malformed-command isolation and staged structured-fact invisibility/commit behavior through the adapter. A reserved adventure command also ignores stale OpenWebUI document-context/review extensions before those extensions can trigger review lookup or document retrieval. Remaining: a live OpenWebUI smoke check only.

### Stage B — Generic adventure state without becoming a game engine (NEXT)

#### B1. Scenario-declared resource definitions

**Completed initial definition slice:** Core now has a pure, closed generic resource catalog for scenario declarations: stable IDs and labels, public/hidden visibility, bounded integer/decimal ranges, enum values, and kind-valid permitted-operation metadata. It intentionally has no workspace-manifest integration, current values, event writes, commands, prompt projections, model extraction, or game-specific rules. Remaining B1 work must add event-backed resource state only through catalog-validated operations.

**Completed initial value slice:** Core now has a pure immutable reducer that supplies deterministic declared-resource defaults and validates supported operations against a catalog before producing a new complete value state. Illegal operations, unknown IDs, invalid inventory counts, and bounds violations fail before replacement. At this slice it remained in-memory only; the subsequent catalog-persistence slice adds declarations but still no resource events, commands, prompt/UI projections, model extraction, or generic game rules.

**Completed initial catalog-persistence slice:** A workspace may now receive exactly one JSON-safe validated catalog declaration before it has an event log; repeated identical initialization is idempotent, conflicting replacement fails, and legacy workspaces retain an empty catalog. This remains a package/Core setup boundary, not a user-facing configuration flow. No resource values, operations, events, commands, prompt projections, providers, or game-specific names were added.

**Completed initial resource-event slice:** Schema-v1 now supports a closed `resource_change` event with generic resource identifier, operation, and JSON-safe value. The event log validates the entire resource-operation sequence against the workspace's immutable catalog before reading or appending, and the pure reducer rebuilds complete values from validated events. There are still no resource commands, mounted-session/prompt/UI projections, provider extraction, or game-specific behavior.

- Core supplies a small closed set of generic kinds: boolean/enum flag, bounded integer/decimal resource, inventory item/count, equipment slot, objective, location, and clock/time marker.
- Adventure packages declare stable IDs, labels, type, bounds, visibility, and permitted operations.
- Core validates operations such as set, increment/decrement, add/remove, equip/unequip, activate, complete, and fail.
- Names such as `ammo`, `credits`, `health`, or `mana` remain package data rather than Core concepts.

**Acceptance:** two different adventures can declare different resources using the same Core primitives; invalid bounds and unknown IDs fail before prompting.  
**Tests:** schema validation, arithmetic boundaries, inventory idempotency, hidden/public projection, v1 event compatibility.

#### B2. Corrections, supersession, and contradiction inspection

- Add explicit correction/retraction/supersession relationships between events.
- Rebuild projections from active event semantics without deleting audit history.
- Distinguish objective facts, character beliefs, disputed facts, and unresolved contradictions.

**Acceptance:** correcting a location or belief changes current state while preserving the original event and explanation.  
**Tests:** correction chains, retractions, conflicting facts, differently worded knowledge claims, deterministic replay.

#### B3. Replay, restart, and branch semantics

- Define `restart from established premise`, `fresh restart`, checkpoint, fork/branch, archive, export, and restore.
- Preserve stable key events while allowing regenerated connective prose.
- Keep branch IDs and save state isolated; never infer branch truth from semantic recall.

**Acceptance:** the same seed/checkpoint reconstructs the same authoritative state even when narrated prose differs.  
**Benchmarks:** long-session restart, branch isolation, contradiction rate, key-event retention, recovery from interrupted turns.

### Stage C — Safe narrative-to-state loop (AFTER A AND B)

#### C1. Bind story lifecycle explicitly

- Add an explicit start/resume control that binds one loaded workspace, one roleplay session, and one active branch.
- Support carefully bounded natural phrases only as discoverable aliases; ambiguous titles require user selection.
- Keep unconditional Core exit/pause controls.

#### C2. Store transcript separately from canonical events

- Transcript records what was presented; event history records validated facts; full projections represent current truth; narrative memory is a bounded derived view.
- Transcript retention and privacy are configurable and never required to rebuild authoritative state.

#### C3. Add staged extraction, validation, and policy

- A task-specific provider may propose events/mutations from the completed user+narrator turn.
- Core validates source, schema, allowed resource operations, contradiction policy, salience, and adventure namespace.
- Strict high-confidence adventure policy may auto-commit low-risk continuity facts without interrupting immersion; uncertain/high-impact candidates remain visible in a post-turn review queue.
- Decorative prose, model inventions, and hidden reasoning never become canonical merely because they appeared in narration.

#### C4. Adventure import and document continuity

- Import reviewed story documents into a selected adventure workspace rather than shared personal memory.
- Preserve source/chunk provenance and stage typed candidates before commit.
- Support multi-file imports, asynchronous progress, resume/retry, and bounded failure reporting.

**Stage C gate:** no automatic extraction until Stage A concurrency/recovery, complete projection separation, typed mutations, and mixed transaction tests pass.

### Stage D — Continuous behavioral evaluation (START ALONGSIDE STAGE A)

**Completed initial fixture slice:** checked-in `adventure-integrity-v1` now evaluates validated in-memory event streams for complete structured projections, bounded replay selection, context-limit separation, and repeatability. The `adventure-eval` CLI is provider-free and cannot open runtime workspaces, production memory, or a ledger. Remaining fixtures must add command/lifecycle, corruption/recovery, relationship consistency, restart, and later resources; ledger integration needs a dedicated bounded adventure-result schema.

1. Add adventure fixtures for replay, state projection, correction, relationship consistency, knowledge isolation, resources, interruption, corruption, restart, and branching.
2. Record retrieval success separately from whether the model used retrieved facts correctly.
3. Add long-document RAG and annotation precision/false-positive suites with increasing sizes and chunk counts.
4. Add persona/instruction adherence, command-precedence, and prompt-contamination cases using fake providers plus optional local-model runs.
5. Compare identical StarFur workloads across model sizes/quantizations while holding architecture, seed, context, policy, and hardware metadata constant.
6. After stable routing, add route accuracy, fallback, latency, TTFT, memory, VRAM, load/unload, and energy/resource metrics when observable.
7. Later add ablations: full StarFur versus no retrieval, no association, no persona runtime, no structured adventure state, and raw-model baselines.

**Gate:** roadmap claims about “small models behaving like larger models” require recorded behavioral results, not unit-test success alone.

### Stage E — Provider registry and measured routing (LATER; before broad tools/media)

1. Convert declarative task profiles into a provider-neutral registry of available chat, embedding, vision, image, speech, and specialist capabilities.
2. Start with deterministic intent/capability rules and explicit user overrides; add a small routing model only where benchmarks show benefit.
3. Record route decision, confidence, selected provider/model, fallback reason, context budget, timing, and outcome without unrestricted prompt logging.
4. Add warm/load/cool/unload state only where the provider exposes trustworthy lifecycle information.
5. Preserve active-persona continuity by applying persona presentation after specialist results, while keeping specialist output labeled and untrusted.

**Acceptance:** a coding or image request can route to a configured specialist and return through the same session without changing memory or persona authority.  
**Tests/benchmarks:** route matrix, unavailable provider, timeout, empty output, fallback loops, user override, context stats accuracy, model-scale comparison.

### Stage F — Tools and permission engine (LATER; routing stable first)

1. Add a structured tool registry with typed inputs/outputs and declared side effects.
2. Centralize allow-once, always-allow, deny, confirmation-required, and revocation policy.
3. Separate read-only tools from state-changing tools; give filesystem, screen, network, process, and external-account access distinct scopes.
4. Produce bounded audit events and user-visible outcomes.
5. Connect the existing sandbox contract to a genuinely isolated backend before permitting autonomous code execution.

**Gate:** no background tool or Workshop package gains ambient filesystem/network/process authority.

### Stage G — Vision, media, and one-shot perception (LATER)

1. Add permissioned one-shot screen/window/region/file inspection through `VisionProvider`.
2. Add `ImageProvider`, TTS, and STT adapters behind the same capability registry and routing metrics.
3. Keep uploaded/captured media as bounded source objects with provenance; do not silently promote descriptions to memory.
4. Cache generated images and keep them non-canonical unless a separate structured event references the asset.

**Acceptance:** “inspect this window” and “generate this scene” are explicit, cancelable, provider-replaceable operations with no hidden continuous monitoring.

### Stage H — Apartment/dashboard prototype (LATER; read-only first)

#### H1. Read-only resident surface

- Render persona identity/state, current activity, provider lifecycle, loaded adventure, task progress, recent safe diagnostics, and permission prompts from structured public snapshots.
- Use replaceable placeholder/procedural assets and stable asset slots.
- Keep the surface useful on low-resource hardware while inference runs.

#### H2. Character presentation

- Add stable sprite/animation slots, expressions, poses, layers, and accessibility fallbacks.
- Persona runtime selects bounded presentation state; missing assets fall back safely.
- Commissioned art can replace placeholders without changing Core identifiers or save data.

#### H3. Permissioned ambient features

- Add opt-in idle scene cards/screensaver images derived from structured state, cached and debounced.
- Later add voice, notifications, calendar/feed displays, and permissioned system monitoring.
- Generated visuals are illustrations, never authoritative events.

### Cross-cutting later requirement — Zero-provider resident runtime (LATER; dependency-gated)

StarFur must remain meaningfully functional with no configured inference providers. This is not an anti-AI branch: it is the architectural consequence of Core resident continuity being separate from optional inference capabilities.

> Models add capabilities; they do not create the resident.

With chat, embedding, vision, image, speech, and hosted providers disabled or unavailable, Core must still restore the allowed resident/persona state and provide a coherent deterministic apartment-companion experience through authored assets and package data. Open-ended conversation, reasoning, perception, generated media, and voice remain optional provider-backed enhancements layered on top of that same resident state.

Use a Core-owned deterministic behavior selector rather than persona-specific provider checks:

```text
activity + momentary state + relationship/development state + elapsed time
+ deterministic events + persona behavior defaults
    -> ResidentAction
```

`ResidentAction` is a future structured presentation intent (for example: activity, animation, expression, movement target, reaction/sound cue, duration, and priority). Core chooses the intent; persona, sprite, apartment, and authored-dialogue packages supply optional asset or text variants such as `greeting.return_short`, `idle.reading`, or `status.tired`. A provider may later enrich wording from the same intent, but its absence must never reset identity or resident state.

Model-free resident behavior should use ordinary simulation techniques: finite state machines, utility scoring, schedules, deterministic transitions, seeded variation, and event-driven reactions. Commissioned or human-created sprite/rig assets, authored reactions, Workshop persona/sprite/apartment packages, local save/load, restart continuity, notifications, and simple interactions must work independently of generative systems.

**Release requirement:** a zero-provider installation boots a persona, restores allowed persistent resident state, runs deterministic activities/reactions, renders available human-authored assets, and exposes normal inspection/settings controls. Removing, unloading, swapping, or re-enabling an optional provider preserves persona identity, resident continuity, and apartment state while clearly reporting only the affected capability as unavailable.

**Tests:** no-provider startup; provider unavailable at startup; provider unload/swap while a resident is active; deterministic seeded behavior; authored-dialogue fallback; missing optional-media assets; restart continuity; assertions that zero-provider mode never attempts a provider call.

### Cross-cutting later slice — Persona-local continuity and presentation profiles (LATER; dependency-gated)

Implement only after persistence/recovery boundaries, policy enforcement, and behavioral benchmarks can observe and validate automatic mutation. Keep this separate from the immediate adventure sequence and from shared user memory.

- Define three explicit persistence classes: durable persona-local continuity; reconstructable/transient state; and session-ephemeral generation/planning state.
- Persist durable, persona-namespaced relationship/development evidence, familiarity or trust baselines, interests, verified skills, learning records, meaningful milestones, and last meaningful interaction timestamps. These records must never silently rewrite shared user memory.
- For momentary emotion, energy/attention/valence, activity, recent contributors, and absence/return context, persist only bounded timestamped snapshots and unresolved contributors where useful. Reconstruct current state on restart with deterministic elapsed-time decay/transition rules instead of restoring stale literal values indefinitely.
- Keep current response construction, temporary attention, clarification state, and other generation-specific planning session-ephemeral.
- Make automatic mutation observable, policy-governed, provenance-bearing, and reversible or correctable where practical. Persona A must not read persona B's private runtime continuity.
- Add optional user-local declarative behavior/presentation overlays that modify bounded expression defaults only. They grant no permissions or tools, do not alter installed persona packages or shared memory, can be disabled or removed without deleting accumulated continuity, survive compatible package updates, and fall back safely when missing or invalid. Do not commit to a file format yet; keep local overlays separate from distributed package content and require explicit user export before distribution.

**Acceptance:** meaningful relationship/development continuity survives restart; transient mood reconstructs and decays according to elapsed time rather than freezing; persona-local namespaces prevent cross-persona access; enabling/disabling an overlay changes presentation only; removing an overlay preserves continuity; compatible persona package updates do not reset user-local state; missing/invalid overlays use safe defaults; none of these operations mutate shared user memory or permissions.

**Tests:** restart and elapsed-time reconstruction with deterministic clocks; persona A/B isolation; overlay enable/disable/removal; package update compatibility; malformed-overlay fallback; provenance/rollback checks; assertions that shared-memory and permission stores remain unchanged.

### Stage I — Steam productization and Workshop (LATER; begin design before UI lock-in)

#### I1. Package manifest v1

Define declarative package types for persona, sprite/asset pack, apartment theme, and adventure. Each manifest includes:

- stable package ID, semantic version, schema version, minimum/maximum Core compatibility;
- display metadata, author, license/attribution, content tags, locale, and optional dependencies;
- declared capabilities and asset slots, never granted permissions;
- normalized relative paths, file sizes, hashes, and bounded package totals;
- optional fallback assets and upgrade/migration metadata.

#### I2. Safe installer and local package registry

- Validate in quarantine, prevent traversal/symlinks/oversized archives, reject executable content by default, and activate atomically.
- Keep installed package content immutable and user/runtime state in separate save namespaces so updates cannot erase memories or adventures.
- User-local overlays and accumulated persona runtime data are separate from installed package content. Normal Workshop install, update, or uninstall must not publish, overwrite, reset, or remove them unless the user explicitly chooses an export or destructive operation.
- Support disable, rollback, dependency errors, compatibility warnings, and offline use.

#### I3. Steam/Workshop adapter

- Treat Steam Workshop as a distribution adapter over the same local package validator.
- Never make Core depend on Steam APIs for local packages.
- Add content reporting/tagging hooks, attribution display, package conflict handling, and deterministic load order.

#### I4. Release engineering

- Add first-run setup, provider discovery, save paths, migration/backup/restore, crash recovery, log redaction, accessibility, controller/keyboard input, offline behavior, update compatibility, and uninstall data choices.
- Build smoke suites for clean install, update, rollback, corrupted package, missing provider, missing asset, save migration, and Workshop removal.

**Steam prototype gate:** companion chat, memory controls, persona switching, one persistent adventure loop, read-only apartment state, package installation, backup/recovery, and permission boundaries work without editing configuration files manually.

### Stage J — Resident autonomy and simulation (RESEARCH until prior gates pass)

- Permissioned scheduler/watchers and bounded idle work.
- Persona-local durable learning with verified experiments and provenance.
- Deterministic offline adventure simulation using structured time/resources, with models invoked only for meaningful decisions or narration.
- Procedural/generated adventures and composited visuals.
- Multi-persona discussion/council modes using temporary shared state.
- Crown of Claws writing-partner mode with POV, timeline, revelation, and contradiction analysis.

These remain research/future until permissions, benchmarks, recovery, and package boundaries are production-capable.

## Recommended immediate baby-step sequence

1. Implement A1: complete projections plus bounded selectors.
2. Implement A2: workspace lock, idempotent commit metadata, and recovery tests.
3. Implement A3/A4: typed mutation envelope and mixed turn transaction.
4. Implement A5: fail-closed reserved command namespaces.
5. Add the Stage D adventure benchmark fixtures for those boundaries.
6. Only then begin B1 generic resources and C1 bound adventure lifecycle.

Each slice should update source, focused tests, `AGENTS.md`, `CHANGELOG.md`, command documentation when user-facing, and this proposed roadmap if it becomes authoritative. Mark a slice completed only after its acceptance tests pass in the authoritative WSL environment.

## End state

The release target is not “a chatbot inside a game.” It is a local resident companion whose continuity remains stable while models, personas, art, voices, interfaces, and fictional worlds are swapped around it. Steam and Workshop provide distribution and presentation; StarFur Core remains the trustworthy continuity engine.
