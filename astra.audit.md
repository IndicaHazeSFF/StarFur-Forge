Current architectural position
StarFur can reach—and already contains—a basic Murr apartment without a broad rewrite. The repository has C3 adventure-generation foundations, initial E1 routing, and an H0/H1 read-only resident surface. It does not yet have a complete autonomous resident or reliable multi-client adventure loop.
The strongest boundaries are explicit candidate review/staging, event-backed projections, declarative assets, and presentation-neutral snapshots. The main weaknesses are at their integration points.
This was static inspection only: no tests, providers, or external services were run; no files were changed. Git status before and after was identical, including existing modifications and untracked files.
Must fix before the next smoke test
These are gates for a meaningful integration acceptance test; disposable diagnostic tests can still reproduce them first.
F1 — High: stale adventure state can survive into commit.
- Observed: Candidate freshness checks compare against the session’s cached event count. Loading the already-mounted adventure does not refresh it. Commit calls append_many() without an expected authoritative revision. See [generation/selection (line 1273)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/assistant.py:1273), [load (line 1486)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/assistant.py:1486), and [commit (line 3005)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/assistant.py:3005).
- Inference: Another session/process can change the world during generation or staging, yet the original session can accept and commit stale changes. Advisory locking prevents overlapping writes, not stale decisions.
- Action: Capture an authoritative revision and compare it under the append lock. Preserve successful request-ID retries before rejecting revision conflicts. Refresh mounted projections explicitly.
- Coverage/gate: The [existing stale-origin test (line 566)](C:/Users/roger/Documents/Codex/StarFur Forge/tests/test_adventure_commands.py:566) changes state through the same session. Add two-session and stage→external-write→commit cases. Before smoke test involving concurrent/generated mutations.
F2 — High: a new conversation can evict itself.
- Observed: _session_slot_for() inserts a new unpinned slot, evicts excess sessions, then returns that slot. Pinning occurs afterward. When existing sessions are all busy, the new slot is the only eviction candidate. See [application registry (line 207)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/application.py:207).
- Inference: At capacity, a new request can produce KeyError instead of the documented temporary-overcapacity behavior.
- Action: Pin/admit the new request before eviction; define bounded overflow or backpressure.
- Coverage/gate: [Tests (line 252)](C:/Users/roger/Documents/Codex/StarFur Forge/tests/test_application.py:252) cover sequential eviction and ordinary concurrency separately, not their combination. Before concurrent API smoke test.
F3 — High: stale document extensions can still override non-adventure controls.
- Observed: API command precedence bypasses document extensions only for the adventure namespace. Otherwise starfur_document_review executes first, and document context resolves before session command dispatch. See [API complete (line 512)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/api.py:512).
- Inference: Stale OpenWebUI metadata can intercept context stats, persona controls, or roleplay exit; expired context can prevent them from reaching Core.
- Action: Share a deterministic Core-command classifier across adapters and resolve actual user controls before unrelated document extensions.
- Coverage/gate: [Current regression (line 801)](C:/Users/roger/Documents/Codex/StarFur Forge/tests/test_api.py:801) covers adventure commands only. Before OpenWebUI smoke test.
Must fix before deeper provider routing
F4 — Medium: route preview, execution, and annotation disagree about availability.
- Observed: Chat routing ignores previous lifecycle errors; route preview and annotation include them. An unsupported optional health probe makes a provider unroutable, while a previous healthy probe takes precedence over later lifecycle errors. See [chat routing (line 611)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/assistant.py:611), [annotation routing (line 480)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/application.py:480), and [status translation (line 67)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/task_routing.py:67).
- Inference: Identical provider conditions can permit chat but reject annotation; probing a usable adapter without health support can disable it.
- Action: Separate probe support, service availability, model eligibility, and last-request outcome. Apply one recovery policy everywhere.
- Gate: Before Stage E expansion. Test unavailable→recovered, unsupported probe, and healthy-probe→generation-failure transitions.
F5 — Medium: provider neutrality is not yet an end-to-end contract.
- Observed: ChatProvider.complete() returns Any; session code consumes Ollama-shaped messages/options. There is no common deadline/cancellation contract. Streaming failures can leave route telemetry at submitted. See [provider protocol (line 55)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/providers.py:55) and [execution/stream handling (line 722)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/assistant.py:722).
- Inference: A second adapter requires compatibility conventions that currently live outside the declared interface. Configured budgets do not themselves enforce a complete input budget.
- Action: Add normalized completion/chunk/error types and stable provider IDs; translate budgets inside adapters. Distinguish submitted, completed, failed, and cancelled without retaining payloads.
- Gate: Before Stage E specialist-provider support. Prove behavior using two differently shaped fake adapters first.
F6 — Medium: annotation is bounded by attempts, not by job lifetime.
- Observed: Annotation holds the default conversation lock throughout extraction. Provider exceptions become DocumentAnnotationError, which the retry loop also retries. OpenWebUI uses a synchronous request with a maximum 600-second timeout; terminal disconnect suppresses output but continues processing. See [application annotation (line 415)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/application.py:415), [retry loop (line 364)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/document_intake.py:364), [filter request (line 262)](C:/Users/roger/Documents/Codex/StarFur Forge/integrations/openwebui/starfur_document_filter.py:262), and [terminal transport (line 603)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/api.py:603).
- Inference: Retrying after client timeout can duplicate expensive work; faster models alone will not solve this.
- Action: Separate transport failures from invalid output, add deadlines and explicit disconnect policy, then introduce bounded annotation jobs with structured progress/result retrieval. Keep valid-empty output distinct from useful extraction.
- Gate: Before Stage E annotation scaling or another large-document acceptance test.
F7 — Medium: the ledger’s final write boundary does not fully enforce its privacy contract.
- Observed: append_benchmark_result() calls case sanitizers but discards their returned sanitized objects, then serializes the original record. Nested extra case fields can therefore survive this boundary. Existing tests reject top-level extras. See [writer (line 321)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/experiment_ledger.py:321) and [tests (line 143)](C:/Users/roger/Documents/Codex/StarFur Forge/tests/test_experiment_ledger.py:143).
- Inference: Current builder-generated records are safer than arbitrary records accepted by the public append function.
- Action: Reconstruct the entire allowed record at append time, including nested fields; reject or remove unknown content.
- Gate: Before Stage E adds more telemetry producers or exports.
F8 — Medium: benchmark labels exceed what the fixtures establish.
- Observed: Routing evaluation tests four planner scenarios and returns repeatability=True; its unit test separately compares two runs. Annotation quality uses one three-target, keyword-based fixture. See [routing evaluation (line 95)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/task_routing_eval.py:95), [repeatability test (line 16)](C:/Users/roger/Documents/Codex/StarFur Forge/tests/test_task_routing_eval.py:16), and [quality scoring (line 94)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/document_annotation_quality_eval.py:94).
- Inference: These do not establish live portability, semantic correctness, or dependable automatic approval. A negated statement containing the required keywords can satisfy the current matcher.
- Action: Label planner-contract results precisely; add negation, conflicting facts, valid-empty, long-document, cancellation, and adapter-shape cases.
- Gate: Before Stage E model-selection claims or automatic acceptance policies.
Must fix before apartment prototype expansion
F9 — Medium: polling cannot reliably show ongoing activity.
- Observed: Responses and snapshots hold the same conversation lock. The apartment polls every two seconds without an in-flight guard, cancellation, or response-generation check. See [application locking (line 285)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/application.py:285) and [browser polling (line 114)](C:/Users/roger/Documents/Codex/StarFur Forge/presentation/apartment.html:114).
- Inference: During a long request, snapshot calls wait; polls accumulate, and an older conversation response can render after the user switches conversations.
- Action: Publish immutable snapshots independently of the long-running request lock; allow one browser poll at a time and discard outdated responses. Also clarify unknown-conversation GET behavior: current lookup can create/evict sessions despite “read-only/no seeding” language.
- Gate: Before Stage H thinking/working animations or multi-client expansion.
F10 — Medium: provider-unavailable operation is not full zero-provider startup.
- Observed: Normal session construction defaults to an Ollama adapter, and the module imports Ollama unconditionally. Persona runtime is explicitly restart-ephemeral. See [session construction (line 274)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/assistant.py:274) and [runtime registry (line 116)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/persona_runtime.py:116).
- Inference: Successfully displaying Murr while Ollama is stopped does not prove a provider-disabled installation or durable resident continuity.
- Action: Add an explicit disabled-provider boot path and test it without provider access. Define which resident fields persist before implementing storage.
- Gate: Before Stage H continuity promises; before Steam release.
F11 — High: participant context is not yet a reliable knowledge boundary.
- Observed: AdventureParticipantView filters relationships/knowledge after global context selection, but copies global event summaries without participant visibility checks. Generated-turn context sanitizes typed relationship values while copying event summaries directly. Normal adventure chat still retrieves the configured shared-memory domain. See [participant view (line 72)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/adventure_participant.py:72), [turn context (line 76)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/adventure_turn_context.py:76), and [chat context (line 782)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/assistant.py:782).
- Inference: NPC-specific facts can disappear behind global limits; another character’s secret—or a numeric meter—can leak through an event summary. Ordinary narration is not automatically an isolated adventure-memory view.
- Action: Select from complete projections in this order: audience/knowledge permissions → relevance → bounded context. Apply protected-value rules across every output channel. Make shared-memory inclusion explicit.
- Coverage/gate: [Participant tests (line 26)](C:/Users/roger/Documents/Codex/StarFur Forge/tests/test_adventure_participant.py:26) manually supply a harmless global event. Before Stage E participant routing or Stage H presenting autonomous adventure participation.
Safe to defer
F12 — High durability risk, deferrable only for disposable tests.
- Observed: Event replacement fsyncs its temporary file, but manifest/registry JSON uses direct write_text; registry creation lacks the event log’s writer lock. See [event/manifest publication (line 864)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/adventure_events.py:864) and [registry writes (line 149)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/adventure_registry.py:149).
- Inference: A crash can leave a malformed manifest outside the existing stale-marker recovery case; concurrent creates can lose registry updates.
- Action/gate: Atomic metadata publication, registry locking, and fault-injection recovery tests before Steam—and before relying on valuable long-lived saves. Existing recovery tests should remain, not be replaced.
F13 — Observation: Workshop’s architecture is appropriate, but packaging is still a separate product boundary.
- Observed: The [roadmap (line 343)](C:/Users/roger/Documents/Codex/StarFur Forge/ROADMAP.v5.md:343) separates immutable packages from saves. Current document extraction uses assistant-memory categories and explicitly omits temporary statements ([annotation prompt (line 27)](C:/Users/roger/Documents/Codex/StarFur Forge/pipeline/document_annotation.py:27)).
- Inference: A reviewed import bundle is not yet an installable world; that extraction policy can omit legitimate current scene state.
- Action/gate: Define adventure-import semantics separately from personal-memory extraction. Add quarantine, schema/version/hash validation, compatibility, rollback, and user-data locations before Steam/Workshop. No separate full memory database per NPC is necessary.
Animation breadth, voice, continuous perception, autonomous simulation, procedural characters, and Steam integration can wait. Define their contracts early without implementing them now.
Recommended next 10 baby slices
1. Fix session admission/pinning and add the capacity-plus-concurrency regression.
2. Add an authoritative revision precondition to event append, preserving idempotent retries.
3. Wire that revision through generation, staging, commit, and explicit refresh.
4. Generalize Core-command precedence across document-enabled API requests.
5. Publish nonblocking resident snapshots with a monotonically increasing version.
6. Make apartment polling single-flight and conversation-switch-safe.
7. Unify provider readiness/recovery semantics across preview and execution.
8. Separate annotation transport/validation failures and enforce bounded request deadlines.
9. Harden nested ledger sanitization with injected-extra-field tests.
10. Add explicit provider-disabled startup and a zero-provider apartment regression.
Then: participant perspective selection, annotation jobs, and a second provider contract—not all three simultaneously.
Smallest smoke-test matrix
Use temporary/test-owned adventures and ledger files.
Test	Minimum acceptance
CLI mixed turn	Stage ordinary + typed changes; abort persists nothing; commit persists the complete batch.
Two adventure sessions	External write during generation/staging causes deterministic stale rejection.
API registry at capacity	Busy A plus new B produces no eviction of active state or missing-slot error.
OWU with stale attachment metadata	Core diagnostics/exit/persona controls still dispatch without annotation or generation.
Apartment during slow request	Snapshot remains responsive; switching conversations never renders an older response.
Provider transitions	Preview and execution agree before probe, after failure, and after recovery.
Annotation fault matrix	Invalid JSON, transport failure, valid-empty, and configured fallback have distinct bounded outcomes.
Restart/platform check	Committed state survives; ephemeral state resets honestly; lock/recovery cases pass on Windows and WSL.


