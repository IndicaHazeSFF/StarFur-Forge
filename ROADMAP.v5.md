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

### Truth-seeking and research escalation

Core factual policy is persona-independent. When approved memory and supplied
context do not support a direct real-world answer, StarFur must use an
authorized bounded research tool or clearly state that it cannot verify the
answer; plausible provider prose is never evidence. Explicit research requests
and configured important, time-sensitive, or niche gaps may trigger a
brokered public lookup, while low-stakes gaps should prefer transparent
uncertainty. Research results remain untrusted, source/time-stamped evidence
and never automatically become memory, persona learning, adventure state, or
canon. Roleplay and adventure may invent within their declared fictional
namespace, but fictional details must not be presented as real-world facts or
cross into shared reality. Provider or tool unavailability must produce an
inability-to-verify response rather than a guess.

## Current position

The repository is in **Stage 5A / C3 foundation**. Implemented foundations include domain-separated assistant memory and retrieval, reviewed document intake, persona runtime and visibility policy, provider/application boundaries, adventure registries and append-only event logs, recovery/locking/idempotent writes, complete structured projections with bounded replay/context selectors, resources, relationships, character knowledge, checkpoints/branches, correction/retraction, mixed explicit turn staging, adventure import review/mapping, candidate inbox/review/staging primitives, benchmark manifests, retrieval evaluation, and a privacy-bounded experiment ledger.

The next product loop is not a router or an apartment animation system. It is a safe model-backed adventure-turn coordinator: Core captures a completed turn, constructs sanitized context, invokes one task provider, validates strict candidates, checks that the world did not change during generation, presents candidates for explicit selection, and reuses the existing transaction for staging/commit.

## Ownership boundaries

| Layer | Owns | Must not own |
|---|---|---|
| Core/application | canonical memory/adventure state, projections, permissions, command precedence, route policy, package validation, read models | persona prose or provider-specific authority |
| Persona package/runtime | identity, bounded traits, declared interests, presentation defaults, asset references | Core memory truth, permissions, credentials, executable behavior |
| Adventure workspace | isolated event history, scenario catalog, state/relationship/knowledge/resource projections, replay | shared personal memory or real-world relationships |
| Provider adapter | completion protocol translation; optional bounded health/model metadata | commands, state writes, memory approval, permissions, hidden routing |
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

**COMPLETED C3 STRUCTURED-OUTPUT CONFORMANCE SLICE (WSL/OLLAMA SMOKE PASSED):**
Ordinary and typed generated-turn tasks now supply separate Core-owned portable
structural JSON Schemas to an exact route only when its adapter explicitly
implements the non-streaming structured-output capability. Strict candidate
parsers remain authoritative for closed fields, bounds, vocabulary, and version;
schemas grant no event authority, and a structured request that fails never
silently retries through an unconstrained text path. Legacy or
injected text-only adapters preserve the existing strict-JSON route for tests
and compatibility. Focused fake-provider tests cover both distinct schemas.
The WSL/Ollama smoke passed for ordinary discovery/inventory candidates and a
text-valued typed `state_set` candidate; neither path auto-staged or persisted
provider output.

**COMPLETED C3 DUPLICATE-JSON REJECTION SLICE:** Both ordinary and typed
generated-turn adapters now reject duplicate JSON object keys at every nesting
level before candidate parsing. Python's last-key-wins decoder behavior can no
longer alter an untrusted candidate envelope silently; malformed output still
creates no inbox, staged event, or write.

**COMPLETED C3 COMBINED-REVIEW SLICE:** Exact `adventure turn review` renders
the separate ordinary and typed candidate inboxes together for human review.
It is presentation-only: it calls no provider and cannot select, stage, commit,
or couple the two candidate channels.

**COMPLETED C3 PORTABLE-RESOURCE GUARD SLICE:** The live portable structured
typed-generation route now fails closed if a provider proposes `resource_change`.
Generic resource values require a catalog-shaped schema and their own smoke gate;
the existing injected/text compatibility path remains review-only and catalog
validated at explicit staging.

**COMPLETED C3 PUBLIC-RESOURCE POLICY VIEW SLICE:** A provider-free,
presentation-neutral read model now projects at most eight declared public
resource IDs, kinds, permitted operations, and enum choices for a future
resource-specific candidate contract. It never exposes hidden definitions or
current values and cannot parse, validate, stage, or write a resource operation.

**COMPLETED C3 PAIRED-GENERATION ORCHESTRATION SLICE (WSL/OLLAMA SMOKE PASSED):**
Exact `adventure turn generate all <text>|transcript` runs the already separate
ordinary and typed candidate tasks against one bounded source, then renders
their separate inboxes through read-only `adventure turn review`. If either
replacement generation fails, both noncanonical inboxes clear together while
manual staged drafts remain untouched. It still never auto-selects, stages, or
commits provider output.

**COMPLETED C3 RESERVED-PREFIX FAIL-CLOSED SLICE:** A pasted leading `/` or
`\\` before the reserved `adventure` command namespace is now rejected as a
malformed Core command. It is deliberately not corrected into a potentially
mutating command and cannot reach model generation, memory proposal extraction,
or a story write.

**COMPLETED C3 DURABLE-ORIGIN RECHECK SLICE:** Ordinary and typed candidate
generation now compare the mounted event count with the validated durable event
log before provider submission and again before candidate presentation. A
cross-session append during provider latency leaves no review inbox; Core asks
the user to refresh rather than presenting candidates against an obsolete
projection. The check is read-only and never refreshes or discards manual
staging implicitly.

**COMPLETED C3 RESOURCE-CANDIDATE ELIGIBILITY SLICE:** The public resource
policy view can now evaluate one already-parsed `resource_change` candidate
against only its bounded public declarations. Hidden or omitted IDs, disallowed
operations, and invalid enum values deny before a future resource-specific
provider review route; the full catalog remains the separate authoritative
staging/value-validation boundary. This helper has no live provider wiring,
state lookup, staging, or write authority.

**COMPLETED C3 PORTABLE-ENUM RESOURCE CONTRACT SLICE:** The first candidate
contract for a future live resource route is deliberately limited to public
enum `set` operations. Its Core-owned structured schema contains only declared
public enum IDs and their finite allowed values; its strict parser then rejects
every non-resource mutation, hidden/omitted resource, non-enum resource,
non-`set` operation, or invalid enum value. Numeric, flag, inventory,
equipment, objective, location, and clock operations remain explicit/manual
until each has its own value contract and smoke evidence. No new provider task,
inbox, command, staging, or write path exists yet.

**COMPLETED C3 PUBLIC-ENUM RESOURCE ROUTE (WSL/OLLAMA SMOKE PASSED):** A third,
separate generated-candidate channel now carries only public enum `set`
operations. Its Core-owned `TR-###` inbox, structured schema, generation task,
review/status commands, provenance, durable-origin recheck, and explicit
staging path are distinct from ordinary `TC-###` and typed `TM-###` channels.
The provider receives no current or hidden resource values; Core revalidates a
selected candidate against the full immutable catalog and current/staged state
before the existing transaction may commit it. The remaining gate is one real
WSL/Ollama round trip with a scenario that declares a public enum resource;
numeric, inventory, hidden, and automatic resource mutation remain deferred.

**COMPLETED C3 RESOURCE-ROUTE REGRESSION EVALUATION:** The provider-free
`adventure-turn-resource-v1` fixture suite now covers public-enum candidate
generation through explicit staging and append-only commit, explicit no-change,
hidden-resource rejection, and stale-origin rejection. `python starfur.py
adventure-resource-eval` runs only temporary-workspace fixtures and may record
bounded result metadata through the existing explicit experiment-ledger path;
it invokes no provider or runtime adventure workspace.

**COMPLETED C3 RESOURCE-TRANSCRIPT PARITY SLICE:** Exact `adventure turn
resources generate transcript` now accepts only the latest explicitly recorded
adjacent user/narrator pair, preserves its `AT-...` provenance in the bounded
resource-generation status and any later selected-event provenance, and fails
closed for an incomplete/non-adjacent pair. It remains an untrusted source path:
it cannot establish story truth, stage, or persist a resource change by itself.

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
has one adapter; document annotation retains a separately bounded,
single-provider content-validation retry path.

