# StarFur Forge C3 / Stage E / Stage H Foundation Review

Date: 2026-08-26  
Scope: constrained, read-only architectural review of the current repository, with this report as the only intended repository change.

## Review method and evidence discipline

This review treats current source and tests as evidence of implemented behavior, and `AGENTS.md`, `ROADMAP.md`, `ROADMAP.v4.md`, and command documentation as evidence of intended architecture. Where they disagree, the discrepancy is stated instead of silently reconciling it. No live provider, embedding, media, speech, or image service was invoked. No runtime data was opened or modified. The existing worktree was already substantially dirty before this review; the audit did not attempt to clean, stage, commit, or reinterpret those changes.

The current architecture is not missing a general “adventure system.” It already has a meaningful Core-owned integrity substrate. The immediate gap is a narrow, trustworthy coordinator between a completed turn, an untrusted task provider, the candidate inbox, and the existing explicit transaction. Stage E then needs to generalize task selection without gaining authority over Core state. Stage H can begin with read-only composition of existing snapshots, but not yet with claims of durable or zero-provider resident continuity.

## Findings

### C3 generated adventure-turn orchestration

#### Finding C3-1 — Generation-origin state is not preserved through provider handoff

- **Severity:** blocker
- **Gate:** required before the first model-backed adventure smoke test
- **Observed implementation fact:** `AdventureTurnGenerationRequest` records the source workspace and `event_count` (`pipeline/adventure_turn_generation.py:31-55`). `AdventureTurnCandidateInbox.select()` correctly rejects a batch when its stored count differs from the current count (`pipeline/adventure_turn_candidate_inbox.py:59-78`). However, `AssistantSession.present_adventure_turn_candidates()` accepts only a validated batch and stores the *current* `self.adventure_session.event_count` (`pipeline/assistant.py:1061-1075`), rather than the count from the request that existed before provider latency. The provider adapter returns decoded provider data only (`pipeline/adventure_turn_provider.py:59-72`); it does not return request origin metadata.
- **Architectural inference:** if the authoritative log advances after generation begins but before candidates are presented, handoff can relabel stale candidates with the new count. The later inbox guard then appears to pass. Per-conversation serialization in `AssistantApplication._locked_session_for()` (`pipeline/application.py:228-240`) reduces one in-process race but does not protect against another process, a future asynchronous coordinator, or direct Core writes to the same workspace.
- **Recommended action:** introduce an immutable `AdventureTurnGenerationResult` (or equivalently named value object) containing a Core-generated `generation_id`, adventure ID, original authoritative event count or event-prefix fingerprint, validated candidate batch, and bounded task/provider metadata. A single Core coordinator must compare the result origin with a freshly mounted/read authoritative origin before replacing the inbox. Never let `present_adventure_turn_candidates()` invent the origin at presentation time.

#### Finding C3-2 — Candidate identity is local to a batch, but staging idempotency treats it as session-global

- **Severity:** high
- **Gate:** required before model-backed regeneration/retry is enabled; safe only for a tightly constrained one-batch smoke test
- **Observed implementation fact:** parsing numbers every returned batch from `TC-001` (`pipeline/adventure_turn_candidates.py:79-107`). `AdventureTurnTransaction.stage_candidate()` considers a candidate already staged when its `candidate_id` matches any retained ID (`pipeline/adventure_turn.py:100-120`). The transaction does not record a candidate batch/generation ID. Tests prove same-object/same-ID idempotency (`tests/test_adventure_turn.py:146-166`) but do not cover two distinct batches that both contain `TC-001`.
- **Architectural inference:** a second generation in the same active transaction can produce a different `TC-001` that silently becomes a no-op. UI retry and fallback paths will make this likely.
- **Recommended action:** make candidate provenance identity `(generation_id, candidate_id)`. Display the generation ID in bounded review output, preserve it in staged draft provenance, and test two batches with colliding local candidate IDs. Keep human-facing `TC-###` labels, but do not use them alone as durable identity.

#### Finding C3-3 — Provider response size is unbounded before strict JSON parsing

- **Severity:** high
- **Gate:** required before the first model-backed adventure smoke test
- **Observed implementation fact:** input context and turn text have explicit character ceilings (`pipeline/adventure_turn_generation.py:17-55`), and decoded candidate envelopes are bounded (`pipeline/adventure_turn_candidates.py:17-107`). The chat adapter obtains `message.content` and passes the complete string to `json.loads()` without first enforcing a raw response-size limit (`pipeline/adventure_turn_provider.py:59-81`).
- **Architectural inference:** a misconfigured or poorly following model can return a very large response, consuming memory and parse time before candidate validation rejects it.
- **Recommended action:** add a small raw response byte/character ceiling aligned with the task profile’s output-token budget. Reject empty, oversized, fenced, prefixed, or suffixed content; do not add permissive “find JSON somewhere in prose” extraction. Preserve the current strict failure behavior.

#### Finding C3-4 — The model-facing context constructor accepts arbitrary text rather than a typed safe projection

- **Severity:** blocker
- **Gate:** required before the first model-backed adventure smoke test
- **Observed implementation fact:** `AdventureTurnGenerationRequest.authoritative_context` is a bounded string supplied by its caller (`pipeline/adventure_turn_generation.py:31-55`). Existing Core state already distinguishes complete authoritative projections from bounded context projections (`pipeline/adventure_session.py:41-170`) and hides non-public resources from normal context. `AGENTS.md` explicitly requires protected values to be sanitized before prompt assembly, and `pipeline/roleplay_presentation.py` exists because model instructions are not a protection boundary.
- **Architectural inference:** a future coordinator that passes arbitrary caller text can accidentally expose hidden resource values, numeric relationship meters, raw evidence, or non-authoritative document text while calling it “authoritative.”
- **Recommended action:** build generation context internally from a typed, presentation-safe adventure projection owned by Core. The coordinator should accept a mounted adventure/session object or a validated `AdventureTurnContextView`, not an externally authored “authoritative” string. Reuse the same protected-value policy as normal adventure prompt assembly, and include only bounded replay, public resources, qualitative relationships, perspective-scoped knowledge, and selected state.

