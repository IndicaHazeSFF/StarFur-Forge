# StarFur Forge: project context and architecture map

Reconstructed 2026-10-31 from repository guidance, roadmap, implementation, test code and recorded slice evidence, with Roger's recovery brief supplying explicit product intent. This is an orientation map, not new development authority, a replacement roadmap, a security certification or a claim that all tests were rerun. Read [AGENTS.md](AGENTS.md) first; use [next.steps.md](next.steps.md) for the changing checkpoint and [session.files.md](session.files.md) for pending deployment files.

## 1. StarFur in one paragraph

StarFur Forge is a **local-first Resident Intelligence Platform**: a persistent, inspectable continuity system around replaceable reasoning, language and eventually media providers. Core owns approved memory, provenance, retrieval, permissions, validated fictional-world transitions and presentation read models; models supply language and untrusted proposals. Murr is the flagship resident, but the architecture supports other personas and eventually multiple residents. The intended experience is someone visibly inhabiting the computer through a lightweight apartment and useful shared services, rather than identity depending on one model or an indefinitely surviving chat. Persistent companions, assistants, governed NPCs and research/coding roles are the direction; durable persona self-memory, autonomous work and full zero-provider continuity are not all implemented today. See the authoritative [mission and end state](ROADMAP.md), and the separately proposed [v5 productization/world direction](ROADMAP.v5.md).

## 2. Non-negotiable architecture

- **Core owns canonical state and permission decisions.** A valid model response is still a proposal; narration, confidence, a capability label or an identifier cannot grant authority.
- **Keep complete state separate from bounded views.** Trimming model context must not destroy adventure history or redefine world truth. Presentation reads typed snapshots rather than reconstructing state from prose.
- **Keep namespaces separate.** Shared human-controlled assistant memory, project lore, persona-local runtime, roleplay scope and adventure-local continuity have different owners and lifetimes. The existing general memory domain validator supports `personal` and `project:<slug>`; adventure/persona namespace concepts do not imply arbitrary new SQLite domains are already supported.
- **Providers are replaceable dependencies.** Core retains commands, validation, routing and review semantics. A provider's version, configuration or declared digest is not independently measured deployment security.
- **Instructions are advisory.** Protected values must be filtered before model disclosure. Hidden resources, sensitive authority material and internal relationship meters are not protected merely by asking the model to keep them secret.
- **Effects require their own explicit path.** Package declarations, chat text, source documents and discovery links cannot execute tools or mutate state. Local tool authority is distinct from shared API/chat access.
- **Failure does not imply rollback of external work.** Local interruption fences acceptance; it is not verified provider termination. Unknown external outcomes cannot be replayed automatically.
- **Identity should survive model absence and replacement.** This is a design requirement with implemented data/presentation foundations, not yet complete durable resident continuity.

## 3. Current project position

Working paths include shared CLI/API assistant orchestration; persistent assistant-memory proposals and explicit approval; deterministic retrieval and one-hop associations; persona selection and ephemeral runtime state; explicit adventure history, staging, review and commit; synchronous reviewed document intake; a read-only apartment; and trusted-local brokered public-web/research controls. Fake-provider tests cover many boundaries, while particular live-smoke claims are recorded separately in the roadmap/changelog.

The active recovered track is **disconnected private annotation jobs**. Store, results/checkpoints, processor, runtime binding, maintenance/submission/inspection controls, locality contracts, loopback transport and model-declaration foundations exist. There is no public processing worker/control. Actual deployment/artifact/execution verification and exact-job disclosure consent remain prerequisites. Do not restart completed declaration work or mistake this one frontier for StarFur's entire purpose.

Latest recorded WSL full regression: **1,353 tests, one expected platform skip**, plus the disposable CLI helper's workflow pass. These are prior development results, not tests run during this reconstruction or Roger's manual acceptance. Current cycle and backup state belong in `next.steps.md`; this document deliberately does not own a second test counter.

## 4. Architecture map

```text
Terminal / authenticated local API / optional OpenWebUI Filter / apartment
       |                          apartment reads bounded snapshots only
AssistantApplication             (no inference from displayed prose)
       |-- isolated, locked ephemeral conversation slots
       |-- trusted-local tool/research controls and session broker
       |-- document review/context services
       `-- AssistantSession: Core commands, chat/context and turn orchestration
              |-- SQLite assistant memory -> retrieval -> visibility -> ContextManager
              |-- PersonaRuntime -> BehaviorContext / ResidentAction
              |-- Adventure registry -> event log -> complete reducers -> bounded views
              |-- explicit candidate generation -> review -> staging -> commit
              `-- task profiles / route planner / capacity / Focus Mode
                          |
              replaceable provider adapters (primarily local Ollama)

Separate explicit surfaces:
  lore pipeline -> structured SQLite / managed canon / external Chroma
  annotation-job CLI -> private POSIX store maintenance (processing disconnected)
  evaluation commands -> synthetic fixtures / explicit experiment ledger
```