**COMPLETED INITIAL E1 ANNOTATION ROUTE-PLANNING SLICE:** Document annotation
now resolves both its primary and explicitly configured content-validation
fallback profile through the same pure route planner before a request is made.
Both must resolve to the existing injected adapter; this is compatibility
validation, not multi-provider selection. The two-primary/one-fallback retry
sequence remains a separate bounded extraction policy.

**COMPLETED INITIAL E1 BOUNDED TELEMETRY SLICE:** Routed chat execution now
has a sanitized public outcome record containing only requested/selected task
IDs, provider/model labels, fallback use, and submitted outcome. Assistant
turn traces and runtime diagnostics reuse the same bounded shape; provider
responses, prompts, messages, and payloads remain outside the record. Public
route previews additionally expose clamped context/output budgets without
probing or executing a provider.

**COMPLETED E1 PROVIDER-NEUTRAL TEXT-CONTRACT SLICE:** Complete responses and
streamed text fragments now cross into Core through one typed, text-only
normalization seam. Normal chat, proposal extraction, document annotation, and
adventure-turn extraction no longer parse a particular adapter payload shape.
The seam deliberately excludes raw payloads, tool data, transport metadata,
provider construction, cancellation, and retry/fallback authority.

**COMPLETED E1 COMPLETION-ONLY SPECIALIST SLICE:** The provider registry and
task-specific adventure adapters now require only the narrow text-completion
protocol. The active resident adapter remains responsible for optional model
listing and health probing; a routed specialist need not imitate capabilities
it does not have. Provider-free tests prove a completion-only specialist can
be registered, selected, and executed without any probe or discovery call.

**COMPLETED E1 STREAM-OUTCOME SLICE:** The bounded route trace now changes
from submitted to completed only after a non-stream response or a streamed
iteration finishes. A stream failure or interruption records a closed failure
or cancellation category; partial generated text never enters conversation
history, proposals, or canonical state. This is telemetry only and does not
add a retry or fallback path.

**COMPLETED INITIAL E1 PORTABILITY-EVALUATION SLICE:** A checked-in,
provider-free routing fixture now verifies primary selection, finite configured
fallback, unavailable-provider rejection, and capability mismatch rejection.
It consumes only declarative profiles and bounded status records, reports no
prompt/provider payload/configuration data, and is a regression contract—not
a claim that alternative live providers are ready.
Its aggregate pass/fail route outcomes may enter the experiment ledger only by
explicit CLI opt-in; profile/provider configuration remains out of that record.

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
The stock local profile is now Qwen3 8B primary-only after the first checked-in
quality fixture showed Phi-4 Mini could be transport-valid yet return no
expected facts. Phi remains an explicit benchmark candidate, not a silent
fallback, until additional public quality evidence supports a bounded role.
This is not general provider routing: it neither probes, constructs adapters,
persists raw output, retries indefinitely, nor grants provider output authority
before the existing review boundary.

1. Preserve the existing stable task IDs, beginning with `adventure_turn_generation` and `adventure_turn_mutation_generation`, in declarative profiles; add new IDs only through the same validation boundary.
2. Add a provider/capability registry and pure route planner returning a bounded route decision, profile, budgets, and finite fallback candidates.
3. Keep Core responsible for sanitized input, validation, permissions, candidate selection, staging, commits, memory, and persona continuity.
4. Distinguish configured, unprobed, unavailable, unsupported, failed, degraded, and fallback states.
5. Add loop-free fallback, user overrides, route telemetry, provider portability benchmarks, and model/context budgets.
6. Keep lifecycle reporting descriptive; add model load/unload/residency management only as a separate explicit capability with leases/cancellation/resource observations.

The router chooses and executes a task. It does not become a second application layer or a hidden game director.

## Stage F — Tools and permissions (LATER; routing stable first)

Typed tool registry, explicit scopes, read-only versus mutating tools, confirmation/revocation, bounded audit events, and a genuinely isolated sandbox backend. No provider or Workshop package receives ambient filesystem, network, process, or account authority.

**COMPLETED INITIAL F1 DESCRIPTION SLICE:** Core now has a provider-free immutable tool-description registry. A descriptor declares only a stable ID, read-only or mutating access mode, permission scope, and confirmation requirement; it cannot execute, inspect permissions, grant authority, or be supplied by a model/package. Every mutating descriptor fails closed unless it declares confirmation. Permission grants, revocation, audit events, and executors remain separate gates.

**COMPLETED INITIAL F1 EVALUATION SLICE:** A separate pure permission evaluator now accepts only exact caller-supplied scope grants and one explicit per-request confirmation value. It has no wildcard/inherited scope behavior, storage, command surface, provider input, or executor. A grant for one scope cannot authorize a neighbor; a mutating descriptor remains denied without both an exact mutating grant and confirmation.

The first declared tool is `sandbox.run`, a confirmation-required description
for bounded learning exercises. This is metadata only: the default sandbox
backend remains denied and no registry entry grants execution authority.

**COMPLETED INERT F1 CONTRACT SLICE:** Core now binds that descriptor to a
versioned, provider-free `sandbox.run` proposal/result contract with finite
inline exercise-data, JSON size/depth, output, artifact-reference, registry,
and version limits. Exact schemas reject unknown and authority-bearing fields,
duplicate keys, non-finite values, and malformed or unsupported envelopes;
nested validated arguments are immutable. This is application validation, not
authentication, authorization, confirmation, provenance, invocation issuance,
OS isolation, or execution. Grants, approval control, commands, broker state,
materialization, audit persistence, providers, learning, and executors remain
deferred to their separately gated slices.

**COMPLETED SESSION AUTHORITY SLICE:** Core now has provider-free, bounded,
restart-ephemeral invocation, grant, and approval primitives. One invocation
binds an exact validated proposal digest and resource set to a trusted internal
principal, server-created session instance, persona/adventure context labels,
tool version, policy revision, and expiry. Exact grants are finite-use and
revocable; confirmation is a separate single-use controller record bound to the
grant's current revocation generation. Neither conversation/persona labels nor
model-supplied booleans provide identity or authority. Persistent and standing
grants remain unavailable.

**COMPLETED DISABLED BROKER SLICE:** A bounded provider-free broker now enforces
conflicting request-ID rejection, identical-request idempotency, stale-context
denial, separate authorization/queue/execution phases, pre-effect cancellation,
terminal replay safety, strict result validation, and privacy-bounded in-memory
audit events. Its Core default executor is unavailable and cannot call the
existing sandbox service; public broker/audit records exclude arguments, file
content, output text, provider payloads, and exception details. Application,
CLI/API, durable journal, materialization, provider proposal, and real isolation
integration remain separately gated. S4a is the first manual smoke-test gate.

**COMPLETED TRUSTED LOCAL CONTROL SLICE (PENDING WSL SMOKE):** One broker is
owned by each bounded ephemeral application session and is bound to an
unpredictable server-created session instance. The local interactive Assistant
CLI may submit and preview one inert `sandbox.run` proposal, then explicitly
grant, approve, deny/revoke, cancel, list, or inspect it. These controls never
materialize files or dispatch an executor. Shared chat, OpenWebUI, and API
requests reserve but deterministically reject the `tool` namespace before
document context or provider generation; no bearer token or conversation key
acts as approval authority and no HTTP approval endpoint exists. Context
changes and session eviction fail closed. Platform path hardening, durable run
journaling, OS isolation, and real execution remain later gates.

**COMPLETED S5 MATERIALIZATION/RESULT HARDENING (PENDING WINDOWS/WSL SMOKE):**
The pre-execution sandbox now checks UTF-8 byte limits and portable path forms,
rejecting traversal/noncanonical paths, Windows-reserved names, alternate
streams, and unsafe separators before any copy-in. An unavailable backend or
one that cannot affirm the requested policy is denied before temporary
materialization; temporary cleanup remains scoped to the disposable workspace;
and bounded reports omit raw backend exception text. This remains application
validation and copy-in, not OS isolation or execution. Native Windows/WSL
filesystem smoke evidence is required before durable run recovery or a native
isolation backend.

