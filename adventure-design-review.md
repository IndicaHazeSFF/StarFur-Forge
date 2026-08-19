# StarFur Forge Stage 5A Adventure Design Review

**Review date:** 2026-08-18  
**Scope:** static repository inspection of the current CYOA/adventure subsystem  
**Change discipline:** review only; no source, runtime data, database, existing roadmap, staging, or dependency changes

## Executive assessment

The current adventure subsystem is a credible, testable foundation. It already separates a registry, validated event history, deterministic replay selection, derived state, mounted model context, and explicit session-local staging. The recent transaction smoke test also demonstrated that staged ordinary events remain invisible until commit and are discarded on abort.

It is not yet safe to treat the subsystem as an automatic narrator/state engine. Three boundaries must be completed first:

1. complete authoritative projections must be separated from bounded model projections;
2. workspace writes need concurrency, idempotency, and crash-recovery semantics;
3. every structured mutation associated with one generated turn must share one transaction.

No P0 issue was identified in the currently explicit, local prototype. Several P1 issues become release/data-integrity risks as soon as multiple API conversations or automatic event extraction can write the same workspace.

## Review method and evidence rules

- Source and tests are treated as evidence of implementation.
- `AGENTS.md`, `ROADMAP.md`, `CHANGELOG.md`, and command documentation are treated as intended architecture when they exceed current code.
- No live provider, embedding service, media service, production database, Chroma collection, or runtime adventure data was invoked.
- The worktree was already heavily dirty before this review. Existing modifications and untracked files were preserved.

## Observed implementation

### Registry and workspace identity

- `pipeline/adventure_registry.py:AdventureRegistry` stores a global `registry.json` and creates `adventures/<stable-id>/manifest.json` using normalized exact titles and title-derived stable IDs.
- `AdventureRegistry.resolve_title()` is exact and never silently creates a world.
- The manifest advertises event-log, database, and semantic-index slots, but only the event log can currently become initialized. Tests in `tests/test_adventure_registry.py` explicitly verify that no database or semantic index is created.

### Event history

- `pipeline/adventure_events.py:AdventureEvent` defines schema-v1 events with sequence IDs, closed event types, bounded summary/details, and optional structured state, relationship, or character-knowledge fields.
- `AdventureEventLog.events()` validates every JSONL line and contiguous sequence and fails closed on corruption.
- `AdventureEventLog.append_many()` validates at most sixteen drafts, rewrites the existing logical history into a `.pending` file, flushes/fsyncs it, and replaces `events.jsonl` in one ordinary success path.
- The storage is logically append-only because public operations do not delete or revise prior events. It is physically rewritten on every batch append.
- The only accepted source is `core_explicit`; no provider or ordinary narration writes the log.

### Replay and projections

- `pipeline/adventure_replay.py:select_replay_spine()` deterministically selects at most eight events by preserving the first event, the latest event from continuity categories, and recency, then restores chronology.
- `pipeline/adventure_state.py:derive_adventure_state()` applies latest-value-wins per state key.
- `pipeline/adventure_relationship.py:derive_adventure_relationships()` applies latest-value-wins per case-folded character/dimension pair.
- `pipeline/adventure_knowledge.py:derive_adventure_knowledge()` applies latest-stance-wins per case-folded character/fact pair.
- All three projection functions apply their twelve-fact context limits during derivation rather than after creation of a complete projection.

### Mounted context and commands

- `pipeline/adventure_session.py:AdventureSessionState.mount()` reads validated events and stores a bounded replay spine plus bounded state, relationship, and knowledge tuples.
- `AdventureSessionState.context_text()` labels these sections as Core-provided and distinguishes character perspectives from objective truth.
- `pipeline/assistant.py:AssistantSession` exposes registry, mount, lifecycle, inspection, immediate structured-state commands, explicit event recording, and turn staging commands.
- Exact commands execute before model generation when recognized. A malformed reserved command that does not match a known prefix may still return `None` from `command()` and fall through to model generation in `respond()`; the smoke test phrase `adventure turn state discovery: ...` demonstrated this behavior.
- `pipeline/context.py:ContextManager` receives one bounded adventure section; it does not query or mutate adventure storage.

### Turn staging