`pipeline/application.py:AssistantApplication` is the shared facade, not a monolithic persistence engine. `pipeline/assistant.py:AssistantSession` still owns much command dispatch and orchestration. `pipeline/api.py` and `starfur.py` adapt those services; they must not create competing truth or provider policy.

## 5. Major subsystem map

Module paths in this table are under `pipeline/` unless otherwise stated. Interfaces are navigation hints, not permission to run maintenance or contact a provider; check `docs/COMMANDS.md` and source before execution.

| Subsystem and purpose | Owners and authoritative data | Current interface/status | Limits and direction |
|---|---|---|---|
| Shared memory, provenance and retrieval | `db.py`, `domains.py`, `memory_proposal_validation.py`, `retrieval.py`, `persona_visibility.py`; SQLite active memories, proposal/evidence/association rows | Implemented: `memory`, `proposal`, explicit remember/forget, `assistant-context`, bounded introspection | Pending proposals are not retrieved truth. Approval is transactional; forgetting is soft. Production assistant retrieval is deterministic; semantic/hybrid strategies remain fixture-only. Temporal/multihop expansion is later. |
| Lore ingestion and semantic corpus | `prechunker.py`, `chunker.py`, `proposal_pipeline.py`, `annotator.py`, `sync.py`, `canon_writer.py`, `ingest.py`, `rag.py`, `query.py` | Implemented manuscript/chapter analysis, structured facts and managed export; Chroma supports corpus retrieval | Structured sync uses generated `canon/chapters/**/*.md`; semantic ingestion has broader `canon/` scope. Source cleanup/reindexing can be destructive and is not an audit operation. Preserve human Markdown outside managed regions. |
| Persona and behavior | `persona.py`, `persona_state.py`, `persona_registry.py`, `persona_runtime.py`, `persona_development.py`, `persona_attention.py`, `emotion.py`, `relationship.py`, `momentary_state.py`, `behavior.py` | Declarative identity, `persona list/current/use/inspect`, bounded runtime/development/relationship snapshots, visibility filtering | Runtime is restart-ephemeral. Explicit authorized signals and verified learning evidence are distinct from chat inference. Durable `persona:<id>` memory, learning execution and richer onboarding remain future policy/storage work. |
| Adventure continuity | `adventure_registry.py`, `adventure_events.py`, `adventure_session.py`, state/relationship/knowledge/resource reducers, correction/checkpoint/replay modules | Explicit create/load/begin, record/set/resource, corrections/retractions, checkpoints and separate restart children; append-only events own history | Character belief is not objective truth; qualitative adventure relationships never update real-world persona relationships. Catalog-constrained resources are generic mechanics, not one game's hardcoded rules. Autonomous simulation/engine adapters are later. |
| Adventure candidates and participants | `adventure_turn*.py`, `adventure_initiative.py`, `adventure_participant*.py`; ephemeral inboxes and staged turns over canonical history | Ordinary, typed and narrow public-enum resource candidates; explicit review/select/stage/commit. Participant action generation/review/optional transcript record exists | Generating or recording a suggestion does not perform it. Exact story/turn/origin guards deny stale output; cooldown counters reset with session lifecycle. Governed NPC autonomy and durable participant memory are not connected. |
| Provider runtime and resource cooperation | `providers.py`, `provider_registry.py`, `task_profiles.py`, `task_routing.py`, `provider_state.py`, `provider_workload_gate.py`, `provider_process_gate.py`, `provider_resource_policy.py` | Replaceable completion contracts, typed tasks, finite configured routes, observed lifecycle, local concurrency and opt-in cooperating-process lock; `routing`, `model`, manual `focus mode` | Planning is not execution authority. Capability declarations are not observed enforcement. Focus Mode defers balanced/background work; it is not automatic process detection or GPU/CPU budgeting. Keep-alive requests do not prove unload. |
| Tools, permissions and execution | `tool_registry.py`, `tool_contracts.py`, `tool_permissions.py`, grants/approval/prerequisite/broker/router modules, `tool_runs.py`, `sandbox*.py` | Trusted-local `tool` lifecycle; durable payload-free run-journal primitive; executable narrow web fetch and opt-in search adapters | `sandbox.run` remains non-executable by default. Hyper-V/IPC/image/readiness contracts do not create a deployed supervisor. No arbitrary shell executor or hostile-code isolation is established. Shared chat/API denies tool controls. |
| Public research | `factual_research_policy.py`, `research_*.py`, `tool_web*.py` | Explicit search/fetch quarantine, local cited-claim review, relationship review/brief, and deterministic explicitly unverified answer presentation | Ordinary chat's narrow research-required categories stop before generation; automatic research is not wired. Source diversity is not independence/corroboration. No automatic canonical memory, learning or adventure promotion. |
| External document intake | `document_intake.py`, `document_prechunker.py`, `document_annotation.py`, `document_review.py`, `document_context.py`; optional OpenWebUI Filter | Authenticated prepare/annotate/review/context APIs; explicit candidate handoff to pending proposals or adventure import staging | UTF-8 text/Markdown only; one attachment per Filter turn. Synchronous large jobs can outlive clients. Reviews/source context expire and disappear on restart. No automatic persistent semantic indexing of uploads. |
| Private annotation jobs | `document_jobs.py`, `document_job_store.py`, result/status/processor/runtime/control/inspection/locality/loopback/model modules | Opt-in POSIX persistence and local submit/list/status/resume/delete/inspect controls; internal processor and transport foundations tested with fakes | Fixed original 24h retention, owner lock and stale-attempt fences. Resume changes intent only. Locality/consent producer and public processing remain disconnected; native Windows store denies. |
| Resident/apartment presentation | `resident_snapshot.py`, `resident_action.py`, `resident_presentation.py`, `system_metrics.py`, `persona_assets.py`, `persona_asset_resolver.py`, application/API shell | Bounded `ResidentSnapshot`, explicit visible actions, authenticated snapshot endpoint and static apartment shell; fixed Murr idle asset route | `ResidentAction` is presentation state, not a scheduler. Metrics are passive aggregates, not resource admission. Rich animation, ambient presence, perception, durable actions and Steam/Workshop installation are later. |
| Evaluation and experiments | `retrieval_eval.py`, `benchmark.py`, `benchmark_comparison.py`, `experiment_ledger.py`, adventure/participant/routing/resource/document evaluation modules | Synthetic fixtures, opt-in append-only aggregate ledger, bounded scaling manifests and pure comparison-eligibility checks | Declared metadata compatibility is not measured quality, verified deployment or statistical significance. Controlled ablations/full scaling campaigns are research work, not established results. |

