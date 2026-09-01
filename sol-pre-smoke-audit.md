# StarFur Forge pre-smoke architectural audit

**Audit date:** 2026-08-19  
**Scope:** static, read-only inspection of current source, tests, `AGENTS.md`, `ROADMAP.md`, and `ROADMAP.v4.md`  
**Repository mutation:** this file only

No tests were executed during this audit. That choice avoids creating or updating test artifacts in an already dirty worktree and complies with the requirement that this report be the only repository change. Findings below distinguish current implementation evidence from architectural inference.

## Executive verdict

The narrow adventure happy path is ready for a controlled smoke test: one process, one stable conversation ID, one loaded workspace, exact documented commands, and no injected crash. The strongest implemented boundary is the separation between complete authoritative state/relationship/knowledge projections and their bounded prompt projections.

The repository is **not yet ready to treat that smoke as A1–A4 acceptance**. Typed mutations exist and can be staged in the transaction object, but the user-facing transaction command accepts only ordinary event drafts and commit persists only the compatibility drafts. Reserved malformed adventure commands can still fall through to model generation. Recovery is write-triggered rather than load-triggered, and registry creation is outside the event-log locking/recovery boundary.

No evidence suggests an ordinary exact-command smoke will corrupt data. The principal pre-smoke risks are false confidence, provider fallthrough on malformed commands, session-local staging loss, and stale views after a crash artifact.

## Findings

### 1. Complete authoritative projections are correctly separated from bounded prompt projections

- **Severity:** observation
- **References:** `pipeline/adventure_state.py:23-46`; `pipeline/adventure_relationship.py:24-52`; `pipeline/adventure_knowledge.py:24-52`; `pipeline/adventure_session.py:91-109`; `pipeline/adventure_session.py:133-191`; `tests/test_adventure_commands.py:179-201`; `tests/test_adventure_state.py:36-47`; `tests/test_adventure_relationship.py:44-55`; `tests/test_adventure_knowledge.py:41-52`.
- **Observed fact:** Each derivation function rebuilds a complete latest-value projection from all validated events. Separate selectors cap prompt-facing collections at twelve. `AdventureSessionState` retains both collections and reports both counts. The command-level state test verifies thirteen keys remain inspectable and survive pause/resume while only twelve enter a model prompt.
- **Architectural inference:** A1's core integrity objective is met. Reducing a prompt budget cannot delete canonical state.
- **Recommended action:** Preserve this split. Add equivalent command-level reload tests for over-limit relationships and character knowledge, since those two currently have only pure-function over-limit tests.
- **Timing:** Can wait until after the narrow smoke; required before declaring A1's entire listed test matrix complete.

### 2. A4 is only a staging foundation, not a user-facing mixed transaction

- **Severity:** high
- **References:** `pipeline/adventure_turn.py:56-107`; `pipeline/assistant.py:1260-1293`; `pipeline/assistant.py:1340-1349`; `tests/test_adventure_turn.py:42-80`; `tests/test_adventure_commands.py:309-333`; `ROADMAP.v4.md:141-159`.
- **Observed fact:** `AdventureTurnTransaction.stage_mutation()` validates a typed mutation, immediately creates a schema-v1-compatible `AdventureEventDraft`, and stores both. `AssistantSession.adventure_turn_stage()` exposes only `adventure turn stage <event-type>: <summary>`. `adventure_turn_commit()` passes only `self.adventure_turn.drafts` to `append_many()`; it never consumes `self.adventure_turn.mutations`. The mixed test constructs and commits the transaction directly rather than exercising CLI/API command routing.
- **Architectural inference:** Atomic mixed persistence works only through an internal compatibility representation. There is no current Core command path that stages structured state, relationship, or knowledge mutations in the turn transaction, and the independent mutation tuple is not the committed source of truth.
- **Recommended action:** Add exact Core-owned staged mutation commands or one strictly typed Core payload boundary. Couple each typed mutation to its corresponding staged event rather than maintaining an unindexed side tuple, validate the association, and exercise the path through `AssistantSession.respond()` and the API.
- **Timing:** Must be fixed before calling tomorrow's test an A1–A4 smoke. It may be excluded from a narrower pre-A4 happy-path smoke if that limitation is stated.