- `pipeline/adventure_turn.py:AdventureTurnTransaction` is immutable and session-local. It stages at most sixteen `AdventureEventDraft` objects.
- `AssistantSession.adventure_turn_commit()` passes the batch to `AdventureEventLog.append_many()`, then remounts the log. Abort and workspace transitions discard staging.
- The transaction currently stages only ordinary event drafts accepted by the generic stage command. State, relationship, and knowledge commands remain immediate writes.
- Generated assistant turns do not yet participate in this transaction, so automatic narrative extraction has not been implemented.

### Current tests

Focused tests cover:

- registry creation, exact resolution, duplicate rejection, and invalid titles (`tests/test_adventure_registry.py`);
- lazy event logs, validation, sequence corruption, and registry binding (`tests/test_adventure_events.py`);
- deterministic replay selection (`tests/test_adventure_replay.py`);
- latest-value state, qualitative relationship, and character-knowledge projection (`tests/test_adventure_state.py`, `tests/test_adventure_relationship.py`, `tests/test_adventure_knowledge.py`);
- session-local staging, batch commit, and abort (`tests/test_adventure_turn.py`);
- command precedence, no-model writes, mount context, lifecycle, structured facts, numeric-memory redaction, and transaction commands (`tests/test_adventure_commands.py`).

These tests establish the explicit prototype mechanics. They do not yet establish concurrent-writer safety, crash recovery, idempotent retry, complete state beyond context limits, branch semantics, automatic extraction accuracy, or long-session consistency.

## State-layer assessment

The design needs four distinct layers before automatic narration or simulation:

| Layer | Meaning | Authority | Current status |
|---|---|---|---|
| Transcript | what the user and narrator were shown | historical presentation only | not stored by the adventure subsystem |
| Canonical event log | validated facts/mutations that happened | authoritative audit history | implemented as schema-v1 JSONL |
| Full current projection | complete world truth rebuilt from active event semantics | authoritative derived state | partial; derivation is currently context-capped |
| Narrative/context projection | selected facts supplied to a model for one task | non-authoritative bounded view | implemented in initial form |

Optional snapshots may later accelerate reconstruction, but they must be versioned, checksummed, and disposable. Semantic/narrative memory may help select history for a scene, but it must never reconstruct money, ammunition, inventory, health, location, quest status, or other volatile truth.

### Is the event representation conflating concerns?

Partially.

`AdventureEvent` currently contains audit metadata, narrative summary/details, and structured mutation fields in one flat record. This is acceptable for the explicit prototype, but extending the flat dataclass for every new resource risks turning the event schema into a growing union with ambiguous validity rules.

The minimum separation is incremental:

```text
EventEnvelope
  event_id / sequence / schema_version
  recorded_at / source / turn_id / idempotency_key
  event_kind
  narrative_summary (optional presentation/history)
  mutation: one validated typed payload (optional)
  supersedes_event_id (optional explicit correction)
```

Core then folds active mutation payloads into a complete `AdventureWorldState`. A separate selector creates `AdventureContextProjection` for the provider. Narrative summaries remain useful replay evidence but are not parsed to obtain state.

This can be introduced as a schema-v2 reader/writer while retaining schema-v1 compatibility. A broad storage rewrite or immediate database migration is not required.

## Risk findings

### P0 — none observed in the constrained prototype

The current subsystem requires explicit Core commands and does not automatically execute tools or write extracted model claims. That limits present impact. P0 should be reconsidered once automatic writes, Workshop ingestion, external tools, or background simulation are enabled.

### P1 — authoritative projection is currently context-capped

**Evidence:** `derive_adventure_state()`, `derive_adventure_relationships()`, and `derive_adventure_knowledge()` each return at most twelve facts. `AdventureSessionState.mount()` stores those tuples as both current state and model context; `AssistantSession.adventure_state()` and diagnostics inspect the same bounded tuples.

**Impact:** the thirteenth distinct state key is still in the event log but disappears from the mounted “current state.” Context-budget changes can therefore alter what Core appears to know. This is unacceptable for inventory, currency, ammunition, health, objectives, or simulation.

**Recommendation:** build complete projections first, then apply separate deterministic selectors for model/UI context. Expose total and selected counts separately.

### P1 — independent writers can lose committed events

**Evidence:** `AdventureEventLog.append_many()` reads the complete file, assigns sequences, and replaces it without a workspace lock or compare-and-swap generation. `AssistantApplication` serializes a single conversation, but different conversations may proceed concurrently and mount the same workspace.

**Impact:** two writers can read the same head, produce identical next sequences, and let the last replacement discard the other batch.