## 6. Persistence and lifetime map

| State | Owner / lifetime / authority | Recovery implications |
|---|---|---|
| Assistant memories, pending/reviewed proposals, evidence and associations | `db.py`; persistent SQLite, normally `data/starfur.db`; domain-scoped shared canonical records and separate pending evidence | Approval links both records and evidence; rejection preserves history; soft forgetting preserves provenance. `db.connect()` can add schema, so even opening production storage is not assumed read-only. |
| Lore structured records and canon Markdown | SQLite lore tables plus human-authored/StarFur-managed Markdown regions; generated chapters are structured-analysis input | Some source-derived rows are rebuildable; confirmed facts, history and human-authored text cannot be treated as disposable caches. Annotation failure after cleanup can leave derived source records absent until explicit retry. |
| Semantic index | External Chroma; corpus-derived search data | Rebuildable in principle, but reindexing deletes/replaces records and invokes embeddings. Never reset it as routine testing. Assistant semantic benchmarks use a separate temporary collection. |
| Sync/performance runtime records | `data/sync_manifest.json`, `data/perf.jsonl` and configured outputs | Preserve during recovery. Hash/version invalidation records are not canonical human memory and are not permission to rerun ingestion. |
| Conversation state | Application/session memory; bounded recent turns, selections, confirmation state, routing observations, roleplay mode, focus setting | Eviction/restart loses it. Conversation IDs select slots; they are not authentication, namespaces or permission grants. |
| Persona state | Declarative installed identity/config plus `PersonaRuntimeRegistry` in memory | Dynamic/momentary/development/relationship/action state currently disappears on restart. Do not claim durable persona learning or store it as user facts to fill the gap. |
| Adventure workspace | Registry/manifest plus validated append-only `events.jsonl`; optional catalog/checkpoint references | Events are authoritative; complete state/resource/perspective reducers and replay selections derive from them. Locking, idempotency and narrow pending-write recovery belong to the store. A checkpoint binds a verified prefix; restart creates a separate child, not a rewind. |
| Adventure transcript, import staging and mappings/bundles | Separate append-only workspace records | Transcript records what was presented, not what happened. Imports/mappings are noncanonical plans until exact typed commit. Neither is a canonical replay source. |
| Adventure runtime | Mounted projections, participant roster/views, candidate inboxes, staged drafts, roleplay binding and pacing in session memory | Staged drafts are not saved events; abort/lifecycle changes discard them. Mount/refresh rebuilds views; live generation/review must reject changed origins. |
| Synchronous document reviews | Bounded `DocumentReviewStore`; default 24h TTL, configurable within documented bounds; original prepared document held in memory | Restart/expiry requires re-annotation. Selected candidates can enter pending proposals only through explicit server-side selection/confirmation. A review is not a durable job. |
| Private annotation store | Explicit existing owner-only POSIX directory; bounded plaintext source/metadata/result/checkpoints, lifetime OS owner lock | Original fixed 24h lifetime, no-follow regular single-link records, bounded atomic replacements, stale-attempt fencing. Opening performs acknowledged maintenance. Malformed/abandoned writes fail closed; logical deletion is not secure erasure. No default production root is enabled. |
| Tool authority, artifacts and research reviews | Session broker/grants/prerequisites/quarantine and `RR`/`RX` reviews are bounded ephemeral objects; optional `ToolRunJournal` records intent/outcome durably | Journal recovery makes unfinished runs unknown rather than reauthorizing execution; it does not persist source/prompt/output payloads or resurrect grants. Do not infer a journal is configured merely because its primitive exists. |
| Experiment ledger | Explicitly selected JSONL destination under `experiment_ledger.py` schema | Aggregate evidence and declared run metadata only; not application memory. Historical rows are not silently rewritten, independently attested or guaranteed concurrent-safe. |