#### Finding C3-5 — The advertised ordinary event-type contract and parser contract differ

- **Severity:** medium
- **Gate:** required before the first model-backed adventure smoke test
- **Observed implementation fact:** the generation prompt lists `choice`, `discovery`, `promise`, `lie`, `emotional_transition`, `unresolved_hook`, `inventory_change`, and `location_change` (`pipeline/adventure_turn_generation.py:63-73`). The parser derives its allowed set as all `DRAFT_EVENT_TYPES` except structured mutation types (`pipeline/adventure_turn_candidates.py:14-21`), which also permits any other non-structured draft type such as `premise` if present in `pipeline/adventure_events.py`.
- **Architectural inference:** provider output can pass validation despite violating the provider-facing closed list. Future event additions could silently expand model authority.
- **Recommended action:** export one immutable `ORDINARY_GENERATED_EVENT_TYPES` constant and use it for prompt rendering, decoded validation, help text, fixtures, and telemetry. Adding a generated event type should be an explicit policy change with a regression test.

#### Finding C3-6 — There is no Core-owned generated-turn coordinator yet

- **Severity:** high
- **Gate:** required before the first model-backed adventure smoke test
- **Observed implementation fact:** `ChatAdventureTurnCandidateProvider` is intentionally dormant and has no session or event-log integration (`pipeline/adventure_turn_provider.py:1-6,42-72`). `AssistantSession.present_adventure_turn_candidates()` is programmatic-only (`pipeline/assistant.py:1061-1067`). Exact commands can inspect and stage candidates but do not generate them (`pipeline/assistant.py:2425-2455`, `pipeline/command_help.py:105`, `docs/COMMANDS.md:565-568`).
- **Architectural inference:** this is the expected next architectural slice, not a defect. Wiring these pieces directly inside a command handler would mix provider execution, stale validation, lifecycle, and presentation.
- **Recommended action:** add one presentation-neutral application/service method with this sequence: capture completed bounded turn input; construct sanitized context and origin; resolve a task profile; call the injected candidate provider; enforce raw response and strict schema; re-read/check origin; atomically replace the session inbox; emit bounded diagnostics. It must never stage or commit candidates. CLI/OpenWebUI/API should call that one coordinator.

#### Finding C3-7 — Provider-candidate provenance disappears at canonical commit

- **Severity:** high
- **Gate:** required before model-backed candidate commits are treated as benchmarkable or release-quality; generation/review-only smoke may precede it
- **Observed implementation fact:** candidates retain confidence and a local ID (`pipeline/adventure_turn_candidates.py:28-55`). The transaction records candidate IDs beside draft indexes (`pipeline/adventure_turn.py:19-60,100-120`), but canonical event append receives ordinary drafts and a batch request ID. The event schema does not preserve a generation ID, task profile, provider/model, candidate ID, or review decision. Existing correction/retraction support preserves event history (`pipeline/adventure_events.py`, tests in `tests/test_adventure_events.py:279-322`) but cannot reconstruct why a generated draft entered it.
- **Architectural inference:** a committed generated event cannot later be attributed in audit, evaluation, or debugging, and model portability results become hard to reproduce.
- **Recommended action:** add bounded, optional Core-authored event provenance metadata or an adjacent append-only decision record keyed by event ID. Store identifiers and hashes, not unrestricted prompt/response text. Preserve schema-v1/v2 read compatibility and keep provider confidence informational.

#### Finding C3-8 — Typed model proposals need separate schemas and policy, not a widened ordinary parser

- **Severity:** high
- **Gate:** safe to defer for the first ordinary-event candidate smoke; required before automatic narrative-to-state extraction
- **Observed implementation fact:** ordinary candidate validation explicitly rejects state, relationship, knowledge, and resource fields (`pipeline/adventure_turn_candidates.py:44-52,79-107`). Manual mixed staging already supports typed state/relationship/knowledge and catalog-validated resources atomically (`pipeline/adventure_turn.py:123-187`; `tests/test_adventure_turn.py:45-104`). `pipeline/adventure_mutation.py` owns typed schema-v2 envelopes, while current Core staged writes remain schema-v1 compatible per `AGENTS.md`.
- **Architectural inference:** widening the ordinary JSON envelope would weaken a deliberate authority boundary and create accidental state from prose.
- **Recommended action:** add independent typed proposal value objects per mutation family, each with its own whitelist, validation, review rendering, and stage adapter. Resource proposals must validate against the immutable scenario catalog before entering the inbox. One generation result may carry ordinary and typed proposal groups, but review and selection remain explicit and the final transaction remains all-or-nothing.

#### Finding C3-9 — Interruption and failure semantics are strong after staging but undefined during generation

- **Severity:** high
- **Gate:** required before the first model-backed adventure smoke test
- **Observed implementation fact:** staged turns are session-local and commit atomically; abort writes nothing (`pipeline/adventure_turn.py:74-216`; `tests/test_adventure_turn.py:19-44`). Provider failures become `AdventureTurnProviderError` (`pipeline/adventure_turn_provider.py:62-72`). There is no coordinator policy defining whether a failed/empty/interrupted generation preserves or clears an older inbox, whether it aborts an already active manual transaction, or how retry IDs relate to event-log request IDs.
- **Architectural inference:** presentation clients may show stale candidates after a failed retry, or a naïve implementation may abort unrelated user-staged work.
- **Recommended action:** define generation and staging as separate state machines. Generation failure/interruption must create no candidates and no canonical writes; it should not abort an unrelated active transaction. A replacement request should mark the previous inbox superseded or clear it before generation according to one documented policy. Only commit uses the transaction’s existing request ID and event-log idempotency. Add failure-injection tests for timeout, interruption, empty output, invalid JSON, stale origin, retry, abort, and commit.