**Recommendation:** add a workspace-level writer coordinator/lock plus expected-head or generation validation. The mechanism must work beyond one `AssistantSession`; document platform limits if the first implementation supports one host process only.

### P1 — event commit and manifest update are not one recoverable operation

**Evidence:** `append_many()` replaces `events.jsonl` and then calls `_mark_manifest_initialized()`. The manifest is written directly with `write_text()`. Registry creation likewise creates a workspace/manifest before rewriting the global registry.

**Impact:** an event can be durably present while the operation reports failure because the manifest update failed; retry can duplicate it. A crash during manifest/registry write can corrupt metadata or leave an orphan workspace.

**Recommendation:** introduce idempotency/commit IDs, atomic metadata replacement, startup reconciliation, and failure-injection tests. Treat event-log presence as discoverable evidence during reconciliation instead of trusting one marker blindly.

### P1 — one semantic turn cannot yet commit all structured effects atomically

**Evidence:** the turn transaction accepts generic `AdventureEventDraft` instances, while `adventure state set`, `adventure relationship set`, and `adventure knowledge set` append immediately through separate commands.

**Impact:** future automatic extraction could persist a narrative event but fail before its state/resource/knowledge updates, or persist some updates from an interrupted turn.

**Recommendation:** allow the transaction to stage all typed mutations and commit the complete validated batch after generation/extraction succeeds. Abort on interruption, provider failure, empty output, policy rejection, or workspace transition.

### P1 — adventure memory namespace is planned but not implemented

**Evidence:** the workspace manifest marks database and semantic index as `not_created`. `AssistantSession._context_plan()` still performs normal assistant-memory retrieval in the configured domain while an adventure is mounted. Active roleplay can label assistant memories `roleplay`, but that scope does not identify one adventure.

**Impact:** imported story facts or explicit remembers can enter shared personal memory and be visible in unrelated adventures/personas; an automatic narrative-memory system built on this path would violate isolation.

**Recommendation:** keep event/state authority in the workspace and add an explicit `adventure:<id>` derived-memory/index boundary before automatic narrative memory. Shared-reality observations continue through normal human-approved proposals.

### P2 — malformed reserved commands can fall through to the model

**Evidence:** command dispatch recognizes exact prefixes. Unrecognized text beginning with `adventure turn` can return no command result and continue through normal chat.

**Impact:** a user typo in a mutating namespace can produce plausible narration rather than a safe syntax error, obscuring whether anything persisted.

**Recommendation:** reserve the `adventure`, `roleplay`, `memory`, `proposal`, and future tool command envelopes. Known malformed mutating prefixes return deterministic help and never call a provider.

### P2 — event provenance and retry identity are insufficient for automatic writes

**Evidence:** source is fixed to `core_explicit`; there is no request/turn ID, actor, extraction policy version, idempotency key, or candidate-to-event link.

**Impact:** retries and recovery cannot distinguish a duplicate from a distinct repeated event, and users cannot inspect why an automatic change became canonical.

**Recommendation:** add a bounded source descriptor, turn/request ID, policy/schema version, and idempotency key before provider-derived candidates are permitted.

### P2 — contradiction/correction semantics are only implicit latest-value rules

**Evidence:** state and relationship keys use latest-value-wins. Knowledge identity is based on normalized fact text, so a rephrased correction may become a second fact. No event explicitly retracts or supersedes another.

**Impact:** audit history survives, but Core cannot reliably explain a correction, dispute, or conflicting account. Replay selection can retain an obsolete statement without its correction.

**Recommendation:** add explicit supersession/retraction/dispute operations and projection rules. Keep old events immutable and explain which event currently governs a fact.

### P2 — qualitative relationship policy is documented more strongly than validated

**Evidence:** relationship values are bounded strings, not a validated qualitative vocabulary/profile. The retrieved-memory sanitizer does not govern `AdventureSessionState.context_text()` values written directly to adventure events.

**Impact:** a direct or future automatic write could store and expose numeric/internal meters despite the presentation invariant.

**Recommendation:** use validated per-adventure qualitative states or a Core-owned hidden numeric model projected to qualitative labels. Redact before all model-facing adventure context, not only retrieved assistant memories.

### P2 — replay spine is deterministic but not yet continuity-complete

**Evidence:** `select_replay_spine()` keeps only the latest event for each category before filling by recency.