This reconstruction did not open any production database, adventure workspace, private job store, Chroma collection, experiment output or local secret configuration.

## 7. Request and data flows

### Normal resident chat

1. CLI/API enters `AssistantApplication.respond_completion()` with a selected ephemeral session. Per-session locking and request-scoped streaming protect response metadata.
2. Whole-message framing, pending confirmation, exact commands/help/introspection and Core namespace handling precede generation. Shared chat/API cannot assert trusted-local tool authority.
3. `AssistantSession.respond()` applies the narrow factual-research classifier. `research_required` returns a deterministic notice; it does not launch research, retrieve memory or ask a model to guess. Unclassified chat is not thereby proven grounded.
4. The session invokes its retriever; active same-domain memories and one-hop association results pass persona scope/confidence filtering. `ContextManager` assembles policy, persona/behavior, bounded recent history, selected facts/details and any separately authorized document/adventure context.
5. Task routing, Focus Mode and provider capacity gate the adapter call. Core consumes completion text and closed finish metadata, not provider reasoning/tool payloads. Stream failure/interruption does not commit a partial turn; a reported output limit skips proposal extraction.
6. A completed reply enters bounded session history. Eligible user observations may produce validated **pending** memory proposals through the configured writer; the assistant reply is not factual evidence. Nothing is automatically approved as canonical memory.

### Memory proposal and correction

User observation or explicitly selected document candidate -> Core-owned domain/source -> strict candidate validation -> pending proposal/evidence upsert -> explicit inspection/review -> approval transaction -> active canonical memory and bidirectional provenance. Same evidence is idempotent; distinct reinforcing evidence can update a pending record without approval. Explicit corrections/forgetting retain the underlying history. `proposal approve all` has its own exact follow-up confirmation; it is not a model-selected batch. Explicit remember is a separate user command, not permission for model prose to write facts.

### Adventure turn and reviewed import

Explicit mounted adventure + active staged turn -> bounded authoritative context and separately framed completed-turn text (or the latest explicit adjacent user/narrator transcript pair) -> task provider -> strict ordinary/typed/resource candidate validation -> workspace/origin-bound review inbox -> exact user selection/staging -> `AdventureEventLog.append_many()` under lock with request ID and expected event count -> fresh complete projections and bounded replay/context. Generation never commits automatically. Public-enum resource generation is narrower than the full manual catalog-operation surface.

Document review -> exact adventure import staging -> user-authored mapping -> explicit typed commit is another path. For state/relationship/knowledge/resource commits, the operator supplies validated mutation values; imported prose provides provenance, not executable mutations. Corrections and retractions append audit history rather than deleting old events. Checkpoint-based restart forks a verified prefix into a new workspace.

### Participant action

Exact `adventure begin` binding + matching staged turn + explicit participant/trigger -> roster-specific perspective -> declared initiative/pacing policy -> bounded untrusted source frame -> one routed provider proposal -> policy/story-generation/turn/origin rechecks -> `TP-###` review. Explicit record may copy one candidate and captured user text into the **noncanonical** transcript. Consequence generation, staging and commit remain separate actions. Eligibility does not schedule a participant; no autonomous loop is implied.

### Research and tools

Explicit trusted-local public query -> exact search broker lifecycle -> quarantined ranked URL/title discovery artifact -> explicit selected rank -> fresh fetch lifecycle -> bounded untrusted source artifact -> permitted local source packet -> strict cited-claim generation -> `RR` review -> optional relationship generation/`RX` review and deterministic briefs. `tool research search` composes the explicit query/rank steps; it does not choose sources autonomously.