#### Finding C3-10 — Corrections and retractions are compatible at the event layer, but generated-turn policy must target active history

- **Severity:** medium
- **Gate:** safe to defer for ordinary new-event smoke; required before generated correction proposals
- **Observed implementation fact:** schema-v1 events remain readable, schema-v2 mutations survive later appends, active correction resolution fails closed, and retraction is append-only (`tests/test_adventure_events.py:199-322`; `pipeline/adventure_correction.py`). Exact Core correction commands require active tips under the policy described in `AGENTS.md`.
- **Architectural inference:** the storage substrate can support generated correction suggestions, but a model must not identify arbitrary supersession targets from prose or mutate historical records directly.
- **Recommended action:** keep correction/retraction proposal types separate from ordinary and typed-new-fact candidates. Core should supply a bounded list of eligible active event IDs, validate exact target activity at selection and again at commit, and persist the user/Core review decision as provenance.

### Provider and task routing preparation

#### Finding E-1 — Task profiles are useful configuration, not yet a router or fallback engine

- **Severity:** observation
- **Gate:** required before Stage E routing, not before the first directly injected model-backed smoke
- **Observed implementation fact:** `TaskProfile` carries provider, model, generation options, context size, output tokens, and `fallback_task` (`pipeline/task_profiles.py:58-120`). `TaskProfiles.resolve()` selects a configured profile (`pipeline/task_profiles.py:124-151`). `provider_matches()` only verifies the configured label against the current runtime (`pipeline/task_profiles.py:173-181`). The known tasks do not yet include adventure-turn extraction (`pipeline/task_profiles.py:17-19`). `ChatProvider` is a single generic completion/list/probe protocol (`pipeline/providers.py:17-38`).
- **Architectural inference:** these are good Stage E inputs, but `fallback_task` currently describes metadata, not a safe bounded fallback chain.
- **Recommended action:** first add a stable Core task ID such as `adventure_turn_extraction` and use direct dependency injection. Later introduce a `ProviderRegistry` and pure `RoutePlanner` returning a `ResolvedRoute` with task, capability, provider, model, options, budgets, reason, and bounded fallback candidates. Do not fold registry discovery or execution into `TaskProfiles`.

#### Finding E-2 — Routing must never own Core authority

- **Severity:** blocker
- **Gate:** required before Stage E routing
- **Observed implementation fact:** current provider adapters return data and do not access event logs (`pipeline/adventure_turn_provider.py:1-6`). Candidate validation and explicit selection are Core-owned. `AssistantApplication` owns session selection/locking while `AssistantSession` owns commands and turn state (`pipeline/application.py:65-284`, `AGENTS.md`).
- **Architectural inference:** a router that performs staging, persistence, persona mutation, memory approval, permission checks, or adventure state reconciliation would collapse the strongest current boundaries.
- **Recommended action:** constrain routing to “choose and execute an eligible provider for a typed task.” Core constructs sanitized input, validates the typed result, decides fallback eligibility, and performs every state transition. Keep permissions, memory retrieval, persona continuity, event commits, correction resolution, candidate selection, and presentation outside the router.

#### Finding E-3 — Fallback and unavailable-provider behavior is not represented faithfully in diagnostics

- **Severity:** high
- **Gate:** required before Stage E routing; partially required before a dashboard labels provider availability
- **Observed implementation fact:** `AssistantApplication.runtime_diagnostics()` exposes lifecycle and bounded provider health but currently reports `fallback: {used: False, reason: None}` unconditionally (`pipeline/application.py:375-431`). Provider health is “not probed” unless explicitly requested. Tests verify passive diagnostics and explicit non-generating probes (`tests/test_application.py:349-389`, `tests/test_api.py:151-176`).
- **Architectural inference:** once routing exists, a static fallback field will become misleading. “Configured,” “not probed,” “unavailable,” and “task unsupported” are distinct states.
- **Recommended action:** add an immutable per-request `RouteDecision`/`RouteOutcome` snapshot with selected route, bounded rejection reasons, fallback count, terminal failure category, and task capability status. Diagnostics should expose only this bounded trace, never raw provider payloads. Prevent fallback loops with a finite visited-route set and maximum attempts.

#### Finding E-4 — Provider lifecycle is single-request/session oriented and not yet a model residency manager

- **Severity:** medium
- **Gate:** required before Stage E loading/unloading optimization; safe to defer for a directly injected smoke
- **Observed implementation fact:** `ProviderLifecycle` tracks disconnected/connecting/loading/ready/generating/streaming/idle/error transitions for one provider/model snapshot (`pipeline/provider_state.py:8-61`). It does not manage queues, model residency, unload policy, VRAM, concurrency limits, or per-specialist health. `ChatProvider` has no load/unload contract (`pipeline/providers.py:17-38`).
- **Architectural inference:** routing can begin without automatic unloading, but annotation speed and multi-model use need a separate residency/scheduling service rather than lifecycle strings inside the router.
- **Recommended action:** keep lifecycle snapshots descriptive. Add a later optional `ModelResidencyManager` capability with explicit load/unload/lease semantics, resource observations, and cancellation. Route planning may consult it; route execution must not infer hardware capacity or unload a model without policy.

#### Finding E-5 — Persona continuity is already outside providers and should stay there

- **Severity:** observation
- **Gate:** design invariant before Stage E routing
- **Observed implementation fact:** session-scoped persona selection and `PersonaRuntimeRegistry` remain Core-owned (`pipeline/persona_runtime.py:22-142`, `pipeline/assistant.py`). Switching personas clears recent conversation but not shared canonical memory, providers, or tools per `AGENTS.md`. Task profiles can change model/options without changing persona.
- **Architectural inference:** specialist model swaps can preserve Murr/Nova identity if every task returns typed data into the same Core session and final presentation uses the active persona context.
- **Recommended action:** route specialist extraction/analysis independently from final response presentation. Never let a route select a persona, replace persona state, or make provider chat history the durable identity store. Include persona ID only as bounded task context when the task actually requires presentation style.