### 3. Malformed reserved adventure commands still reach the model

- **Severity:** high
- **References:** `pipeline/assistant.py:1302-1433`; `pipeline/assistant.py:1551-1585`; `tests/test_adventure_commands.py:48-56`; `ROADMAP.v4.md:161-167`.
- **Observed fact:** `command()` recognizes exact forms and then returns `None`. `respond()` interprets `None` as ordinary conversation and calls the provider. Existing invalid-command coverage checks only recognized command branches such as an empty `adventure create`; it does not cover unknown or near-miss input inside `adventure`, `adventure turn`, `adventure state`, `adventure relationship`, or `adventure knowledge` namespaces.
- **Architectural inference:** Inputs such as `adventure turn state ...`, `adventure status/`, or a misspelled mutation verb can generate prose and may run proposal extraction. That is unsafe command ambiguity even though the model has no direct event-log authority.
- **Recommended action:** Implement A5 before broad smoke testing: reserve Core namespaces, return deterministic usage/errors for malformed members, and assert zero provider calls, zero proposals, zero chat-history mutation, and zero event writes through CLI and API adapters.
- **Timing:** Must be fixed before a meaningful negative-path CLI/OpenWebUI smoke.

### 4. Typed mutation validation is strong, but the transaction can contain unrelated drafts and mutations

- **Severity:** medium
- **References:** `pipeline/adventure_turn.py:17-41`; `pipeline/adventure_turn.py:68-107`; `pipeline/adventure_mutation.py:63-164`; `tests/test_adventure_turn.py:42-80`.
- **Observed fact:** Transaction construction checks only that every mutation has the right type and that mutation count does not exceed draft count. It does not verify that a mutation corresponds to any particular draft. The normal `stage_mutation()` helper constructs a valid pair, but callers can instantiate a transaction with unrelated valid tuples. Commit ignores the mutation tuple.
- **Architectural inference:** Once generated-turn orchestration or another adapter constructs transactions, typed intent could diverge from the persisted compatibility draft without detection.
- **Recommended action:** Represent staged items as a discriminated union or paired record, or derive the compatibility draft only at commit from the authoritative staged mutation. Reject inconsistent manually constructed transactions.
- **Timing:** Fix with Finding 2 before automatic narration/state extraction; it can wait for a strictly ordinary-event smoke.

### 5. Schema-v1 compatibility and schema-v2 read preservation are real, but Core does not write v2

- **Severity:** observation
- **References:** `pipeline/adventure_events.py:151-165`; `pipeline/adventure_events.py:213-243`; `pipeline/adventure_events.py:245-311`; `pipeline/adventure_events.py:449-458`; `tests/test_adventure_events.py:196-235`; `ROADMAP.v4.md:139-150`.
- **Observed fact:** The reader defaults legacy entries to schema v1, validates schema v2 through `AdventureEventEnvelope`, projects typed mutations through existing readers, and serializes without converting versions. `append_many()` always constructs default schema-v1 `AdventureEvent` objects.
- **Architectural inference:** The current design is an adapter foundation, not a storage migration. That is coherent with the roadmap as long as no documentation claims new Core events are v2.
- **Recommended action:** Keep v1 writes until a migration policy exists. Before enabling v2 writes, add mixed-log restart, projection, request-id retry, pending recovery, and supersession tests.
- **Timing:** Safe to defer.

### 6. Valid pending logs are recovered only on an explicit recovery or the next write, not on load