`tool research answer` exists as an explicit deterministic **source-backed-unverified** presentation; an optional question must match its binding. It is not a newly verified factual answer or automatic normal-chat publication. Search results, citations, multiple hosts and relationship labels do not establish truth. No memory/learning/adventure write follows automatically.

The underlying tool lifecycle is descriptor/proposal -> exact grant -> one-use approval -> bound short-lived prerequisites -> revalidated invocation -> selected enabled supervisor/connector -> bounded outcome/artifact. Some local convenience commands compose these steps for literal user input; they do not bypass them. DNS/preparation and network execution are separate effects. After an ambiguous post-launch outcome, recovery records uncertainty rather than retrying.

### Documents and private jobs

Synchronous API/Filter text -> deterministic preparation/profile/chunks -> routed bounded annotation attempts -> strict candidates and per-chunk failure accounting -> expiring review. Source-context chat retrieves lexical chunks from that review using the actual user question; it does not inject the whole attachment or retain it in chat history. Explicit handoff creates pending proposals, not approved memories. Reordered extraction uses content-derived candidate provenance rather than relying on display ordinals.

Private job submit -> confirmed plaintext storage -> restart-safe intent/checkpoints -> internal processor seam is a separate, incomplete path. Public controls presently stop at maintenance, submission and separately confirmed inspection; `resume` only queues intent. Completion or a saved configuration fingerprint does not prove extraction quality, local execution or consent. The verifier/consent gates must precede connecting processing.

## 8. Authority matrix

This describes implemented boundaries and intended package restrictions, not unrestricted power for any actor. Local OS-user trust is not hostile-host isolation.

| Actor/component | May read | May propose | May mutate canonical state | May grant permission | May perform external effects |
|---|---|---|---|---|---|
| User/operator | Authorized UI/CLI views; separately confirmed private inspection | Yes, explicit input/selections | Through validated explicit Core commands | Through supported trusted controls | May authorize scoped supported effects |
| Core/application | Data permitted by the invoked path/domain/policy | Yes, including validated model candidates | Only through designated validated writers | Enforces and records authorized decisions, not model self-approval | Through enabled adapters after gates |
| Model/provider | Only supplied bounded task context | Untrusted text/candidates | No direct writer | No | Not through generated tool text; the provider call itself is a separately controlled disclosure |
| Persona package | Declarative identity/assets/policies supplied at load | Presentation guidance, not grants | No | No | No executable behavior by declaration |
| Adventure package | Declarative scenario/catalog/participant definitions | Scenario data, not canonical inferred events | No direct authority | No | No executable authority by package contents |
| Presentation client | Authenticated bounded views, except static public shell/art | Explicit user requests | Requests Core operations; does not write stores directly | Cannot fabricate trusted-local authority; conversation keys are not grants | Own client behavior is outside Core; Core effects remain gated |
| Tool broker | Exact proposal and trusted grant/prerequisite bindings | Tracks proposals | No general memory/world authority | Validates/consumes operator-authorized records | Dispatches only exact enabled one-use invocations |
| External integration/provider adapter | Explicitly disclosed input | Reduced untrusted results | No independent Core truth ownership | No | Only the configured, separately authorized transport path |

## 9. What reaches model context

Normal prompts use selected active memory summaries **and details**, not database dumps. Persona visibility applies after ranking and also constrains introspection; scope metadata is not inferred from prose. Source evidence/provenance can be retained internally without being copied wholesale into normal chat. Engine policy is separate from replaceable persona style.

Adventure complete projections outlive prompt selection. Hidden resources and resource-event free-form summaries stay out of ordinary adventure prompts; participant views add subject/visibility filtering and whole-fact character budgeting. Relationship-meter redaction occurs before fictional prompt construction unless explicit diagnostics are requested. Character `knows`, `believes` and `uncertain` remain distinct perspectives. Transcript prose remains untrusted input even when explicitly selected as a generation source.

Document/research source text is explicitly framed as data. Research packets exclude broker authority/network internals; relationship requests use bounded reviewed claim metadata, not full source bodies. JSON framing, schemas and model instructions improve conformance but are not prompt-injection immunity. Strict output validation and separate mutation/effect gates remain necessary.

Bounded public diagnostics are not proof that every debugging mode is content-free: `retrieval_debug.py` verbose/trace modes can expose prompts/content and must be handled as sensitive. Routine snapshots and experiment records must not turn into private conversation logging. Token estimates, model settings and acceptance deadlines are not equivalent to actual server resource enforcement.

## 10. Evaluation and research foundation

The research question is how much continuity and competence can come from persistent architecture rather than larger models or longer contexts. Roger's recovery brief confirms eventual raw-model/retrieval/association/full-system ablations. The roadmap also calls for reproducible model-size/quantization comparisons. These are hypotheses to measure, not current superiority claims.