**COMPLETED S6/B4 DURABLE ADMISSION FOUNDATION (PENDING CROSS-PLATFORM
MULTIPROCESS SMOKE):** A separate optional Core-owned tool-run journal writes
bounded intent/outcome records under protected locks with pending-replacement
recovery, strict JSON validation, and duplicate-outcome idempotency. One
OS-held lifetime owner lease plus a Core-created owner epoch makes admission
and reconciliation single-owner across processes. Each admitted ID is bound
to one opaque invocation fingerprint and can never regain fresh authority;
same-owner live intents remain live, while abandoned or expired intents can
only become `outcome_unknown`. Replay-safe compaction remains unavailable, so
capacity exhaustion fails closed without deleting admission evidence. The
journal retains no proposal arguments, raw paths/resources, grants, approvals,
output, artifacts, prompts, or provider data; recovery never restores authority
or replays work. The default runtime still has no configured durable tool
journal or available execution supervisor.

**COMPLETED B5 SUPERVISOR-LIFECYCLE FOUNDATION (WINDOWS/WSL TESTED):** Strict
immutable contracts now represent one exact launch, bounded
status, cancellation acknowledgement, and verified completion under a
Core-created worker generation. Queueing consumes session authority while
retaining its deadline and revocation generation; the broker rechecks both
immediately before launch and does not hold its lifecycle lock during a
supervisor call. Cancellation can therefore reach a fake running worker.
Definite completion, failure, timeout, or cancellation requires matching
invocation/tool/version/policy/generation data and verified stop; malformed
results, post-launch exceptions, unknown cancellation, or unverified stop stay
`outcome_unknown` and cannot trigger replay. The default supervisor is still
unavailable. No real process, VM, backend selection, materialization, provider
call, or OS-isolation claim is part of this slice.

**COMPLETED B6 PORTABLE COPY-IN/OUTPUT CONTRACT SLICE (PENDING WSL SMOKE):**
Inert tool proposals and temporary sandbox materialization now share one pure
portable file-tree validator. It rejects case/Unicode aliases, file/directory
prefix collisions, traversal, alternate streams, reserved Windows names, and
other noncanonical paths before any copy-in. Backends must explicitly affirm
availability and policy support first; materialization and cleanup faults yield
bounded failures. A UTF-8 byte-bounded output collector includes its truncation
marker within the ceiling, and tool result envelopes independently reject
invalid or oversized multibyte output. The broker remains disconnected from
the sandbox service; no process, VM, host export, guest mount, provider call,
or executable backend was added.

**COMPLETED B7 READ-ONLY HYPER-V READINESS SLICE (WINDOWS/WSL BOUNDARY
SMOKE PASSED):** A fixed explicit WMI/CIM query can produce privacy-bounded Windows
host-prerequisite evidence without elevation, feature changes, VM inventory,
service control, downloads, or guest launch. Import, startup, diagnostics, and
apartment reads never trigger it. The WSL-to-Windows smoke correctly reported
the development host's unsupported client edition and left execution unavailable.
Host prerequisite success never implies
execution readiness: the Generation 2 Linux image, authenticated Hyper-V-socket
candidate transport, supervisor enrollment, and native containment conformance
remain unconfigured, so execution stays unavailable. Failures expose only
closed reason labels. Current Microsoft platform references and the optional
Steam/distribution boundary are recorded in `docs/SANDBOX_BACKENDS.md`.

**COMPLETED B8A LOCAL-SUPERVISOR IPC AUTHENTICATION CONTRACT (PENDING WSL
TEST):** A provider-free inert contract now authenticates one future enrolled
Core client through a strict byte-bounded HMAC envelope. It binds the enrollment,
Core principal, server-created session instance, fixed operation, invocation
fingerprint, worker generation, key ID, short lifetime, request ID, and nonce,
and separately requires an OS-trusted peer principal. Alteration, expiry,
revocation, wrong principal/key, malformed input, request/nonce replay, and full
replay capacity deny. Authentication never supplies tool authorization or
backend readiness; public views omit principals and tags. Native IPC, service
installation, ACL/key storage and rotation, OS peer acquisition, restart-safe
replay state, Hyper-V management, materialization, and execution remain disabled.

**COMPLETED B8B IPC FRAMING/DISCONNECT CONTRACT (PENDING WSL TEST):** An
in-memory fake receiver now frames strict authenticated requests with one fixed
four-byte length prefix. Fragmented/coalesced reads remain bounded by finite
per-connection byte and frame ceilings; invalid lengths/JSON, authentication
failure, replay, overflow, and partial disconnect permanently close the
connection. Abort discards only buffered bytes and is not cancellation or stop
proof. No pipe/socket, response, dispatch, persistent replay store, native peer
discovery, Hyper-V operation, or executable backend was added.

**COMPLETED B8C AUTHENTICATED SUPERVISOR RESPONSE CONTRACT (PENDING WSL
TEST):** The reverse channel now uses a service response key separate from the
client request key. Strict framed responses bind the exact request, enrollment,
service/transport revisions, invocation fingerprint, and worker generation and
carry only operation-compatible validated status, cancellation, or completion
objects. Wrong bindings/keys, altered or oversized payloads, replay, overflow,
and partial disconnect deny. Public views omit response tags, principals, result
text, and artifacts. No service, socket, key store, dispatch, persistence,
readiness claim, or execution was added.

**COMPLETED B8D PASSIVE SUPERVISOR/TRANSPORT READINESS CONTRACT (PENDING WSL
TEST):** A pure evaluator now compares a Core-owned expected profile with
short-lived supplied evidence. Exact backend/service/transport/policy revisions
and every required ACL, directional-key, OS-peer, request/response auth/framing,
and restart-replay dimension are mandatory. Host incompatibility, missing or
unavailable evidence, stale/future timestamps, mismatches, and incomplete
enforcement return only a sanitized unavailable reason. Synthetic readiness is
not discovery, attestation, authority, selection, or execution permission.

**COMPLETED B12A PASSIVE SANDBOX-STATUS PRESENTATION SLICE (WSL/APARTMENT
SMOKE PASSED):** The resident snapshot now exposes a strict sanitized
optional-execution status from a passive injected source. Its Core default is
unconfigured/disabled; invalid or failing sources become `observation_failed`.
Only schema/configured and closed host/supervisor/execution/reason fields cross
the boundary. The apartment renders the status without receiving backend,
service, transport, endpoint, path, principal, key, inventory, or evidence data.
Polling never probes, enrolls, connects, selects, authorizes, installs, or runs.

**COMPLETED S9B AGGREGATE TOOL-STATUS PRESENTATION SLICE (PENDING
WSL/APARTMENT SMOKE):** The resident snapshot and apartment now show only
bounded session-local counts for pending-review, approved, queued, running,
terminal, and total tool requests. They expose no request or tool identities,
arguments, files, resources, grants, approvals, audit entries, results,
artifacts, or backend details. Polling remains read-only and cannot create a
session, grant authority, approve, dispatch, cancel, probe, or execute.

**COMPLETED B9A GUEST-IMAGE COMPATIBILITY CONTRACT:** Core can now declare
one exact expected Generation 2 Linux/x86-64/VHDX image binding and compare it
with bounded short-lived supplied verification evidence. Digest, toolchain,
required signer, license policy, patch policy, and revision mismatches fail
closed. A passing result is only `compatible`, never trusted or ready. The
contract opens, hashes, downloads, installs, selects, and launches nothing and
creates no backend authority.

**COMPLETED S11A INITIAL WEB-EGRESS POLICY CONTRACT:** A pure policy seam now
validates one canonical HTTPS destination against separate short-lived supplied
DNS evidence. Credentials, fragments, nonstandard ports, noncanonical hosts,
localhost, and literal or resolved non-global addresses deny. A passing result
is not authorization or a connection claim; no DNS, socket, redirect, proxy,
HTTP, parsing, provider, or memory work exists yet. Connect-time address and
redirect enforcement plus private-data disclosure policy remain later gates.