- **Severity:** high
- **References:** `pipeline/adventure_events.py:383-411`; `pipeline/adventure_events.py:439-443`; `pipeline/adventure_events.py:555-576`; `pipeline/assistant.py:1025-1046`; `tests/test_adventure_events.py:104-166`.
- **Observed fact:** `AdventureEventLog.events()` reads only `events.jsonl`. Recovery runs in `recover()` or at the start of `append_many()`. `adventure_load()` calls `events()` directly. Tests prove recovery before the next append and fail-closed conflict handling, but not recovery during mount.
- **Architectural inference:** After a crash leaves a valid `.pending` extension, the first reload can mount stale authoritative state until another write occurs. That conflicts with the intuitive meaning of restart recovery and could make a smoke appear to lose the latest turn.
- **Recommended action:** Define a single Core-owned open/mount recovery boundary that acquires the write guard, reconciles pending and manifest state, then returns validated events. Keep the raw read method side-effect-free for inspection/tests.
- **Timing:** Must be fixed before a crash/restart recovery smoke; may be deferred only if tomorrow's smoke explicitly excludes crash artifacts.

### 7. Event-log replacement and manifest reconciliation are not one durable transaction

- **Severity:** high
- **References:** `pipeline/adventure_events.py:439-463`; `pipeline/adventure_events.py:542-553`; `pipeline/adventure_events.py:588-621`; `tests/test_adventure_events.py:168-194`; `ROADMAP.v4.md:127-137`.
- **Observed fact:** The pending log is flushed and `fsync`ed, then atomically replaces the event log. Manifest reconciliation happens afterward through a direct `write_text()`. A valid log can repair `not_created`, but an event-log commit can succeed before a manifest write reports failure. The containing directory is not `fsync`ed after replacement.
- **Architectural inference:** Logical append integrity is substantially improved, but power-loss durability and metadata atomicity are not complete. A request-ID staged retry is recoverable; an immediate command without a request ID can be reported as failed after its event was actually committed and then duplicate on user retry.
- **Recommended action:** Document the commit point, make manifest replacement recoverable/atomic, consider directory sync where supported, and assign idempotency keys to all externally retryable mutation requests rather than only staged turns.
- **Timing:** Safe to defer for a single-process happy-path smoke; must be addressed before A2 is marked complete or automatic retries are enabled.

### 8. The advisory lock protects event logs, not registry creation

- **Severity:** high
- **References:** `pipeline/adventure_events.py:465-510`; `pipeline/adventure_registry.py:143-186`; `tests/test_adventure_events.py:81-102`; `tests/test_adventure_registry.py:16-52`.
- **Observed fact:** Event-log writers use nonblocking `flock` under WSL/POSIX and `msvcrt.locking` on native Windows. `AdventureRegistry.create()` creates a workspace, writes a manifest, rereads the registry, and overwrites `registry.json` without a registry lock, pending file, atomic replace, or orphan reconciliation.
- **Architectural inference:** Concurrent `adventure create` calls can lose a registry entry or leave an orphan workspace even though later event writes are serialized correctly.
- **Recommended action:** Add a registry-scoped advisory lock and atomic/recoverable registry replacement, then define orphan reconciliation. Do not reuse a workspace event lock for registry-wide writes.
- **Timing:** Safe to defer only for a one-writer smoke. Must precede concurrent API testing and any multi-surface release claim.

### 9. Lock coverage is not yet proven across actual processes or both host platforms

- **Severity:** medium
- **References:** `pipeline/adventure_events.py:23-26`; `pipeline/adventure_events.py:488-510`; `tests/test_adventure_events.py:81-102`.
- **Observed fact:** The lock test uses two `AdventureEventLog` instances in one Python process and manually holds the first object's private guard. The native-Windows branch is explicitly excluded from coverage. There is no subprocess race test.
- **Architectural inference:** POSIX `flock` should work in WSL on the Linux filesystem, but current tests do not prove independent-process sequencing, native-Windows byte-range behavior, or behavior on Windows-mounted/network filesystems.
- **Recommended action:** Add a subprocess-based two-writer test in authoritative WSL and a small native-Windows compatibility test. Keep adventure storage on the WSL Linux filesystem for the first smoke.
- **Timing:** The automated regression can wait, but tomorrow's matrix should include one manual two-process contention check before treating A2 locking as verified.