| Existing evidence family | What it can establish | What it does not establish |
|---|---|---|
| `tests/fixtures/retrieval_*`, `retrieval_eval.py` | Temporary-DB retrieval IDs, Recall/Precision, false positives, lexical/semantic/no-match tiers and repeatability; explicit temporary-Chroma semantic experiments | Production semantic chat policy or whether a model used retrieved facts correctly |
| `adventure_eval.py`, turn candidate/orchestration/resource evaluations | Deterministic state/replay/resource integrity, rejected envelopes, stale-origin and bounded commit behavior using synthetic data | Narrative quality or a live autonomous world |
| `adventure_participant_eval.py` | Eleven-case v2 synthetic lifecycle evidence, including missing/stale story binding and explicit fresh recovery | Durable NPC memory, live-model intelligence or provider termination |
| `task_routing_eval.py`, `provider_resource_eval.py` | Declarative portability/admission decisions and reason labels | Actual hardware enforcement or installed provider capability |
| `document_annotation_eval.py`, `document_annotation_quality_eval.py` and public fixtures | Reliability counts/attempts versus separately scored extraction-quality criteria | Transport/schema success alone does not mean useful facts; historical large-upload observations are not privacy-safe general benchmarks |
| `benchmark.py`, `benchmark_comparison.py`, `experiment_ledger.py` | Bounded manifests/scaling plans, aggregate records and strict declared-evidence comparison eligibility | Independent measurement/attestation, a wired live scaling runner, statistical significance or permission to log private data |

Keep separate: a fact existed -> retrieval selected it -> correct bounded context reached the provider -> the provider used it -> Core accepted/rejected output -> the correct canonical transition occurred -> the user-visible result was useful. A failed link is not automatically a model-quality failure. Historical ledger records may lack comparison commitments; never invent missing hashes or controls.

## 11. Development frontier and gates

**Current active work:** recover durable orientation and finish the private annotation deployment-verification design. The completed request/acquisition/declaration binding, final retention/deadline fixes, newer listing metadata compatibility and one-command operator workflow are recorded in the October 31 changelog/sprint.

**Completed safe prerequisite:** M1 in `pipeline/document_job_manifest.py` is a pure bounded schema-2 decoder over supplied bytes. Its focused/subsystem WSL verification passed; see the October 31 codec sprint. It returns immutable redacted descriptors and a separately named raw-input hash, never locality, readiness or API-digest proof. No files/services or layer payloads are opened, and later trusted-evidence gates remain unchanged.

**Next authority-bearing gate:** targeted review of the plan's measured evidence producers remains pending. Resolve manifest/blob/release-decoder identity comparison, trusted executable/server evidence, sufficient measured local execution and freshness/drift handling, and exact-job/attempt consent consumption. The chosen server location is StarFur-Forge WSL. Historical process/cloud-disable/listener observations and version declarations are not a complete verifier. A wildcard listener alone does not violate the literal-loopback client rule. M1 does not clear this review; ask Astra only for unresolved reasoning/security/design ambiguity.

After the design review, implement the agreed small pure identity/codec boundary before opt-in bounded filesystem/server verification; connect processing only after required deterministic and separately authorized live gates. Storage confirmation and result-inspection confirmation cannot be reused as disclosure consent. Do not add another declaration wrapper and call it measured locality.

**Operator acceptance:** [user.smokes.md](user.smokes.md) contains the temporary concise workflow runbook; Roger's results are pending. Developer helper success does not substitute for that review. A live private-processing smoke is unavailable while processing remains disconnected.

**Later product work:** durable persona-local continuity and zero-provider resident actions; richer apartment/ambient presence; permissioned perception/media/voice; safe package installation/Workshop/Steam; bounded scheduling and verified learning. Persistent spatial worlds/engine orchestration build on adventure truth/replay, not a parallel prose-owned world. Their order is governed by `ROADMAP.md`, with proposed v5 offering additional design context.

**Research only:** controlled cognition ablations, broader model portability/size studies, richer autonomous residents and multi-agent worlds. Existing primitives are not a promise that these loops are complete.

## 12. Known issues, discrepancies and missing evidence

### Known safe bugs

[safe.bugs.md](safe.bugs.md) records terminal paste/Ctrl+C edge behavior; relationship-meter leakage mitigated structurally but awaiting its stated live closeout; long synchronous annotation disconnect handling mitigated; redundant identical manual adventure staging; invalid/empty typed model outputs that correctly fail closed; and an ordinary-chat exact-response suffix failure. These are historical reports, not all independently reproduced here. They are not permission to weaken schemas, strip arbitrary output or replay failed operations. Later interruption fixes do not automatically close every older terminal-input case.

### Documentation drift to interpret explicitly