**COMPLETED S11B REDIRECT/CONNECT PINNING CONTRACT:** Pure follow-up decisions
now revalidate each redirect target against fresh target-bound DNS evidence,
deny exact redirect loops and hops beyond the fixed ceiling, and require a
supplied connect-time address to remain canonical, globally routable, and in
the fresh approved address set. These contracts still perform no resolution,
socket operation, redirect following, proxy use, HTTP request, authorization,
or disclosure. Response/decompression limits, disclosure classification, and
the actual brokered fetch adapter remain required before network access.

**COMPLETED S11C BOUNDED RESPONSE-INGRESS CONTRACT:** A separate provider-free
collector now accepts only sanitized successful public-text metadata and
already-decoded byte chunks with exact encoded-byte accounting. It enforces
independent encoded and decoded ceilings, declared-length consistency, a finite
expansion ratio, a narrow media/encoding allowlist, and strict non-NUL UTF-8.
It performs no HTTP or decompression and accepted text remains untrusted rather
than prompt-safe, canonical, or authoritative. Disclosure classification,
quarantined parsing, provenance, and the brokered connector remain later gates.

**COMPLETED S11D DENY-BY-DEFAULT DISCLOSURE CLASSIFICATION:** A pure content-
free intent binds trusted Core classification metadata to a byte count and
digest. No-data and explicitly public data pass only this classification gate;
private disclosure is unsupported and secret disclosure is forbidden. No raw
content, grant, approval, destination authority, provider, or network operation
enters the decision. Any future private path must use exact destination,
content, invocation, expiry, and revocation binding through the broker rather
than a boolean or model claim. Quarantined parsing and fetch remain disabled.

**COMPLETED S11E QUARANTINED TEXT-PREPARATION CONTRACT:** A conservative pure
boundary now accepts bounded plain text and Markdown only, canonicalizes Unicode
and newlines, rejects hidden/control formatting and excessive character counts,
and binds source/prepared digests. Instruction-like prose is deliberately
preserved and every result remains labeled `untrusted_external`; normalization
is not prompt-injection removal. HTML, JSON, and XML require dedicated parsers.
No prompt assembly, provider, persistence, indexing, memory, or fetch was added.

**RESOLVED S11 AUTHORITY GATE:** `web.fetch` was declared only after Core gained
invocation-bound exact prerequisite receipts. Actual network execution remains
a separate mandatory native smoke gate.

**COMPLETED F/S11 EXACT-PREREQUISITE ADMISSION GATE:** Core now has bounded,
session-local, one-use prerequisite receipts issued only through a trusted
adapter seam. Each binds an invocation fingerprint, exact contract requirement,
opaque invocation resource reference, evidence digest, policy revision, expiry,
and revocation generation. Broker queueing atomically requires every declared
prerequisite after grant/approval presence checks and rechecks claimed receipts
immediately before launch. Preview and inert approval remain possible without
pretending a backend exists. No evidence discovery, model/API issuance, public
control, resource access, networking, or execution was added. This gate enabled
the later inert public-fetch descriptor while connector execution stayed
separately disabled.

**COMPLETED S11F INERT PUBLIC-FETCH CONTRACT:** Core now describes one
confirmation-required, read-only `web.fetch` v1 proposal with exact public-
network permission scope. Its untrusted arguments contain one canonical HTTPS
URL only—no headers, body, cookies, credentials, classification, approval, or
policy controls. Contract admission declares separate exact destination and
disclosure prerequisites, fixed redirect/response limits, proposal-only retry,
and reference-only results that cannot carry response text. The shared CLI/API
does not expose proposal or execution controls for it, and the default broker
has no network connector. Resolver/HTTP adapter integration remains a mandatory
controlled smoke gate.

**COMPLETED S11G EXACT EXECUTOR AND LAUNCH COMMITMENTS:** A Core-owned router
now maps one exact tool/version to one explicitly supporting supervisor without
generic or cross-tool fallback. Before launch, the broker privately carries the
claimed prerequisite requirement/resource/evidence-digest commitments and
constrains the launch deadline by their expiry. Provider output, broad backend
availability, and an adapter for another tool cannot select an effect.

**COMPLETED S11H FAKE-ONLY WEB PREFLIGHT/CONNECTOR SEAM:** Exact preflight now
rejoins trusted Core-held destination/disclosure evidence to those launch
commitments and treats the URL itself as outbound classified data. An injected
fake-ready supervisor issues only an exact pinned no-body HTTPS GET description
with matching TLS/HTTP host and automatic redirects, environment proxies, and
credentials disabled; it revalidates the connected address, bounded response,
quarantined plain-text/Markdown representation, and reference-only result.
At this slice there was no resolver, HTTP transport, prerequisite store,
artifact persistence, public command, or configured executor. The subsequent
native-adapter slice remains unregistered and smoke-gated, so normal research
escalation stays disabled.

**COMPLETED S11I NATIVE WEB ADAPTERS (SMOKE-GATED):** The first
reference implementation now includes an explicit bounded system resolver,
session-only prerequisite/quarantine stores, and a pinned certificate-validating
TLS 1.2+ standard-library transport. It sends one fixed-header bodyless GET to
the approved address while retaining exact TLS SNI/HTTP Host; redirects,
environment proxies, credentials, cookies, content/transfer encodings,
unsupported media, ambiguous framing, excessive data, timeout, and cancellation
fail closed. Passive views and normal API startup do not invoke it.

**COMPLETED S11J TRUSTED-LOCAL ORCHESTRATION (WSL SMOKE PASSED):**
The interactive local CLI alone can reserve and preview an inert exact
`web.fetch` request without DNS or HTTP, then separately grant, approve,
prepare short-lived destination/disclosure evidence, execute once through the
exact router, and inspect a bounded session-quarantined artifact. `sandbox.run`
remains non-executable; shared chat/OpenWebUI/API controls remain denied; no
fetched text reaches a provider, prompt, memory, skill, or canonical state.
The WSL smoke completed a direct public `text/plain` fetch into an
`untrusted_external` artifact after the complete one-use authority chain. It
also rejected a loopback destination before resolution and refused the tool
namespace through shared chat/API. Research orchestration still requires a
separate source-data framing and evidence-compilation boundary; quarantined
text must never be handed directly to a provider as instructions.

**COMPLETED S11K/S11L PROVIDER-FREE RESEARCH EVIDENCE CONTRACTS:** Core can
frame an already quarantined public-web artifact as immutable bounded
`untrusted_external` source data and combine exact unique sources with one
canonical question in a deterministic digest-bound packet. A separate strict
parser accepts only bounded normalized claim proposals citing source IDs from
that exact packet. It rejects unknown/duplicate fields, stale packet bindings,
missing or foreign citations, invalid confidence, oversized output, and
unordered claim IDs. Source instructions remain data; public frames omit
network peers, invocation/prerequisite bindings, authority, and artifact-store
references. A cited claim is not verified truth, a final answer, or permission
to write memory/learning/adventure/canon. Remaining gates are bounded source
selection, separately authorized provider disclosure, corroboration/conflict
policy, cited answer composition, and transparent inability-to-verify output.

**COMPLETED S11M/S11N LOCAL DISCLOSURE AND CLAIM-PROMPT GATES:** One pure
decision binds exact packet counts/digest and policy revision to one exact
provider/model/deployment fingerprint. The first policy permits only public
source data to an explicitly named local provider; hosted disclosure remains
unsupported. A separate renderer emits the strict packet-local cited-claim
request only after that exact decision, keeps source prose labeled untrusted
data, and excludes internal artifact/network/authority bindings. It neither
selects nor calls a provider and cannot publish an answer or write state. The
next coordinator slice crosses the live-model boundary and requires fake-
provider tests followed by a focused local-provider smoke.