### 10. Session eviction can silently discard an uncommitted turn between API requests

- **Severity:** high
- **References:** `pipeline/application.py:179-225`; `pipeline/application.py:227-239`; `pipeline/assistant.py:249-254`; `tests/test_application.py:163-207`.
- **Observed fact:** Non-default conversations are bounded to sixteen and evicted by LRU whenever they have no active request. `AdventureTurnTransaction` and the mounted workspace are session-local. Request pinning lasts only for one request. The eviction tests use `FakeSession` and verify generic recreation, not staged adventure state.
- **Architectural inference:** An OpenWebUI user can begin/stage a turn, allow enough other conversations to evict that session, then receive an inactive transaction on commit. Nothing is partially persisted, so integrity is safe, but staged work disappears without an explicit lifecycle message.
- **Recommended action:** Define a policy for sessions with staged mutations: pin until commit/abort with a bounded timeout, or return an explicit resumability token backed by a non-canonical staging store. At minimum expose eviction/expiration in diagnostics.
- **Timing:** Safe to defer for a controlled smoke using one stable conversation ID and fewer than sixteen active chats; required before normal multi-chat UX.

### 11. Persona and roleplay transitions do not abort active adventure staging

- **Severity:** medium
- **References:** `pipeline/assistant.py:921-960`; `pipeline/assistant.py:1018-1023`; `pipeline/assistant.py:1243-1300`; `AGENTS.md:68`.
- **Observed fact:** Adventure mount/unmount transitions reset `adventure_turn`. Persona selection and roleplay begin/end clear recent conversation state but leave `adventure_turn` untouched.
- **Architectural inference:** A user can stage under one persona or roleplay mode, switch presentation identity/mode, and commit the old transaction afterward. This may be intentional because authority belongs to Core, but it is currently unspecified and contradicts the broader documentation phrase “lifecycle cleanup discard it.”
- **Recommended action:** Decide explicitly which transitions preserve staging. The conservative first policy is to abort on persona switch, roleplay end, conversation eviction, and server shutdown, with a clear discarded-count message.
- **Timing:** Prefer fixing before the lifecycle portion of smoke testing; it is not a data-corruption blocker for an exact happy path.

### 12. Diagnostics are accurate for model turns but intentionally disappear across Core lifecycle commands

- **Severity:** low
- **References:** `pipeline/assistant.py:382-448`; `pipeline/assistant.py:1018-1023`; `pipeline/assistant.py:1090-1102`; `tests/test_adventure_commands.py:170-177`; `tests/test_adventure_commands.py:192-201`.
- **Observed fact:** Context diagnostics include authoritative and selected adventure counts for the most recent generated turn. Loading/unloading an adventure clears `last_turn_diagnostics`, and exact Core commands do not create a model-turn diagnostic record.
- **Architectural inference:** `context stats` immediately after load or a mutation can say no turn is available even though `adventure status` reflects current Core state. This is internally consistent but easy to misread as lost state in OpenWebUI.
- **Recommended action:** Keep model-turn diagnostics immutable, but add a separate read-only current session/adventure snapshot or label the distinction prominently.
- **Timing:** Safe to defer; account for it in the smoke sequence.

### 13. The v2 parsers validate known semantics but tolerate unknown object keys

- **Severity:** medium
- **References:** `pipeline/adventure_mutation.py:143-164`; `pipeline/adventure_mutation.py:233-250`; `tests/test_adventure_mutation.py:39-72`.
- **Observed fact:** Unknown mutation kinds and mixed dataclass payloads fail closed. `from_dict()` extracts recognized keys but does not reject unexpected keys in the mutation or envelope, and `recorded_at` is checked only as a nonempty string.
- **Architectural inference:** This is acceptable while only trusted Core constructs v2 values, but it weakens schema strictness if a future provider/tool/API submits envelopes. Extra authority-like fields can be silently ignored, complicating reproducibility and migration diagnostics.
- **Recommended action:** Add exact allowed-key validation and parse/normalize timestamps before any external or automatic writer can reach this boundary.
- **Timing:** Safe to defer until before generated/tool-authored structured mutations.