- `AGENTS.md` retains older Stage 3 prose saying proposals remain non-persistent. Current `_proposal()` uses an injected proposal writer; the standard application factory supplies `upsert_assistant_memory_proposal`. `db.approve_assistant_memory_proposal()` and proposal tests establish the separate approval transaction. The operative distinction is **pending persistence versus canonical approval**, not no persistence at all. Do not expand writer authority from this observation.
- Older `AGENTS.md` intake paragraphs call document intake future work and uploads unintegrated; later module guidance, `integrations/openwebui/README.md`, the Filter and API tests describe the implemented optional bridge. Its existence does not attest the operator's currently installed Filter version.
- Some module descriptions retain historical “future/dormant” language after later callers were added. For example, research coordinators remain nonpublishing primitives, but a separate explicit unverified answer presentation exists. Read the composed application path, not one module's historical description, before declaring a whole feature absent or complete.
- Roadmap heading dates and broad dependency summaries lag later appended completion records. The October 31 “current recovery checkpoint” paragraph preserves an earlier 3/10 counter; `next.steps.md` records the later 8/10 checkpoint. Treat dated outcomes as history and the rotating handoff as the current operational counter. v5's “ACTIVE NEXT GATE” umbrella headings are not authority to redo completed C3 slices or adopt v5.
- The root authoritative roadmap is `ROADMAP.md` v4. `ROADMAP.v4.md` is a preserved earlier design document despite the similar name; `ROADMAP.v5.md` explicitly remains proposed. Earlier versions, `docs/ROADMAP.md`, `docs/StarFur Forge Roadmap.md` and backup files are context, not parallel authorities.

This slice records these discrepancies rather than mass-rewriting development rules or historical evidence. Resolve a disputed ownership rule explicitly before changing its behavior.

### Verification limits

This is a source/document reconstruction with selected implementation and test-path inspection, not an exhaustive security audit or live acceptance run. Recorded fetch/Tavily/research smokes remain historical evidence; Brave native search is separately marked live-smoke-required in the roadmap. Neither old smoke results nor current fake tests establish today's deployment/configuration. Full security, zero-provider persistence, hostile-code sandboxing, private-job locality/consent and automated factual publication are not proven by absence of a finding here.

Local WSL HEAD and local `origin/main` were read as `eade99aa73aeac847fc679b135acf7cb83dd31ac`; Windows HEAD remains the separate older `955d42b62ec11d554b846ec527af4ec2d3acb7b1` and has no local `origin/main` reference. No remote was contacted. Windows-versus-WSL Git metadata differences do not replace exact queued-file hash comparison or prove GitHub backup. Keep experiment directories and unrelated pre-existing changes outside this slice.

## 13. Safe development workflow

Existing user instructions and [AGENTS.md](AGENTS.md) remain canonical. The recovery brief and this file grant no additional execution authority and do not change commit cadence.

Use Windows as the editing source -> record exact changed paths/pre-copy baselines -> verify/copy only that queue to the exact WSL checkout -> required provider-free WSL tests -> scoped GitHub backup at the established ten-successful-required-run cadence. Keep `CHANGELOG.md`, roadmap completion/dependencies, guidance and durable sprint evidence current; record unchanged reviews when no factual update is needed. A clear copy queue is not a backup. Never infer commit scope from the whole dirty tree.

Read `next.steps.md` and `session.files.md` after interruption; inspect actual state before assuming a copy, test or commit completed. Keep `user.smokes.md` until Roger revokes it. No optional test is needed for this documentation-only slice; required-run accounting stays in the rotating handoff. Preserve existing runtime stores/configuration, and never mirror/reset a checkout or convert a synthetic passing test into deployment proof.

Roger normally leaves WSL running in PowerShell. When actively messaging without saying away/at work, assume it is available for authorized operations and leave its lifecycle alone; this assumption is not a measured service/readiness claim. If it is unavailable or a boundary fails, report the actual condition rather than repeatedly starting/stopping or bypassing it.

Safe scoped correction of ordinary known failures is authorized. Stop on uncertain effects, copy/hash/path/permission problems, independent WSL changes, possible runtime corruption, security-boundary failure or unexpected external effects; request higher-model review for unresolved security/design reasoning. Check quota between substantial slices and leave handoff time near the user-specified threshold. A context summary must never weaken these rules.

## 14. Rationale that must survive chat loss