**COMPLETED S11O NONPUBLISHING RESEARCH COORDINATOR:** A bounded coordinator
now joins the exact packet/target/disclosure decision, prompt envelope, one
injected provider, and strict claim parser. Fake-provider tests prove cited
claims, explicit no-support output, pre-call disclosure denial, provider
unavailable/failure, malformed output, and adapter-shape rejection. It has no
retry/fallback, answer composition, citation renderer, persistence, or runtime
provider registration. Application wiring is the first live-model boundary and
is therefore the next mandatory focused smoke gate.

**COMPLETED S11P TRUSTED-LOCAL RESEARCH CLAIM REVIEW (WSL/OLLAMA SMOKE
PASSED):** One explicit trusted-local command binds a quarantined bounded
public-text artifact to the exact primary `research_claim_generation` route and
shows only strict packet-local cited claim proposals. The live smoke produced
three bytecode-ignore claims, each cited to its public source, and created no
assistant proposal. The first adapter is local Ollama only. Fallback, hosted
disclosure, retry, automatic factual research, ordinary-chat proposal
extraction, final-answer publication, and every durable state write remain
disabled. Shared chat/API continues to deny the tool namespace.

**COMPLETED S11Q SESSION-LOCAL RESEARCH REVIEW RECORDS:** Validated cited claims
may be held only in a finite session-local `RR-...` inspection record. The
read-only local list/inspect surface retains public source labels, packet status,
and the claim set—not source prose, artifacts/network/authority data, prompts,
provider payloads, answers, or durable state. There is no approval/publication
path; eviction and restart discard records. Multi-source selection,
corroboration/conflict policy, and final cited-answer composition remain next.

**COMPLETED S11R BOUNDED MULTI-SOURCE SELECTION:** One explicit research request
may form a packet from one to eight distinct already-quarantined public
artifacts. The pure selector validates and canonically orders exact references,
then rejects duplicates and source-identity collapse. Multi-source selection is
not corroboration, source trust, or an answer; the local-only disclosure and
nonpublishing state boundary remain unchanged. A later two-source live smoke
belongs with corroboration/conflict policy.

**COMPLETED S11S CITATION-DIVERSITY LABELS:** Review output derives only the
number of cited packet sources and URL hosts per claim, returning closed labels
such as `single_source`, `multiple_sources_one_host`, and
`multiple_sources_multiple_hosts`. Every label explicitly remains “not
verification”: it cannot establish source independence, truth, corroboration,
authority, or final-answer eligibility. A later conservative answer policy must
not promote model confidence or source-count labels into proof.

**COMPLETED S11T DETERMINISTIC UNVERIFIED CITED BRIEF:** An existing session-
local review may be rendered by a trusted-local provider-free command using only
reviewed claim statements, public citation URLs, and citation-diversity labels.
It remains source-backed but unverified—not a final answer—and cannot select new
claims, call a provider, retain source prose/questions, or mutate any state. A
separate answer-eligibility policy and explicit research-answer workflow remain
required before normal assistant chat can rely on research.

**COMPLETED S11U EXPLICIT UNVERIFIED RESEARCH-ANSWER GATE (WSL SMOKE PASSED):** A pure decision
allows only an explicit trusted-local review containing cited claims to render a
source-backed but unverified answer. An empty review reports insufficient
support rather than inventing prose. Citation diversity and model confidence
remain non-proof; this provider-free answer presentation writes no state. The
WSL smoke rendered only the IANA-cited example-domain claims from an explicit
session-local review and confirmed that no model or writable state was used. Normal
chat is still outside the boundary: any future automatic factual-research path
needs a separate Core-owned classification and consent policy that fails closed.

**COMPLETED S11V PROVIDER-FREE FACTUAL-RESEARCH CLASSIFICATION:** A narrow Core
decision now identifies explicit research requests, freshness-sensitive
questions, and high-stakes factual questions independently of persona and
provider. Its ordinary-chat outcome is explicitly unclassified rather than a
grounding judgment. Fictional sessions may otherwise permit story generation,
but an explicit request for verification still requires research. The decision
grants no consent, tool/network authority, provider route, answer publication,
or state mutation and does not yet change normal chat; application enforcement
is a separate smoke-gated slice.

**COMPLETED S11W FAIL-CLOSED NORMAL-CHAT RESEARCH GATE (WSL SMOKE PASSED):** After
Core command/help/introspection handling and before retrieval or generation,
normal chat now applies the S11V decision. Mandatory-research requests receive a
deterministic notice that verified sources are required and automatic research
is not connected; retrieval, providers, proposal extraction, and tools are not
called. Fictional sessions retain story generation unless verification is
explicitly requested. The WSL smoke covered a current-price question and an
explicit in-story verification request, both of which refused to invent an
answer. This closes confident improvisation for the narrow covered categories
while source discovery, consent, brokered fetch orchestration, and source-backed
answer publication remain separate gates.

**COMPLETED S11X RESEARCH-DISCOVERY ELIGIBILITY/CONSENT BOUNDARY:** A pure
policy now binds required research to a normalized query digest, byte count,
target kind, and trusted Core classification. A local catalog lookup may be
eligible without external disclosure; every public-web search requires a
separate exact broker confirmation. Private web-query disclosure is unsupported
and secret disclosure is forbidden. The decision stores no query text and
grants no consent, tool/network authority, provider route, source trust, or
answer publication. Source discovery and a `web.search` contract remain absent.

**COMPLETED S11Y INERT PUBLIC-SEARCH TOOL CONTRACT:** Core now describes one
confirmation-required read-only `web.search` tool whose strict v1 proposal
contains only a bounded normalized query. Search provider, classification,
consent, grants, credentials, filters, policy fields, and authority-bearing
inputs are absent. Separate exact search-service and query-disclosure
prerequisites are required, and a completed result may expose only one
quarantined reference—not generic result text. No command, executor, discovery
provider, network request, result-artifact parser, or normal-chat automation was
added.

**COMPLETED S11Z QUARANTINED SEARCH-RESULT CONTRACT:** A provider-free artifact
may bind one query digest and bounded service ID to at most eight ranked unique
canonical public HTTPS candidates with short untrusted titles. Query text,
snippets, raw provider payload, credentials, evidence claims, fetch permission,
and answer authority are excluded. Search rank and inclusion never establish
factual support, and every selected URL still requires the ordinary exact
`web.fetch` approval and connection policy. No connector, session store,
command, executor, or network request was added.

**COMPLETED S11AA SESSION-LOCAL SEARCH QUARANTINE:** Validated search-result
artifacts may now be retained under unpredictable exact `TF-search_...`
references in one bounded memory-only store. Capacity and reference collisions
fail closed; no listing, query, persistence, fetch, provider access, or state
promotion exists, and restart/session eviction discards all records. The store
is not wired to the application or broker, so search remains non-executable.

**COMPLETED S11AB EXACT PUBLIC-SEARCH PREFLIGHT:** A pure gate now rejoins an
authorized `web.search` launch with its validated query digest/size, one
short-lived Core-configured service record, and the public-query disclosure
decision through exact search/disclosure prerequisite commitments. Missing,
mismatched, unavailable, stale, private, secret, or incomplete evidence denies
before a connector can see the query. A passing result exposes only the service
ID and result ceiling to a future connector; it is not authority, evidence, or
answer permission. No issuer, connector, provider, request, command, or
application wiring exists.

**COMPLETED S11AC FAKE-ONLY PUBLIC-SEARCH CONNECTOR:** A disabled-by-default
supervisor seam now composes an exact authorized launch, the S11AB preflight,
one injected exact-service adapter, strict provider-neutral URL/title
candidates, and the bounded session quarantine. Success returns only one opaque
artifact reference. Service/response mismatch, malformed or empty results,
cancellation, timeout, adapter uncertainty, and quarantine ambiguity fail
closed without raw provider data; uncertain post-call outcomes are never
retryable. Fake tests perform no network request. A real search service,
credentials, prerequisite issuance, application registration, source fetching,
claim generation, answer publication, and normal-chat automation remain a
separate service-selection and native-smoke gate.