#### Finding E-6 — Routing telemetry needs a bounded schema and ledger bridge

- **Severity:** medium
- **Gate:** required before measured Stage E routing
- **Observed implementation fact:** benchmark manifests already record provider/model/quantization/context/hardware/git/seed (`pipeline/benchmark.py:8-60`). The experiment ledger is append-only and raw-content-free but accepts only retrieval-oriented metric fields (`pipeline/experiment_ledger.py:11-26,82-159`). Runtime diagnostics expose provider latency/TTFT for recent turns but not a route decision (`pipeline/application.py:375-431`).
- **Architectural inference:** route-quality claims cannot be reconstructed from current ledger records.
- **Recommended action:** version a bounded behavioral-result schema that records task ID, route/profile fingerprint, provider/model/quantization, attempts, fallback category, latency/TTFT, parse/validation result, and Core-use result. Keep raw prompts/responses opt-in and outside the normal ledger. Do not overload retrieval-only `expected`/`returned` integer IDs for adventure candidates.

### Persona and NPC participation

#### Finding P-1 — Participant and initiative contracts exist, but there is no participant-view assembler

- **Severity:** medium
- **Gate:** required before model-backed NPC/persona initiative; safe to defer for narrator-only generated turns
- **Observed implementation fact:** `AdventureParticipantMemoryPolicy`, `AdventureParticipant`, `PersonaInitiativePolicy`, and `evaluate_initiative()` provide bounded, provider-free validation and eligibility (`pipeline/adventure_initiative.py:27-121`; `tests/test_adventure_initiative.py`). They do not read projections, schedule work, call providers, or write events.
- **Architectural inference:** the missing stable interface is a read-only `AdventureParticipantView` assembled from the loaded adventure’s active event projection, character-specific knowledge, allowed relationship facts, public/participant-visible resources, recent replay facts, and limited unresolved hooks.
- **Recommended action:** add a pure participant-view builder keyed by exact adventure ID and participant ID. It must enforce fact counts, perspective, visibility, and a context budget, and must never write a separate memory merely because a fact was selected.

#### Finding P-2 — NPCs do not need full StarFur memory subsystems

- **Severity:** observation
- **Gate:** design invariant before NPC memory implementation
- **Observed implementation fact:** authoritative adventure facts already live in append-only events and rebuildable projections (`pipeline/adventure_events.py`, `pipeline/adventure_state.py`, `pipeline/adventure_relationship.py`, `pipeline/adventure_knowledge.py`, `pipeline/adventure_resource_state.py`). Participant policy already requests bounded adventure namespaces (`pipeline/adventure_initiative.py:27-63`). Assistant personal memory is a separate reviewed/provenance-heavy system per `AGENTS.md`.
- **Architectural inference:** cloning assistant memory databases per NPC would duplicate world truth, complicate corrections, and add unnecessary retrieval/provider work.
- **Recommended action:** treat each NPC’s durable “memory” as character-knowledge and relationship events plus optional package-defined traits and a small derived salience/recent-experience cache. Important facts remain in the authoritative event log. A bounded cache may evict low-salience entries deterministically and rebuild from events; it must not become independent truth.

#### Finding P-3 — Participant namespace validation is too weak for future isolation

- **Severity:** medium
- **Gate:** required before participant memory is persisted or routed to a provider
- **Observed implementation fact:** current initiative contracts validate an `adventure:` namespace shape but do not demonstrate that it equals the currently loaded adventure or contains an exact participant identity (`pipeline/adventure_initiative.py:27-63`; `tests/test_adventure_initiative.py:11-18`).
- **Architectural inference:** accepting arbitrary adventure-prefixed strings will be insufficient once multiple workspaces/personas/NPC caches coexist.
- **Recommended action:** use a typed namespace object constructed from the mounted `AdventureRecord.adventure_id` plus validated participant ID. The view builder, initiative evaluator, and provider request should receive that object rather than free-form namespace text.

#### Finding P-4 — Real-world persona state and fictional adventure state are properly separated, but participation binding is missing

- **Severity:** medium
- **Gate:** required before active-persona party-member initiative; safe to defer for narrator-only smoke
- **Observed implementation fact:** `PersonaRuntimeRegistry` stores real-world persona dynamic/momentary/development/relationship state (`pipeline/persona_runtime.py:22-142`). Adventure relationships and knowledge are separate event-backed projections, and `AGENTS.md` forbids fictional facts from changing real-world persona/user relationships. No current contract binds the active persona to a participant record in a loaded adventure.
- **Architectural inference:** a persona can be presented as a party member without copying real-world relationship values into the story, but the binding must be explicit and adventure-local.
- **Recommended action:** add an adventure participant roster/mapping that references a persona package ID while storing all story role, relationship, knowledge, inventory, cooldown, and initiative state under `adventure:<id>`. Persona runtime contributes identity/presentation only. Unloading the adventure removes the binding from prompt context without mutating real-world state.

#### Finding P-5 — Initiative eligibility is deterministic, but cooldown history has no authoritative event/state source yet

- **Severity:** medium
- **Gate:** required before autonomous or proactive participant turns
- **Observed implementation fact:** `evaluate_initiative()` accepts caller-supplied trigger, action, cooldown, and turn-count conditions (`pipeline/adventure_initiative.py:71-121`). It does not own a clock or persistence, consistent with its pure-contract role.
- **Architectural inference:** callers could accidentally supply inconsistent cooldown/turn history unless Core derives it from authoritative events or a reconstructable scheduler record.
- **Recommended action:** define explicit initiative-attempt/accepted-action audit events or a separate reconstructable adventure activity log. Core computes eligibility; the provider proposes at most one bounded action; the normal candidate/typed-mutation review and commit path remains authoritative. Zero-provider mode may deterministically decline or choose package-authored actions.