Run both platforms’ filesystem cases on their actual filesystems; a Windows pass does not establish WSL or cross-filesystem behavior. Live-model quality is a separate opt-in test, not required for deterministic regressions.
Roadmap inconsistencies and proposed corrections
- Low — authority ambiguity: [ROADMAP.md (line 6)](C:/Users/roger/Documents/Codex/StarFur Forge/ROADMAP.md:6) remains authoritative; v4 and v5 explicitly remain proposals. Adopt one current roadmap explicitly, preserving the others as snapshots. Safe to defer, but resolve before planning another long run.
- Low — stale current-position text: [v5’s introduction (line 37)](C:/Users/roger/Documents/Codex/StarFur Forge/ROADMAP.v5.md:37) says the next loop is the coordinator, while later sections document completed coordinator, routing, and apartment slices. Replace this with C3 foundations + E1/H0 integration hardening.
- Narrow “stale-state protection completed” and “pinned sessions completed” claims to the cases actually tested until F1/F2 are fixed.
- Describe annotation retries as implemented: transport failures currently enter the same retry path; schema-valid empty output is accepted.
- Mark AdventureParticipantView as implemented but not integrated or perspective-complete.
- Move zero-provider startup and responsive snapshots ahead of further apartment polish. They need not wait for broad tools/media.
- Preserve the distinction between metadata/import bundles, validated installable packages, and durable user saves.
Open design questions
- Are simultaneous writers to one adventure supported, or should Core enforce one active writer?
- Should failed generation preserve manually staged drafts? Current behavior and blanket “abort on failure” guidance need one explicit policy.
- Which real-world memories may accompany a persona into an adventure?
- Does “public resource” mean visible to the player, every NPC, or only designated participants?
- Should annotation continue after disconnect, cancel, or become a resumable job?
- Which resident state is shared across conversations, and which survives restart?
Overall readiness estimate
Controlled local prototype: viable. Basic Murr apartment: already present. Broad rewrite: unnecessary.
Concurrent adventures, specialist routing, and autonomous participation: not yet acceptance-ready. Steam release: still substantially ahead.
A single completion percentage would be misleading. The next useful milestone is a responsive, provider-optional apartment over concurrency-safe Core state, with the ten slices above providing a concrete path toward it.


2:06 AM