### 14. Zero-provider identity construction is possible, but a true zero-provider mode does not exist

- **Severity:** high
- **References:** `pipeline/assistant.py:64-78`; `pipeline/assistant.py:187-230`; `pipeline/application.py:443-488`; `pipeline/persona_runtime.py:105-145`; `ROADMAP.v4.md:289-311`.
- **Observed fact:** Persona packages and runtime state are created before any generation call, and exact Core commands do not inherently need a model. However, `AssistantConfig` requires a chat model, `AssistantSession` substitutes `OllamaChatProvider` whenever no provider is injected, and the standard application factory always builds ordinary provider-backed sessions. There is no `NullChatProvider`, disabled-provider configuration, deterministic `ResidentAction`, or authored-dialogue fallback.
- **Architectural inference:** An unavailable Ollama daemon is not the same as a supported zero-provider installation. Core identity can survive a provider call failure in-process, but the current product cannot intentionally boot and advertise a coherent provider-free capability set.
- **Recommended action:** Introduce an explicit optional-provider boundary and capability availability model before apartment UI contracts harden. A null/disabled capability must never be mistaken for a configured but unhealthy provider.
- **Timing:** Safe to defer from the adventure smoke; not safe to defer beyond the first apartment/runtime integration boundary.

### 15. Current persona state cannot satisfy zero-provider restart continuity

- **Severity:** high
- **References:** `pipeline/persona_runtime.py:105-145`; `pipeline/application.py:459-474`; `AGENTS.md:53-54`; `ROADMAP.md:184`; `ROADMAP.v4.md:83-87`; `ROADMAP.v4.md:309-311`.
- **Observed fact:** `PersonaRuntimeRegistry` is in-memory and explicitly restart-ephemeral. `create_assistant_application()` creates a new registry for each application process. Its public snapshot is appropriately bounded, but no persistent resident-state restore exists.
- **Architectural inference:** Provider independence and restart continuity are separate requirements. The former can be added without solving the latter, but the zero-provider release requirement needs a persistence-class design before it can preserve a resident across restarts.
- **Recommended action:** Keep shared user memory separate. Define durable persona-local, reconstructable, and session-ephemeral state classes, then persist only reviewed durable fields with versioned migrations and rollback.
- **Timing:** Safe to defer from A-stage smoke; must precede the apartment persistence and Steam release gates.

### 16. Capability reporting is statically Ollama-shaped

- **Severity:** medium
- **References:** `pipeline/capabilities.py:249-255`; `pipeline/application.py:82-95`; `pipeline/application.py:407-430`; `ROADMAP.v4.md:289-311`.
- **Observed fact:** The core capability registry always includes `provider.ollama`. Runtime diagnostics call a provider “configured” when a provider object exists, even if it has not been probed and the service is absent.
- **Architectural inference:** A future zero-provider or non-Ollama installation could tell personas/UI that Ollama is a capability simply because the manifest is static. This conflicts with the goal that all presentation surfaces accurately reflect available capabilities.
- **Recommended action:** Separate capability definitions from per-session availability/health. Build the runtime manifest from configured adapters and expose unavailable optional capabilities explicitly.
- **Timing:** Safe to defer until provider profiles or zero-provider foundation, but settle before apartment/dashboard capability rendering.

### 17. Several tests prove lower-level mechanics without proving the composed product boundary