### Stage H apartment/dashboard preparation

#### Finding H-1 — Useful read-only pieces exist, but there is no unified resident snapshot

- **Severity:** high
- **Gate:** required before the apartment/dashboard prototype
- **Observed implementation fact:** `AssistantApplication.runtime_diagnostics()` exposes bounded provider/model/lifecycle/latest-turn/capability data (`pipeline/application.py:375-431`). `persona_runtime_snapshot()` exposes the active conversation’s bounded persona runtime (`pipeline/application.py:294-308`), backed by `PersonaRuntimeState.public_dict()` (`pipeline/persona_runtime.py:87-103`). `AdventureSessionState.public_dict()` exposes loaded workspace counts/status (`pipeline/adventure_session.py:149-168`). The API exposes diagnostics and persona runtime (`pipeline/api.py:51,618-646`) but not a unified adventure/resident state endpoint.
- **Architectural inference:** a dashboard could call chat commands and parse prose today, but that would duplicate CLI behavior and make UI state unreliable.
- **Recommended action:** define a versioned, presentation-neutral `ResidentSnapshot` composed under the application/session lock. Include active persona public state, provider/model lifecycle and capability availability, roleplay/adventure mount summary, authoritative/context projection counts, turn staging/candidate-inbox status, and a bounded current activity. Start with polling; event streaming can be added later without changing the schema.

#### Finding H-2 — The apartment must display Core facts, never infer or mutate them

- **Severity:** blocker
- **Gate:** required before the apartment/dashboard prototype
- **Observed implementation fact:** existing public snapshots deliberately omit prompts, raw evidence, relationship subjects, memory contents, and hidden resources (`pipeline/persona_runtime.py:87-103`, `pipeline/adventure_session.py:149-170`, `AGENTS.md`). Command handlers remain the current Core mutation surface.
- **Architectural inference:** deriving “Murr is thinking,” mood, provider health, relationship values, or adventure state by parsing generated prose would recreate model authority at the UI layer.
- **Recommended action:** publish explicit enums/fields such as resident activity, provider lifecycle, task activity, active persona, adventure mount, and capability degradation. The apartment may render, animate, filter, and request an existing Core command/action; it must not calculate canonical state, write databases, approve proposals, or translate animation completion into a story event.

#### Finding H-3 — Client synchronization requires one application service, not duplicated command logic

- **Severity:** high
- **Gate:** required before Stage H; begin before adding more client-specific features
- **Observed implementation fact:** CLI and OpenAI-compatible API already share `AssistantApplication` and per-conversation session locking (`pipeline/application.py:65-284`, `pipeline/api.py:91-114`). Exact adventure controls are owned by `AssistantSession`, and malformed `adventure` commands fail closed (`tests/test_adventure_commands.py:54-87`, `tests/test_api.py:731-751`).
- **Architectural inference:** CLI, OpenWebUI, TUI, dashboard, and Steam can stay synchronized if they use stable typed application methods/snapshots; they will drift if the dashboard sends natural-language chat commands and parses responses.
- **Recommended action:** expose typed application methods for read models and controlled actions, then adapt each client. Keep OpenAI chat compatibility as a presentation adapter, not the only control protocol. Use the same opaque conversation/session identity and report when state is session-local versus durable.

#### Finding H-4 — Zero-provider resident architecture is coherent in the roadmap but not implemented end to end

- **Severity:** high
- **Gate:** safe to defer for H0/H1 read-only prototype; required before H2/H3 polish and Steam/release claims
- **Observed implementation fact:** Core adventure commands, event projections, persona package selection, and public snapshots are provider-free. `ROADMAP.v4.md:406-428` defines deterministic `ResidentAction`, authored assets/dialogue, schedules, finite-state/utility behavior, and no-provider tests. There is no current durable resident scheduler/activity store, authored-dialogue resolver, asset resolver, restart-persistent persona runtime, or `ResidentAction` implementation.
- **Architectural inference:** an apartment can truthfully show “provider unavailable” and deterministic stored Core state now, but it cannot yet claim that Murr independently lives, sleeps, works, and restores continuity without a provider.
- **Recommended action:** H0/H1 should be a read-only diagnostic/state viewer with explicit degraded capability status. Implement zero-provider behavior later as a separate deterministic runtime consuming package data and durable reviewed state, not as fallback text inside the provider router.

#### Finding H-5 — Session-local state and LRU eviction need explicit UI semantics

- **Severity:** medium
- **Gate:** required before multi-chat apartment/dashboard use
- **Observed implementation fact:** `AssistantApplication` retains one legacy/default session plus a bounded LRU registry of conversation sessions and pins in-flight sessions (`pipeline/application.py:179-240`; tests `tests/test_application.py:163-263`). Candidate inboxes, staged turns, active mounts, and much persona runtime are restart/session ephemeral.
- **Architectural inference:** a dashboard can appear to “lose” an active candidate inbox or mount when a conversation key changes, is evicted, or the process restarts, even while canonical adventure events remain safe.
- **Recommended action:** expose conversation ID, storage class, last-active time, and ephemeral/durable flags in the resident snapshot. A future dashboard chooses one stable resident session explicitly. Never imply that session-local candidate/staging state is restart durable.

### Benchmark and validation readiness

#### Finding B-1 — Current adventure integrity benchmarks validate projections, not generated-turn behavior