**Impact:** multiple simultaneous promises, hooks, lies, or discoveries can be dropped from context even while unresolved. The event log remains safe, but narration may contradict omitted continuity.

**Recommendation:** project unresolved obligations and active facts as structured state, then select relevant history by scene/participants/objective. Do not attempt to solve this with larger raw prompts.

### P3 — append cost scales with total history

**Evidence:** every `append_many()` reads and rewrites the complete JSONL file.

**Impact:** long adventures will increase commit latency and widen the concurrency window.

**Recommendation:** retain the simple format during prototype hardening. Consider true append with durable framing, segmented logs, or SQLite only after benchmarks justify it and recovery semantics are specified.

### P3 — documentation/status terminology is ahead of implementation

The baseline sometimes describes an adventure database, semantic index, automatic narrative memory, and persistent simulation alongside completed primitives. The source clearly does not implement those capabilities yet. The proposed roadmap separates foundation, active, later, and research work.

## Minimal scenario-defined resource model

Core should not hardcode game-specific concepts. It should expose a closed set of generic declarations and operations.

Example declaration:

```json
{
  "resource_id": "ship_ammo",
  "kind": "bounded_integer",
  "label": "Deck ammunition",
  "minimum": 0,
  "maximum": 40,
  "initial": 12,
  "visibility": "player_visible",
  "operations": ["increment", "decrement", "set"]
}
```

Recommended kinds:

- `flag`: boolean or bounded enum;
- `bounded_integer` and `bounded_decimal`;
- `inventory_item`: stable item ID and non-negative count;
- `equipment_slot`: stable slot to item reference;
- `objective`: inactive/active/completed/failed plus optional parent;
- `location`: stable location ID;
- `clock`: explicit bounded time marker, not wall-clock simulation by default.

Rules:

- Adventure/package data defines labels and meaning; Core defines type validation and mutation semantics.
- Every operation becomes a typed event mutation and is applied by Core.
- Hidden values may exist in full state but are omitted or qualitatively projected for models/players according to policy.
- Derived totals are recomputed, not trusted from narration.
- Package definitions are immutable for a running save unless a versioned migration succeeds.

This provides game-adjacent state without making StarFur a rendering, physics, combat, or scripting engine.

## Grounded persona narration

Persona commentary can remain natural without owning state:

1. Core selects the active scene, participants, objectives, visible resources, relevant relationship projections, character-specific knowledge, and replay facts.
2. `ContextManager` labels that packet as authoritative Core state and labels omitted/hidden values explicitly where needed.
3. The persona/provider generates narration or commentary.
4. Generated text is displayed as transcript, not canonical state.
5. A separate extractor may propose typed events/mutations from the completed turn.
6. Core validates policy, provenance, contradiction rules, and resource operations, then commits or rejects the whole batch.

A persona may say “we are low on ammunition” because Core supplied a qualitative projection. It must not receive or reveal the exact hidden count unless policy permits it. A different persona may comment in a different style while seeing the same permitted world truth.

## Workshop-safe package boundaries

### Persona package

May contain:

- stable package/persona ID and version;
- static identity/presentation text;
- validated behavior defaults and memory-visibility defaults;
- declared interests and compatible capability preferences;
- stable sprite/voice/animation asset references;
- locale, content tags, author, license, attribution, and fallback metadata.

Must not contain Core permissions, provider credentials, direct database writes, arbitrary Python/shell code, or mutable user/adventure saves.

### Sprite/asset package

May contain bounded images/animations/audio and a declarative map of stable slots such as `portrait.neutral`, `pose.working`, or `expression.concerned`. Missing slots fall back. Asset metadata never becomes persona truth.

### Adventure package

May contain initial world/resource definitions, characters, locations, objectives, starting events, presentation assets, and compatibility metadata. It must not include the user's runtime event log or silently access shared memories/tools.

### Runtime/save state

Installed package content is immutable. Persona development, user memory, adventure saves, generated assets, and configuration live in separate versioned namespaces. Updating or removing a Workshop item cannot silently erase or rewrite saves; incompatible saves are disabled with a recoverable explanation.

### Installer boundary

All local and Steam Workshop packages pass through the same validator: normalized relative paths, no traversal or symlinks, bounded file/count/size totals, allowed media types, hashes, compatibility checks, dependency resolution, content metadata, and atomic activation. Steam is a distribution adapter, not a trust boundary.

## Required gates before automatic adventure memory

Automatic extraction or auto-approval should remain disabled until all are true:

- complete authoritative projections are separate from context limits;
- workspace writes are coordinated, recoverable, and idempotent;
- all turn mutations share one commit/abort boundary;
- adventure-specific namespace and provenance are implemented;
- correction/supersession is inspectable;
- transcript is separate from events/state;
- salience and false-positive benchmarks exist;
- interruption, restart, corrupted storage, duplicate retry, and cross-adventure isolation tests pass;
- users can inspect and correct canonical story state without editing files.

Auto-commit policy should initially allow only low-risk, schema-valid adventure facts with explicit evidence from the completed turn. High-impact, destructive, hidden, contradictory, or low-confidence changes should remain staged for review. The policy can be less conservative than real-world user memory without becoming unbounded.

## Recommended next six implementation slices

### Slice 1 — complete projections plus bounded selectors

Add full state/relationship/knowledge projection objects and separate context selectors. Preserve existing prompt output for fixtures below the limit.

**Tests:** more than twelve keys/facts, full inspection after reload, deterministic selected subset, total-versus-selected diagnostics, unchanged small fixture output.

### Slice 2 — durable workspace commit boundary

Add workspace-scoped serialization, expected-head validation, atomic metadata writes, commit/idempotency IDs, and recovery of stale temporary/orphan state.

**Tests:** concurrent writers, process-style retry, failure before/after event replacement, failed manifest update, stale `.pending`, orphan registry entry/workspace, duplicate commit.

### Slice 3 — typed mutation envelope and mixed transactions

Introduce schema-v2 envelope/payload compatibility and let one `AdventureTurnTransaction` stage state, relationship, knowledge, and generic resource mutations alongside ordinary events.

**Tests:** v1 read compatibility, mixed batch commit, invalid payload abort, source/provenance round trip, interrupted/empty/provider-failed turn seam.

### Slice 4 — fail-closed commands and bound story lifecycle

Reserve command namespaces and add explicit start/resume binding of workspace, branch, and roleplay state. Keep exact pause/end overrides.

**Tests:** malformed mutating commands never call the model, ambiguous title selection, lifecycle cleanup, independent API conversations, restart mount.

### Slice 5 — corrections and replay benchmark

Add supersession/retraction/dispute semantics and fixtures for unresolved hooks, multiple promises/lies, differently worded knowledge corrections, long sessions, restart, and branch isolation.

**Tests/metrics:** projection correctness, key-event retention, contradiction rate, false continuity, replay determinism, recovery outcome.

### Slice 6 — staged narrative candidate pipeline

Only after Slices 1–5 pass, add task-profile-driven extraction of typed candidate events from completed turns, deterministic validation, bounded policy, and atomic commit/abort. Keep raw model output non-authoritative.

**Tests/benchmarks:** extraction precision/recall, decorative-prose false positives, hidden-value leakage, interruption, retry idempotency, model-size comparison, user correction.

## Assumptions

- The near-term runtime is a single local user, but multiple API conversations/processes may access one adventure workspace.
- JSONL remains acceptable for the prototype if integrity/recovery is hardened; migration to SQLite is not assumed.
- Persona narration should work with different chat providers and models.
- Workshop packages are declarative and non-executable by default.
- Exact internal numeric values may exist, but normal narration receives only policy-permitted projections.
- The authoritative WSL test suite remains the release test environment.

## Unresolved product decisions

1. Whether automatic low-risk adventure mutations are always enabled in adventure mode or require a per-adventure policy toggle.
2. Whether transcript retention defaults to full, bounded, summarized, or disabled.
3. Whether branches share immutable prefix events physically or copy them during the first implementation.
4. Whether hidden resources are visible to the narrator model, a separate simulation provider, or Core only.
5. Whether a running adventure can change package/schema versions, and what migration/rollback UX is required.
6. Whether Workshop v1 supports adventures as well as persona/sprite packages, or launches with personas/sprites first.
7. Whether local third-party executable plugins are ever supported; this review recommends keeping that separate from Workshop content.

## Conclusion

The current architecture has the right central instinct: event-backed truth and bounded model context. The next work should deepen that boundary rather than add more model prompts. Once complete projections, durable commits, typed mutations, and correction semantics are in place, StarFur can safely grow from an explicit CYOA prototype into a persistent, replayable, persona-narrated simulation—and later expose it through a Steam apartment and Workshop ecosystem without turning personas or models into the authority.