- **Severity:** medium
- **References:** `tests/test_adventure_turn.py:16-80`; `tests/test_adventure_mutation.py:17-72`; `tests/test_adventure_events.py:63-92`; `tests/test_application.py:163-207`; `tests/test_api.py:201-242`; `ROADMAP.v4.md:149-167`.
- **Observed fact:** Mixed transactions are committed by directly calling the event log; lock contention is same-process; API isolation uses fake sessions; eviction uses fake sessions; v2 entries are manually written to disk; there are no zero-provider startup tests; and there are no malformed reserved-namespace, provider interruption with active staging, post-replace retry, relationship/knowledge reload-over-limit, or real `AssistantSession` multi-conversation adventure tests.
- **Architectural inference:** Unit coverage is useful and generally well bounded, but it can overstate readiness at the CLI/API/OpenWebUI composition seams where most likely failures now live.
- **Recommended action:** Add a thin integration layer using temporary adventure roots and fake providers. Preserve each real smoke failure as a regression fixture.
- **Timing:** Add malformed namespace and mixed Core command cases before broad smoke; the remainder can follow immediately after the first controlled run.

### 18. Native Windows and WSL have distinct unverified failure surfaces

- **Severity:** medium
- **References:** `pipeline/adventure_events.py:23-26`; `pipeline/adventure_events.py:488-510`; `pipeline/adventure_events.py:542-551`; `tests/test_adventure_events.py:81-102`.
- **Observed fact:** WSL uses `fcntl.flock`; native Windows uses a one-byte `msvcrt` lock. Atomic replacement also depends on host filesystem semantics. Tests do not exercise both implementations or a repository/data directory mounted across the Windows/WSL boundary.
- **Architectural inference:** The likely WSL happy path is sound when the repository and adventure data live in the Linux filesystem. Native Windows file sharing, antivirus/indexer handles, and `/mnt/c` behavior may produce lock or replace differences not represented by current tests.
- **Recommended action:** Make WSL-on-Linux-filesystem the documented prototype environment. Later add platform-specific subprocess tests and avoid sharing a live adventure root between native Windows and WSL processes.
- **Timing:** No code fix is required before the WSL-only smoke; environment placement must be checked first.

## Must fix before smoke test

For a **narrow happy-path smoke**, there is no identified corruption blocker if it uses exact commands, one process, one stable conversation ID, one writer, and no crash injection.

Before calling the run an **A1–A4 integrity smoke**, fix or complete:

1. Wire typed state/relationship/knowledge staging through the Core command/API boundary and verify mixed commit through `AssistantSession.respond()` (Findings 2 and 4).
2. Fail closed for malformed reserved adventure namespaces so no typo calls a provider or creates a proposal (Finding 3).
3. Recover/reconcile a valid pending log on the Core load/open path if crash/restart recovery is in scope (Finding 6).
4. Define and test whether persona/roleplay transitions abort an active transaction (Finding 11).

If those are intentionally the next slices, run only the limited happy path now and label it “pre-A4 wiring smoke,” not completion evidence.

## Safe to defer

- Full registry transaction/orphan recovery, provided the smoke has one writer and creates adventures serially.
- Directory-level durability and manifest atomicity, provided no crash or injected I/O failure is part of the smoke.
- Schema-v2 writes, supersession behavior, and strict unknown-key rejection.
- Better bounded projection selection quality; full authoritative state is already preserved.
- Persistent staged-turn recovery across LRU eviction or server restart.
- True zero-provider mode, durable persona-local continuity, authored `ResidentAction` fallbacks, and dynamic provider capability manifests—provided these boundaries are settled before apartment UI lock-in.
- Native-Windows support beyond documenting WSL/Linux-filesystem as the current authoritative prototype environment.

## Recommended smoke-test sequence