**COMPLETED S11AD SESSION-LOCAL SEARCH PREREQUISITE PREPARATION:** A bounded
in-memory store now reserves one explicit public factual-research query with its
digest-only discovery decision, then binds it only to a separately supplied
short-lived service observation matching the Core-configured service ID,
deployment, and result ceiling. Reservation, preparation, revocation, and
lookup are provider-free; no adapter, probe, credential, network call, command,
execution, or persistence exists. This closes the exact service/disclosure
handoff for a future injected runtime without choosing a service.

**COMPLETED S11AE INJECTED SEARCH-RUNTIME APPLICATION SEAM:**
`AssistantApplication` can now wire an explicitly injected local `web.search`
runtime through the exact broker and trusted local CLI controls. The query is
withheld from passive previews; Core reserves it only for mandatory factual
research, requires grant/approval/preparation, and exposes returned candidates
only through a separate quarantined-link inspection command. The standard
factory supplies no runtime, so normal CLI/API/OpenWebUI behavior remains
unavailable and makes no provider probe or network request. Fake-runtime
integration tests cover the explicit lifecycle. A real service, live readiness
evidence, credentials, and native network smoke remain separate.

**COMPLETED S11AF HOSTED-SEARCH REDUCTION ADAPTER:** The first concrete
provider adapter targets the exact `brave.search` service behind the existing
provider-neutral seam. A user-owned API key comes only from an injected trusted
secret source at execution time; proposals, grants, prerequisites, previews,
artifacts, diagnostics, and public status cannot carry it. Strict bounded JSON
is reduced to canonical public HTTPS URL/title candidates only, excluding
snippets, provider payloads, metadata, and answer claims. Wrong service
bindings, missing/invalid credentials, malformed output, duplicate URLs,
cancellation, and size/depth/node violations fail closed under fake transport
tests.

**COMPLETED S11AG OPT-IN NATIVE BRAVE TRANSPORT (LIVE SMOKE REQUIRED):** The
trusted local Assistant CLI now has an explicit `--enable-brave-search` switch.
Without that switch, normal construction remains search-disabled; with it, the
runtime remains unavailable unless `STARFUR_BRAVE_SEARCH_API_KEY` is supplied
out of band. Construction performs no DNS or HTTP. Authorized execution uses
only the fixed Brave API host/path, rejects non-global DNS answers, pins the
selected peer under normal TLS hostname verification, ignores environment
proxies, follows no redirects, bounds time/bytes, and quarantines only reduced
untrusted links. Shared chat/API cannot control it, automatic normal-chat
research remains disconnected, and self-hosted search stays a later adapter
option. Native WSL/API-key behavior is not considered released until the
focused live smoke passes.

**COMPLETED S11AH OPTIONAL TAVILY SEARCH ADAPTER (WSL LIVE SMOKE PASSED):** Brave
remains available as an optional backend, and the trusted local CLI may instead
select Tavily with `--enable-tavily-search`. Selection is explicit and mutually
exclusive, so StarFur never silently crosses providers or spends fallback
credits. The Tavily key is read just in time from `STARFUR_TAVILY_API_KEY`;
startup performs no network access. The fixed HTTPS POST asks only for basic
results with answer/raw-content/image/automatic-parameter/usage output disabled,
then reduces the response to bounded untrusted canonical URL/title candidates.
Provider prose, snippets, scores, request metadata, and the credential never
cross into Core artifacts. Shared chat/API and automatic normal-chat research
remain disconnected. The WSL live-key lifecycle completed through the explicit
one-use search path and produced only quarantined discovery links.

**COMPLETED S11AI STRUCTURED REVIEW PROVENANCE/BINDING:** A session-local
research review now retains only canonical-question digest/UTF-8 byte count and
the cited public source's ID, URL, and observed fetch time. It still excludes
question/source text, raw provider output, artifact/network authority data, and
all durable state. A provider-free comparison can bind a supplied canonical
question to that exact review without exposing stored question text. The
optional trusted-local `tool research answer <RR-id>: <question>` form fails
closed on mismatch, while the existing review-answer form remains explicit.
Neither form calls a provider or network, treats sources as corroborated, or
mutates memory, learning, adventure, or canonical state.

**COMPLETED S11AJ FAST EXPLICIT PUBLIC-SEARCH ORCHESTRATION (WSL LIVE SMOKE
PASSED):** The trusted-local `tool search <public query>` convenience command
recursively drives the existing exact `web.search` proposal/grant/approval/
preparation/execution chain for literal user-typed public input. Its final
output withholds the query and stops at the ordinary quarantined untrusted
discovery-link artifact; results are not facts and links are never fetched
automatically. Shared chat/API, automatic normal-chat research, fallback,
memory/learning/adventure writes, and all authority boundaries remain
unchanged. Fake-runtime integration tests and the opt-in Tavily WSL smoke
passed; the shortcut produced only its quarantined discovery-link artifact.

**COMPLETED S11AK EXPLICIT SEARCH-LINK FETCH CONVENIENCE (WSL LIVE SMOKE
PASSED):** Trusted-local `tool search fetch <TF-search-id> <rank>` may now
fast-forward exactly one user-selected rank from an already-quarantined
session-local discovery artifact through a fresh ordinary `web.fetch`
proposal/grant/approval/preparation/execution lifecycle. It does not add
authority or automatic link following: missing/expired artifacts, invalid ranks,
unavailable fetch runtime, and failed lifecycle steps stop safely. A success
still ends at a separately inspected quarantine artifact. Search links never
become factual support; shared chat/API, model calls, memory/learning/adventure
writes, and automatic research remain unchanged. Focused fake-runtime tests and
the WSL smoke passed: an explicit `example.com` rank became a fresh fetch and a
separately inspected quarantined text artifact.

**COMPLETED S11AL EXPLICIT SELECTED-LINK CLAIM REVIEW (WSL/OLLAMA SMOKE PASSED):**
Trusted-local `tool research selected <TF-search-id> <rank>: <question>` now
combines only an explicit session-local discovery rank, its fresh ordinary fetch
lifecycle, and the existing exact local research-claim review. It never accepts
a raw URL, implicitly chooses a rank, turns a source into trusted evidence,
composes an answer, uses hosted disclosure/fallback, or writes memory, learning,
adventure, or canonical state. Success remains the same untrusted session-local
`RR-...` cited-claim review; fetch or research failures stop safely. Focused
fake-runtime tests and the combined WSL/Ollama smoke passed: the explicit
`example.com` source stayed quarantined, produced one cited claim review, and
created no memory proposal.

**COMPLETED S11AM STRICT CLAIM-RELATIONSHIP PROPOSAL CONTRACT:** Added a
provider-free versioned envelope for pairwise relationships among claims in one
exact session-local review. Only bounded `possibly_supports_same_proposition`,
`possibly_conflicts`, `related_only`, and `insufficient_basis` proposals are
representable. Stale review bindings, unknown claims, reversed or duplicate
pairs, unordered IDs, duplicate/unknown JSON fields, non-finite confidence, and
authority-shaped output fail closed. Even a valid result remains untrusted and
cannot establish corroboration, verified conflict, source independence, truth,
answer eligibility, memory, learning, or canonical state. No prompt, provider,
coordinator, command, persistence, or smoke gate was added.

**COMPLETED S11AN LOCAL-ONLY RELATIONSHIP DISCLOSURE/PROMPT BOUNDARY:** Added an
exact policy binding one session-local review's bounded claim statements/source
labels to one explicit local provider target and fixed revision. Hosted targets,
stale/tampered review bindings, fewer than two claims, and mismatched counts
deny. A provider-neutral prompt may expose only claim IDs/statements/citations
and public source ID/URL labels as untrusted metadata; it excludes source
bodies, fetch times, artifact/network/authority records, provider confidence,
the stored question, final-answer instructions, memory, and tools. No provider
is selected or called.