- **Severity:** high
- **Gate:** required before architecture claims about model-backed turns; a basic exploratory smoke may run first if clearly labeled
- **Observed implementation fact:** `adventure-integrity-v3` covers complete state/relationship/knowledge/resource projections, replay selection, invalid resources, branch-prefix isolation, and repeatability (`pipeline/adventure_eval.py:28-242`; `tests/fixtures/adventure_integrity_cases.json`; `tests/test_adventure_eval.py:17-39`). Event-log unit tests cover validation, locks, request idempotency, pending recovery, schema compatibility, corrections, retractions, checkpoints, and resource catalogs (`tests/test_adventure_events.py:28-364`). No behavioral fixture evaluates model candidate extraction, false positives, provider errors, or Core use of candidates.
- **Architectural inference:** event integrity is well founded, but it cannot support a claim that a model correctly extracts or applies story changes.
- **Recommended action:** add an `adventure-turn-extraction-v1` suite that separately scores provider output validity, candidate precision/recall, false positives, no-event cases, protected-value leakage, stale rejection, explicit selection, and final committed projection accuracy.

#### Finding B-2 — The experiment ledger schema is retrieval-specific

- **Severity:** high
- **Gate:** required before generated-turn benchmark results enter the experiment ledger
- **Observed implementation fact:** the ledger allows only retrieval metrics (`top1_hit_rate`, `top3_hit_rate`, recall/precision, irrelevant count, latency/TTFT, repeatability) and case payloads with integer `expected`/`returned` memory IDs (`pipeline/experiment_ledger.py:11-79,82-159`). The benchmark manifest already carries the major reproducibility metadata (`pipeline/benchmark.py:12-60`). `ROADMAP.md:421-442` intends broader reusable instrumentation.
- **Architectural inference:** forcing adventure candidates into integer memory-ID fields would make results semantically misleading; adding arbitrary metrics would weaken bounded privacy guarantees.
- **Recommended action:** version the ledger with typed benchmark-family case schemas, or add a separate bounded adventure result adapter that normalizes into a v2 ledger. Include candidate type/key hashes, counts, outcome categories, route metadata, latency/TTFT, and Core-use result without raw story text.

#### Finding B-3 — Retrieval success and model-use success must remain separate in adventure evaluation

- **Severity:** medium
- **Gate:** required before comparative model/provider claims
- **Observed implementation fact:** StarFur already has separate retrieval evaluation and context diagnostics. The planned generated-turn path contains distinct steps: Core projection selection, provider generation, strict parse, candidate validation, user selection, staging, commit, and reconstructed projection.
- **Architectural inference:** one end-to-end pass/fail would hide whether a small model failed to extract a fact, Core rejected malformed data correctly, the candidate was not selected, or the final narrator failed to use valid context.
- **Recommended action:** record independent outcomes for context selection, provider response, schema validation, semantic candidate correctness, Core acceptance/rejection, canonical projection, and final answer/narration use. This directly supports the small-model scaling research goal.

#### Finding B-4 — Permanent regression fixtures should preserve failures without preserving private transcripts

- **Severity:** medium
- **Gate:** begin with the first model-backed smoke; safe to defer automated promotion tooling
- **Observed implementation fact:** checked-in deterministic fixtures already exist for retrieval and adventure integrity. The ledger intentionally excludes raw content (`pipeline/experiment_ledger.py:1-11,82-129`).
- **Architectural inference:** real failures are valuable, but copying personal CYOA/manuscript text into public fixtures or the ledger would conflict with privacy and reproducibility goals.
- **Recommended action:** minimize each failure into a synthetic, sanitized fixture retaining the triggering structure. Record the originating failure category, architecture fingerprint, model profile, and expected Core behavior. Keep optional raw captures local and explicitly privacy-approved.

#### Finding B-5 — Cross-platform and restart behavior is underrepresented

- **Severity:** medium
- **Gate:** required before release-quality routing/apartment claims; safe to defer for the first in-process candidate smoke
- **Observed implementation fact:** event-log tests exercise advisory locking and pending recovery in temporary directories (`tests/test_adventure_events.py:66-198`), and application tests exercise concurrent conversations and LRU behavior (`tests/test_application.py:163-263`). There is no checked-in Windows-versus-WSL lock/restart matrix, process-kill generation test, provider-unload mid-task test, or persisted resident-state restart test.
- **Architectural inference:** the development workflow’s Windows/WSL split and OpenWebUI timeouts make these likely practical failure points.
- **Recommended action:** add an opt-in platform smoke harness that records OS/filesystem, process boundaries, provider profile, and outcome. Keep unit tests fake-provider/provider-free. Preserve interruption cases for generation-before-inbox, inbox-before-stage, stage-before-commit, and event-log pending replacement.

## Minimum stable interfaces

The following are the smallest useful contracts between subsystems. They should be added incrementally, not as a framework rewrite.

1. **Core → generated-turn context:** `AdventureTurnContextView`, built only from sanitized bounded Core projections and carrying an authoritative origin fingerprint/count.
2. **Core → task execution:** `AdventureTaskRequest`/`AdventureTurnGenerationRequest` with task ID, context view, untrusted completed-turn text, budgets, and generation ID.
3. **Provider execution → Core:** `AdventureTurnGenerationResult` with origin, route/task metadata, timing/failure category, and a strictly validated candidate envelope; never write authority.
4. **Core candidate review:** session-local `AdventureTurnCandidateInbox` keyed by adventure and generation ID, with stale-origin checking at present, inspect, stage, and commit boundaries.
5. **Core transaction:** existing `AdventureTurnTransaction`, extended only to preserve batch/candidate provenance and to accept separately validated typed proposals.
6. **Core → presentation:** versioned `ResidentSnapshot` and later `ResidentEvent`, containing bounded public state and explicit storage/lifecycle classes.
7. **Core → participant provider:** `AdventureParticipantView` with exact adventure/participant identity, bounded perspective, initiative eligibility, and no real-world relationship leakage.
8. **Benchmarks → ledger:** typed behavioral case result and route result schemas with privacy-bounded identifiers and reproducibility metadata.