1. **Environment guard:** Use the WSL repository/adventure root on its Linux filesystem. Back up the test adventure directory. Start with a unique disposable adventure title and a stable OpenWebUI conversation identifier.
2. **Core-only CLI sanity:** With no generation request, run `persona current`, `adventure create <title>`, `adventure load <title>`, `adventure status`, and `adventure turn status`. Confirm no model latency and no memory proposal.
3. **Projection integrity:** Add at least thirteen state keys, thirteen relationship character/dimension pairs, and thirteen character-knowledge facts. Confirm full inspection shows all facts, `adventure status` reports total versus twelve selected, then pause/resume and inspect again.
4. **Ordinary transaction baseline:** Begin, stage two ordinary events, verify `adventure events` is unchanged, abort, and verify no append. Repeat and commit; confirm contiguous IDs and one request ID in the log.
5. **Mixed transaction acceptance (after Core wiring):** In one turn stage an ordinary event, state change, qualitative relationship change, and character-knowledge change. Confirm none are visible before commit; commit once; verify all four projections and one shared request ID after reload.
6. **Reserved-namespace negative cases (after A5):** Try missing colons, unknown subcommands, near-miss mutation verbs, invalid event types, and trailing punctuation through both CLI and OpenWebUI. Confirm deterministic Core errors, unchanged event/proposal counts, and no provider call.
7. **Lifecycle checks:** Begin and stage, then switch persona, end roleplay, unload, and change OpenWebUI conversation ID one case at a time. Verify the documented preserve/abort behavior and explicit user feedback.
8. **API/OpenWebUI isolation:** Load the adventure in conversation A. Confirm conversation B has no mount. Return to A and verify the mount and staging state remain while under the LRU bound. Restart `serve`; confirm session-local mounts are gone and an explicit reload reconstructs all authoritative projections.
9. **Recovery check:** Using only a disposable copy, create a valid pending extension and restart/load. Once Finding 6 is fixed, confirm mount recovers it; confirm malformed/divergent pending content fails closed without changing `events.jsonl`.
10. **Two-process WSL lock:** Hold or initiate a write from one process and attempt a second write from another. Confirm one writer succeeds, the contender fails clearly, and retry produces a contiguous nonduplicated log.
11. **Diagnostics:** Generate one model turn only after Core state is established. Confirm context stats show authoritative and selected counts. Do not interpret “no turn diagnostics” immediately after a Core lifecycle command as state loss; use `adventure status` for current Core state.
12. **Regression capture:** Save any real failure's exact command sequence, conversation-ID behavior, event-log fixture, and expected no-write/no-provider outcome as a focused temporary-state test.

## Roadmap/documentation corrections, if any

1. **`ROADMAP.v4.md` contains stale baseline statements.** Lines 102 and 108 say complete projections do not exist, while lines 118-125 correctly mark A1's initial slice complete. Lines 109-110 similarly predate the A2 and A4 foundations described at lines 137-141. Label the earlier section as findings at audit time with resolved/superseded annotations, or update each discrepancy's current status.
2. **The Stage A status is stale.** `ROADMAP.v4.md:116` says “A2 next,” while A2, A3, and A4 foundations are recorded below and current source makes A4 Core wiring/A5 the actual next boundary.
3. **`AGENTS.md` understates current write paths.** `AGENTS.md:64` calls `adventure_record` and `adventure state set` the sole user-facing Core writes, but `pipeline/assistant.py:1162-1221` also exposes immediate relationship and knowledge writes and lines 1276-1293 expose staged batch commit.
4. **Mutation conversion timing is described inaccurately.** `AGENTS.md:68`, `ROADMAP.md:227`, and `ROADMAP.v4.md:141` describe typed mutations as becoming compatibility drafts at commit. In source, `AdventureTurnTransaction.stage_mutation()` creates the compatibility draft during staging, and commit uses the draft tuple without reading the mutation tuple.
5. **Zero-provider work is placed too late as an architectural boundary.** Full deterministic resident behavior can remain later, but optional-provider construction, dynamic capability availability, and provider-independent resident identity/state contracts should be a dependency gate before the apartment/dashboard surface—not introduced after it. This avoids encoding Ollama assumptions into apartment and Steam presentation APIs.
6. **Keep the product distinction explicit.** The roadmap is coherent in treating the apartment and Steam client as replaceable presentation over Core. Zero-provider mode strengthens rather than contradicts that goal, but only if “provider unavailable,” “provider disabled,” and “capability not installed” become different structured states while persona identity and allowed persistent resident state remain stable.