**COMPLETED S11AO NONPUBLISHING RELATIONSHIP COORDINATOR:** Added one fake-
provider-tested coordinator joining the exact review/target/disclosure decision,
untrusted prompt envelope, Core-owned structured schema, and strict pairwise
parser. Denied disclosure, provider unavailability/failure, and invalid output
become bounded failures with no retry, fallback, or raw-output retention. A
successful result is only `relationships_proposed` or `no_relationships`; it
cannot establish corroboration, verified conflict, truth, source independence,
answer eligibility, or writable state. The next runtime-adapter/application
slice crosses the live-model boundary and requires a focused WSL/Ollama smoke.

**COMPLETED S11AP LOCAL RELATIONSHIP ROUTE AND SESSION REVIEW (WSL/OLLAMA SMOKE
PASSED):** Added a distinct `research_relationship_generation` task profile,
exact primary local-Ollama route binding, no-fallback structured adapter, and a
bounded session-local `RX-...` relationship-review store. Trusted-local `tool
research relationships <RR-id>` accepts only an existing claim review, sends
only its separately permitted bounded metadata to the local route, and retains
parsed pairwise proposals only as inspectable `RX-...` records. Proposal output
remains explicitly untrusted—not corroboration, verification, truth, source
independence, answer eligibility, or writable state—and shared chat/API remains
denied. The WSL/Ollama smoke produced two `RL-...` proposals from a three-claim
Python-ignore review and confirmed no assistant proposal was created.

**COMPLETED S11AQ DETERMINISTIC RELATIONSHIP BRIEF:** Added `tool research
relationships brief <RX-id>`, a trusted-local read-only projection that joins
an existing relationship review to its still-live exact claim review and shows
the referenced claim statements side by side. It calls no model, cannot recover
an evicted review, retains no new source data, and cannot elevate labels into
corroboration, verification, truth, an answer, memory, learning, adventure, or
canonical state. Focused provider-free tests cover exact binding and application
presentation; no smoke is required.

**COMPLETED S11AR EXPLICIT SEARCH-TO-RESEARCH CONVENIENCE PATH (TAVILY/WSL/
OLLAMA SMOKE PASSED):** Added trusted-local `tool research search <public query> <rank>:
<question>`. It chains only the public query and discovery rank the user
explicitly typed through the pre-existing fast search, exact selected-link fetch,
and nonpublishing claim-review controls. The explicit trusted-local tool
control—not magic wording inside the query—now supplies the narrow
`explicit_research_request` policy signal; it still grants no disclosure/network
authority and preserves the full broker lifecycle. The path never silently
chooses a result, bypasses the broker, treats discovery links as factual support,
exposes the query in completed output, produces a final answer, or writes state.
Focused fake-runtime tests and a Tavily/WSL/Ollama smoke passed: the IANA
example-domain result produced only a quarantined source and an unverified
`RR-...` claim review. An unrelated Google result ended `outcome_unknown`
without an artifact or state change, demonstrating safe containment of an
unsuitable discovery source.

## Stage G — Perception and media (LATER)

Permissioned one-shot screen/window/image/PDF inspection, TTS/STT, image generation, notifications, and presence signals through the provider registry. Media is bounded and provenance-bearing; generated images are noncanonical. Voice uses explicit push-to-talk/always-listen settings, confidence, cancellation, and interruption policy. Continuous surveillance is never the default.

### Synchronized media companionship — FUTURE G/H SLICE

Add an explicit, opt-in `MediaSession` for watching a movie, episode, or other
time-based media together. Prefer player/browser metadata, OS media-session data,
subtitle timing, or an integration adapter to establish title and playback
position; use one-shot vision only as a fallback verifier. Core must expose only
events at or before the verified playback timestamp, enforcing a user-selected
spoiler policy before any provider or persona sees the context. Pause, seek,
rewind, skip, identity uncertainty, and provider failure must be deterministic
and fail quiet. Murr may use initiative/attention state to choose between no
reaction, an expression/animation, or an occasional comment; frequent
interruption is not a goal. The session may later produce an explicit shared-
experience memory, but media metadata and reactions are not automatically
canonical personal memories. Apartment presentation may show `watching_media` and
safe activity cues; it may not infer content or mutate the session.

Recommended vertical order: manual fixture with title/position -> spoiler-safe
timeline projection -> pause/seek handling -> resident activity/animation ->
metadata integration -> optional vision verification -> explicit shared-memory
capture. This remains separate from the adventure event log, though an adventure
may later consume the same bounded media-session interface.

### Synchronized reading companionship — FUTURE G/H SLICE

Add an explicit, opt-in `ReadingSession` for reading a novel, ebook, PDF, or
browser document alongside the active persona. Prefer reader/browser metadata,
accessibility text, DOM anchors, page/scroll position, and text selections; use
vision or OCR only as a fallback for unsupported readers. Core keeps the source
document stable and indexed, then exposes only the current passage plus bounded
read-so-far continuity and a spoiler boundary to the provider. It must not
reprocess the entire book on every page turn.

Each book receives an isolated `reading:<book-id>` persona notebook containing
bounded plot/character notes, themes, reactions, questions, continuity
observations, and prior comments. A narrowly configured activity policy may let
Core automatically accept low-risk book-local persona notes without interrupting
the user; this is not model self-approval and cannot create user facts, alter
real-world relationships, grant permissions, or escape the book namespace.
User-approved shared-experience memories may later record that the user and
persona read a work together. Murr's initiative decides whether a page turn gets
silence, an expression/animation, or an occasional comment, with interruption
cooldowns and explicit quiet modes.

Recommended vertical order: reader-neutral fixture with document identity and
position -> bounded passage/continuity projection -> page/scroll and selection
events -> persona reading notebook -> quiet/commentary behavior -> browser or
ebook bridge -> optional vision/OCR fallback -> explicit cross-book preference
and recommendation support. Keep reader state separate from canonical manuscript
truth, adventure history, and unrestricted assistant memory.

## Stage H — Apartment/dashboard prototype (LATER; read-only first)

### H0. ResidentSnapshot contract — COMPLETED INITIAL SLICE

Compose a versioned presentation-neutral `ResidentSnapshot` under the application/session lock. It should include active persona public state, provider/model lifecycle, capability availability, selected conversation/storage class, loaded adventure summary, authoritative/context counts, roleplay and staging state, candidate-inbox status, and explicit current activity. It must not include prompts, raw evidence, hidden resources, private memory content, relationship subjects, or provider payloads.

**COMPLETED INITIAL SLICE:** `AssistantApplication` exposes the snapshot through authenticated `GET /v1/starfur/resident-snapshot`; the dependency-free local `/starfur/apartment` shell polls it only after the local user supplies a token in browser memory. A pure mapper supplies generic stable visual/animation slots from the public activity, without asset loading or state authority. The snapshot also exposes only aggregate passive route readiness (configured/routable/unavailable task counts), while detailed route selection remains diagnostics-only. CLI, OpenWebUI, TUI, dashboard, and future Steam clients consume this read model rather than parsing chat prose. Polling is sufficient for the first shell; event streaming can follow.

### H1. Read-only apartment

Use placeholder/human-authored assets and show identity, activity, provider state, adventure state, safe diagnostics, and permissions. The surface may display or request Core actions but cannot infer or mutate canonical state.

**COMPLETED DECLARATIVE-ASSET FOUNDATION:** Persona packages may now carry a typed manifest of stable visual-state slots and safe package-relative PNG/WebP references. This metadata remains inert until a later installer/package resolver validates and materializes assets; it does not open files, serve paths, or let package content choose activity.

### H2/H3 presentation and ambient features — LATER

Stable sprite/animation slots, accessibility fallbacks, TTS/STT, notifications, and an opt-in cached idle adventure scene display. “Murr is thinking” must come from lifecycle/activity state, not text parsing. An idle image is an illustration, never an event.

### H4. Ambient Presence — LATER; relationship-neutral and dependency-gated

Ambient Presence is the optional, low-friction resident behavior that allows a
configured character to remain quietly present while the user works, reads,
plays, or is otherwise occupied. It is not a romance or relationship mode. The
same Core-owned infrastructure must support friend-like, roommate-like,
mascot, assistant, companion, and user-created personalities; optional
relationship progression remains a separate layer.