- **External continuity is the product and research hypothesis.** Swapping a model should change reasoning quality, not erase the user's approved memories or fictional-world history. Current restart-ephemeral persona state is an acknowledged gap against that goal.
- **Separate truth, presentation and perspective.** A narrator can describe an action that has not been committed; a participant can believe something false; a transcript can preserve wording without becoming replay truth. Conflating these would make model prose a hidden writer.
- **Retain complete state while bounding context.** More history should not mean an ever-growing prompt or permanent loss of older canonical facts. Replay and projections are selective views over retained evidence.
- **Review and typed mutation preserve user agency.** Pending memory proposals, document candidates, adventure candidates and research reviews have different owners. Reusing a display ID or generic “approve” across them would erase distinct authority boundaries.
- **Quarantine discovery before factual use.** Search ranking is not support; source citation is not verification; relationship labels are not corroboration. The explicit unverified answer gate preserves those distinctions.
- **Use conservative failure semantics.** Configured pre-request fallback, annotation's bounded retries and non-replaying research/tool paths are different contracts. Local interruption or a lost response must not silently duplicate external effects or canonical writes.
- **Keep resident behavior honest.** Interest, skill, action and emotion records require their own explicit evidence/transition rules. A provider must not invent off-screen work, expertise, history or emotional obligations to make the resident feel persistent.

These reasons are supported by the roadmap invariants, module contracts and implementation history; they do not add a new architecture or silently choose unresolved verifier policy.

## 15. Terminology and identifiers

| Term | Meaning here |
|---|---|
| Core / resident / persona | Core is the policy/state/continuity implementation; resident is the intended persistent experience; persona is declarative identity plus its bounded runtime presentation/state. |
| Canonical / projection / review | Canonical is accepted state owned by its designated store; projection is a derived bounded or complete view; review is untrusted material awaiting a separate decision. |
| Proposal / candidate / provenance | Suggested data, not permission; a typed/displayed selection unit; and the recorded source/evidence/history supporting a record. |
| Adventure / participant / transcript | Isolated fictional workspace; governed persona/NPC perspective within it; and noncanonical presentation history. |
| Resource | Scenario-declared generic value with Core kinds/bounds/operations/visibility, not automatic game logic. |
| Provider / route | Replaceable completion/media/integration adapter; Core's declared task/provider/model selection path. Neither is canonical truth. |
| ResidentAction / ResidentSnapshot | Explicit persona-local visible activity (not scheduled work); bounded public read model (not an authority or full database). |
| `M-###`, `P-###` | Compact domain-scoped memory/proposal references; not authentication. |
| `DR-...`, `C-###`, `JC-####` | Ephemeral document review, its exact candidate ordinal, and private-job inspection display reference. They are not interchangeable proposal IDs. |
| `AE-...`, `AT-...`, `AI-...`, `AB-...` | Adventure event, transcript, staged import and import bundle references, respectively; only event history establishes canonical changes. |
| `TC-###`, `TP-###`, `TR-###` | Ordinary turn candidate, participant-action candidate and public-resource candidate selection references; none means an action was committed. |
| `TF-...`, `RR-...`, `RX-...` | Quarantined web artifact, cited-claim review and relationship-review references; not source trust, grants or publication permission. |

## 16. Evidence and source-of-truth hierarchy

1. **Current source and tests establish implemented behavior**, with test code distinguished from recorded execution and live deployment evidence. Disagreement with a rule is a discrepancy to resolve, not permission to bypass the rule.
2. **Current user instructions and `AGENTS.md` govern development, ownership and safety.** Applicable nested guidance also matters; this reconstruction found only the root `AGENTS.md` in the repository file inventory.
3. **`ROADMAP.md` governs intended direction and milestone dependencies.** Read appended completion records alongside broad stage headings. v5 remains proposed unless Roger explicitly adopts it.
4. **`CHANGELOG.md` and sprint records preserve implementation/test history.** `next.steps.md` and `session.files.md` distinguish active work, pending copies and backup state; `user.smokes.md` tracks temporary operator acceptance.
5. **Proposed/historical roadmaps and command/integration docs provide context.** They do not override current rules, grant effects or establish current deployment.
6. **`starfur.context.md` is the map.** Update it for material ownership, authority, persistence, data-flow or product-loop changes. Small fixes belong in the changelog; milestone changes in the roadmap; development rules in AGENTS. Do not grow this into another chronological log.

Reconstruction evidence: root AGENTS; authoritative/proposed roadmap sections and historical roadmap identities; recent CHANGELOG; [annotation audit sprint](2026-10-31.annotation-audit-followup.sprint.md); current handoff/copy/runbook records; private verification draft; `safe.bugs.md`; command reference and OpenWebUI README. Implementation anchors include application/session request and tool gates, database approval/upsert, retrieval strategies, persona runtime, adventure commit/participant generation and storage contracts, document-job controls, routing, broker/journal, research answer policy and benchmark contracts. Corresponding `tests/test_application.py`, `test_api.py`, `test_assistant_proposals.py`, `test_persona_runtime.py`, adventure/participant, tool/journal, document-job and benchmark comparison families provide navigation to executable contracts. See [context-recovery sprint](2026-10-31.context-recovery.sprint.md) for this slice's exact edits, checks and limitations.