The provider registry/router should never own interfaces 1, 4, 5, 6, or canonical portions of 7. It should only resolve and execute interface 2 and return interface 3.

## Current architectural position

StarFur is in Stage 5A with a mature provider-free adventure integrity foundation and the opening C3 candidate-generation boundary. The repository already has append-only validated event history, recovery and advisory locking, request-ID idempotency, schema-v1/v2 read compatibility, active correction/retraction resolution, complete event-backed projections separate from bounded prompt projections, catalog-validated resources, explicit mixed turn staging, checkpoint-derived branches, reviewed document import, exact fail-closed adventure commands, declarative task profiles, one generic `ChatProvider` boundary, session isolation, bounded persona/provider diagnostics, and initial deterministic adventure benchmarks.

It does **not** yet have model-backed adventure orchestration, typed generated mutations, durable generated-candidate provenance, a provider registry/router, an adventure participant-view assembler, a unified resident snapshot, durable persona resident continuity, or a zero-provider apartment simulation. C3 should therefore advance through one coordinator and its benchmark seams before Stage E routing. H0/H1 read-only apartment work can proceed in parallel after a stable resident snapshot, but deeper apartment behavior should wait for explicit continuity and zero-provider gates.

## Must fix before model-backed adventure smoke test

1. Preserve the generation request’s original adventure ID and event count/fingerprint through provider latency; reject stale results before inbox replacement.
2. Build provider context from a typed Core-sanitized adventure view, not arbitrary “authoritative context” text.
3. Enforce a raw provider response-size ceiling before `json.loads()` and retain strict JSON-only behavior.
4. Unify the provider prompt and parser’s ordinary event-type whitelist.
5. Add a Core-owned orchestration method with explicit generation failure, interruption, replacement, and retry semantics; it may populate the inbox but never stage or commit.
6. Add fake-provider tests for success, empty output, oversized output, malformed JSON, invalid schema, provider exception, stale origin during latency, and no canonical write.
7. Either add generation/batch identity before allowing retries/regeneration in an active turn, or explicitly prohibit multiple batches for the first narrow smoke.
8. Record at least bounded generation/task/provider/model/timing metadata so the smoke result can be interpreted; add durable event provenance before treating generated commits as validated architecture.

## Must fix before provider routing

1. Register a stable adventure-turn extraction task profile and exercise it through direct injection first.
2. Add a pure provider registry/capability view and route planner; keep Core state and permissions outside it.
3. Define finite, loop-free fallback behavior and distinguish configured, unprobed, unavailable, unsupported, failed, and degraded states.
4. Add bounded `RouteDecision`/`RouteOutcome` diagnostics and a compatible experiment-ledger schema.
5. Preserve persona identity and resident session continuity across provider/model changes.
6. Define context/output budgets per task and a separate optional model-residency manager; do not make the router infer VRAM or unload policy.
7. Benchmark route stability, fallback correctness, provider portability, latency/TTFT, and Core validation across at least fake providers plus two real profiles when explicitly run.

## Must fix before apartment/dashboard prototype

1. Add a versioned, read-only `ResidentSnapshot` composed by `AssistantApplication` under the selected conversation lock.
2. Include bounded persona, provider/model lifecycle, capability status, loaded adventure, projection counts, roleplay, staged-turn, candidate-inbox, and explicit activity fields; include storage class and conversation identity.
3. Expose the snapshot through a presentation-neutral application method and authenticated API endpoint. Do not require clients to parse chat command prose.
4. Specify that the UI may display/request but never infer or mutate canonical memory, mood, relationship, adventure, provider, or permission state.
5. Make unavailable/unprobed provider states explicit so a read-only apartment can degrade honestly.
6. Document LRU/session eviction and restart-ephemeral fields before multi-chat dashboard testing.

H0/H1 may remain provider-backed and session-ephemeral. Durable zero-provider activities, authored dialogue, asset resolution, schedules, and restart continuity are later release gates rather than blockers for the first read-only shell.

## Safe to defer

- Generated typed state/relationship/knowledge/resource proposals, provided the first smoke is ordinary-event generation/review only.
- Generated correction and retraction proposals; existing explicit Core correction/retraction remains authoritative.
- Autonomous persona/NPC initiative, cooldown scheduling, and offline adventure advancement.
- Persistent NPC salience caches; event-backed participant views should come first.
- Automatic model loading/unloading and resource-aware queueing.
- Streaming route events/SSE; polling a versioned snapshot is sufficient for H0/H1.
- Full zero-provider resident simulation, authored-dialogue selection, apartment animation FSM, TTS/STT, vision, image generation, and idle scene rendering.
- Workshop packaging/editor UX and RPG-engine adapters.
- Automatic promotion of real failures into fixtures; manual sanitized regression capture is enough initially.

## Recommended baby-step implementation order

1. Export one exact ordinary generated-event whitelist and add a response-size ceiling with unit tests.
2. Add `generation_id` and immutable origin fields to a generation result; add the stale-during-provider-latency regression test.
3. Extend inbox and transaction candidate provenance to `(generation_id, candidate_id)`; test two batches containing distinct `TC-001` candidates.
4. Add a pure `AdventureTurnContextView` builder from the mounted session’s sanitized bounded projections; test hidden resource and numeric relationship non-disclosure.
5. Add the presentation-neutral generated-turn coordinator with an injected fake provider. Success populates only the inbox; every failure leaves canonical state untouched.
6. Add exact Core/API initiation and status surfaces around that coordinator. Keep candidate review/stage/commit explicit.
7. Add bounded generation decision/provenance metadata and carry it through staged commit audit without raw provider text.
8. Add `adventure-turn-extraction-v1` deterministic fake-provider fixtures and the first privacy-bounded result adapter.
9. Run the first explicit real-model smoke and minimize every failure into a sanitized regression fixture.
10. Add separate typed proposal schemas one family at a time: state, relationship, knowledge, then catalog-validated resources. Reuse the existing mixed transaction.
11. Add `AdventureParticipantView` and explicit active-persona participant binding; keep initiative disabled.
12. Add the versioned `ResidentSnapshot` plus authenticated read-only endpoint and a placeholder polling dashboard/TUI surface.
13. Add the Stage E provider registry and pure route planner around already benchmarked task execution.
14. Add fallback/route telemetry and model residency only after route behavior is measurable.
15. Add deterministic initiative and zero-provider `ResidentAction` slices after persistence/storage policies are explicit.