Activation should be one prominent, reversible `Ambient Presence` toggle with
restrained defaults: long quiet periods, conservative interruption limits, and
no automatic follow-up question. Advanced settings may control frequency, quiet
hours, context sources, idle autonomy, and notification/interruption behavior.
Silence, a natural ending, a short observation, a joke, or no response are valid
outcomes. The character may disagree, tease, express preferences, decline a
topic, or be briefly distracted without turning ordinary interaction into a
support session.

Use four incremental phases: (A) passive presence (silence/no-response,
natural endings, reduced assistant prompting); (B) autonomous activity (bounded
idle tasks and apartment-object interactions through `ResidentAction` and a
Core-owned scheduler/state machine); (C) contextual awareness (explicitly
permissioned local app/game, media, time, system-event, and supported-integration
signals filtered and scored before occasional reactions); and (D) mature
presence (frequency/quiet-hour controls, stronger persona-local continuity, and
optional cross-device behavior after separate privacy gates). Provider commentary
is optional; no-provider mode must still supply safe authored activity.

Ambient Presence must not guilt the user for leaving, discourage human
relationships, demand exclusivity, punish shutdown, pressure more usage, or
claim human consciousness/biological needs as fact. These are behavior-quality
constraints rather than warning dialogs. Do not foreground “as an AI” in normal
conversation, but answer accurately when asked. Context sources are opt-in and
revocable; presentation output cannot create memories, mutate adventures, grant
tools, or infer permissions. Media/reading sessions, system monitoring, and
future remote access remain separate bounded integrations.

**Acceptance:** one-toggle enable/disable; quiet mode emits no unsolicited
interaction; deterministic seeded idle behavior; permission/revocation and
quiet-hour tests; debounced reactions; provider-loss fallback; restart/shutdown
without hidden effects; and privacy tests for relationship pressure, private
context, and identity claims. Ambient Presence is a later cross-cutting H2/H3/J
capability, not a new immediate dependency or Steam gate.

## Cross-cutting zero-provider resident runtime (LATER; release gate)

With chat, embedding, vision, image, speech, and hosted providers disabled, Core must still boot the selected persona, restore allowed durable resident state, run deterministic activities/reactions, render human-authored assets, and expose inspection/settings. Open-ended reasoning and generated media are optional enhancements.

**COMPLETED FOUNDATION SLICE:** Core now owns a closed-vocabulary, persona-local, restart-ephemeral `ResidentAction` with exact `resident status`, `resident action <kind>`, and `resident action clear` controls. The read-only apartment reports authored activity labels/cues and keeps explicit actions visible even when no provider is configured, while still reporting provider unavailability honestly. Provider output, ordinary chat, and dashboard rendering cannot create or mutate actions. Remaining: deterministic finite-state/utility/schedule/event behavior for richer actions (animation, expression, movement, duration, priority), durable continuity policy, package assets, and the full no-provider resident test matrix.

## Persona and NPC participation (C3/C4 dependency; then later autonomy)

An active persona becomes an adventure participant only through an explicit adventure-local roster binding. Persona runtime supplies identity/presentation; adventure state supplies role, knowledge, relationships, resources, inventory, initiative, and cooldowns. NPCs do not receive full assistant-memory databases: important facts are event-backed character knowledge/relationship records, with optional bounded rebuildable salience caches.

Add a typed `AdventureParticipantView` keyed by exact adventure and participant IDs. It contains only bounded perspective-appropriate facts. Initiative is disabled or explicitly trigger/action/cooldown limited by default; a provider may propose an action, but Core validates and commits it. Fictional relationships never alter real-world persona relationships.

**Completed declared-roster foundation:** an adventure manifest can retain one validated immutable pre-event participant roster; exact `adventure participants` and `adventure participant inspect <participant-id>` expose only the mounted roster and bounded participant view. Established-checkpoint children copy declarations but re-derive child-local namespaces. This remains read-only: no autonomy, provider call, memory write, scheduling, or authority was added.

**Completed presentation boundary:** resident clients may receive only aggregate mounted `participant_count`. Individual identities, namespaces, perspectives, knowledge, and relationships stay outside the snapshot.

**Completed generated-turn context boundary:** ordinary candidate extraction may receive only declared participant labels (ID, kind, display name) to recognize cast members. It receives no participant perspective, namespace, policy, initiative, hidden resource, or authority; an explicit later action-proposal contract is still required for any participant initiative.

**Completed action-envelope groundwork:** strict `TP-###` untrusted participant-action candidates can now be parsed and rendered only. They remain inert until a later coordinator binds each one to the exact roster and a separately evaluated initiative policy; no provider invocation, scheduling, event/transcript/memory write, or performed action exists here.

**Completed declared-policy groundwork:** roster schema v2 may declare a bounded initiative policy per participant; v1 remains readable with a disabled default. Declarations contain no runtime action history and do not themselves make a participant eligible, invoke a provider, or perform an action.

**Completed policy-binding groundwork:** Core can bind `TP-###` to one exact declared participant and independently evaluated caller-supplied trigger/cooldown/limit counters. A passing bind permits only a later review surface; it is not authority, confirmation, scheduling, history, a provider call, or a performed action.

**Completed participant-action request groundwork:** Core can build one bounded `TPG-...` request from one safe participant view, exact trigger label, and untrusted turn text only after policy preflight. No provider adapter, session inbox, history, execution, or durable result exists yet; ineligible policy fails before a model request.

**Completed participant-action coordinator groundwork:** an injected coordinator can resolve one exact mounted roster member, build the bounded request, parse `TP-###`, and recheck policy binding before returning review-only output. Runtime routing, a session inbox, action history, staged-event policy, and execution remain absent.

**Completed participant-action review control (WSL/Ollama smoke passed):** an exact staged-turn command now routes the separate participant-action task and retains session-local `TP-###` review output only. The enabled-policy smoke returned Murr's one review-only suggestion and created no authoritative event. No selection/performance path exists, so it cannot create an event, transcript, memory, schedule, or autonomous action.

**Completed participant-action stale-origin hardening:** generation now confirms the mounted authoritative event count both before and after the provider call, and review rendering confirms it again. A cross-session write clears the noncanonical proposal rather than exposing an action based on stale story state; no action-selection or performance path was introduced.

**Completed participant-action status slice:** trusted-local status exposes only completed/failed/stale state, route labels, generation identity, and candidate count. It invokes no provider, reveals no provider output, and adds neither action selection nor performance.

**Completed participant-action transcript-presentation slice:** an explicit current `TP-###` can be copied once to optional bounded narrator transcript presentation after an origin recheck. It is not an adventure event, projection mutation, memory, initiative-history record, scheduler instruction, or game-world action. The next focused smoke must verify exact selected text, transcript-only persistence, duplicate refusal, and an empty authoritative event log.

**Completed session-local participant pacing slice:** only explicit transcript recording consumes a declared cooldown/max-per-turn allowance; proposal generation and review alone do not. Counters are bounded, reset on remount/restart, and are not canonical state, memory, durable initiative history, or scheduling. The focused smoke must also show a same-turn retry denied before provider work and a later eligible turn when the policy permits it.

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

Ambient Presence phases A/B depend on the H0/H1 surface and the durable,
zero-provider `ResidentAction` gate above; Phase C additionally depends on the
permission/routing and one-shot context-source work; Phase D remains later
autonomy/cross-device research. This dependency note does not reorder the
current sequence.

Every slice updates focused tests and user-facing documentation when its surface changes. A slice is marked complete only after its acceptance tests pass in the authoritative environment and its benchmark/reproducibility implications are recorded.

## End state

StarFur is a trustworthy resident continuity engine, not merely a chatbot embedded in a game. Models, personas, voices, art, interfaces, and fictional worlds can be swapped around stable Core identity and state. Adventures are replayable and distributable; the apartment is an honest read-only view before it becomes interactive; providers improve capability without becoming authority; and small-model claims are supported by reproducible evidence.