## Benchmark cases to add first

1. Valid zero-candidate response for a turn containing no continuity fact.
2. One exact ordinary discovery with no false positive.
3. Multiple ordinary events in stable source order up to the configured limit.
4. Disallowed typed mutation or `premise` returned through the ordinary contract and rejected.
5. Empty, fenced, prefixed, malformed, wrong-version, unknown-field, oversized, and over-count JSON.
6. Provider exception, timeout/interruption, and unavailable model: no inbox replacement, staging, event, or memory write.
7. Event log advances while provider is running: result rejected as stale before presentation.
8. Two generation batches each containing `TC-001`: both remain distinguishable; retry of the exact same generation is idempotent.
9. Candidate inspection is read-only; explicit selection stages only one; abort persists none; commit persists the selected batch atomically.
10. Mixed ordinary and each typed proposal family, with all structured values invisible until commit.
11. Hidden resource value and numeric relationship meter never enter provider messages or normal narration candidates.
12. Prompt-contamination attempt in user/narrator text cannot create commands, permissions, hidden reasoning, or structured mutations.
13. Correction/retraction after a generated event preserves history and yields the correct active projection.
14. Provider/model portability matrix holding architecture, source turn, seed, context budget, and expected candidates constant.
15. Separate measurements for context selection, parse validity, candidate precision/recall, false-positive rate, Core acceptance, canonical projection, and final narration use.
16. Latency, TTFT where meaningful, provider/model/quantization/context/output budgets, hardware, git commit, route/fallback, and failure category captured without raw story content.
17. Long conversation/session LRU behavior, process restart, provider unload, WSL/Windows advisory lock behavior, and recovery at each pre-commit boundary.

## Roadmap/documentation corrections

1. `ROADMAP.md` accurately records the recent C3 foundation through the dormant provider adapter (`ROADMAP.md:309-331`) and identifies the active dependency order (`ROADMAP.md:333-344`). Add the stale-origin handoff and batch-identity gates before describing the inbox stale guard as complete end-to-end.
2. `ROADMAP.v4.md` still labels Stage A as “A2 next” and Stage B as “NEXT” (`ROADMAP.v4.md:118,175`) while current source/tests and later inserted completion notes show substantial A2-A4, B, and C3 work. Revise status labels or add a dated implementation-position block; do not erase the intended dependency gates.
3. `ROADMAP.v4.md` correctly states task profiles are not a router (`ROADMAP.v4.md:65-71`) and places routing at Stage E (`ROADMAP.v4.md:351-370`). Add the proposed `ResolvedRoute`/bounded route-outcome boundary and explicitly keep Core validation/commit outside the router.
4. `ROADMAP.v4.md` correctly places the apartment read-only first (`ROADMAP.v4.md:382-404`) and zero-provider runtime later (`ROADMAP.v4.md:406-428`). Add `ResidentSnapshot` as the H0 contract and distinguish a read-only provider-degraded prototype from the later zero-provider release gate.
5. `docs/COMMANDS.md:565-568` accurately says candidate commands do not generate. When orchestration is added, document generation initiation, batch/generation identity, stale/retry semantics, and its noncanonical status. Do not imply that `adventure turn candidates` itself calls a provider.
6. `AGENTS.md` should gain the final coordinator ownership rule once implemented: only Core may build sanitized generation context, compare authoritative origin, replace the inbox, and convert explicit selections into existing transactions; providers and routers never own these actions.
7. The benchmark documentation should state that the current ledger v1 is retrieval-shaped and that adventure/routing results require a bounded versioned adapter/schema rather than arbitrary extension fields.

## Open design questions

1. Should staleness use event count, deterministic event-prefix fingerprint, or both? A fingerprint is stronger across repair/import scenarios; count is cheaper and useful for diagnostics.
2. On a failed regeneration, should Core preserve the last still-current inbox, clear it immediately, or retain it visibly as superseded? The choice must be explicit and consistent across clients.
3. Should generated-candidate provenance live on each event record or in an adjacent append-only decision log? The former simplifies inspection; the latter avoids expanding the event schema for non-story metadata.
4. What is the exact source of a “completed turn” for generation: an explicit transcript pair, a generated narrator response after stream completion, or a dedicated typed API request? Partial streamed text must never qualify.
5. Which typed proposal family should follow ordinary events first? State is simplest; relationship and knowledge require perspective policy; resources require catalog-aware operation validation.
6. Is the active persona automatically a participant when an adventure begins, or only after an explicit roster binding? Explicit binding is safer and supports narrator-only personas.
7. Which participant facts are visible to the persona versus NPCs, especially private player inventory, hidden resources, and uncertain character knowledge?
8. What durable store, if any, should hold NPC salience caches? Rebuildable event-derived views should be sufficient until benchmarks prove a cache is needed.
9. Is H0 tied to one stable resident conversation ID, or can it inspect several sessions? A single explicit resident session is simpler and avoids ambiguous ephemeral state.
10. Which snapshot fields are durable, restart-reconstructable, session-local, or provider-observed? The schema should label storage class rather than leaving clients to infer it.
11. Does task fallback mean another model/provider for the same task, a deterministic Core implementation, or a different task profile? These should be distinct route outcomes.
12. What privacy policy permits raw prompt/response capture for failed benchmark minimization? The default ledger should remain raw-content-free.
