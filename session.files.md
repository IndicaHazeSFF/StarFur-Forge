# Pending copy manifest

## Latest slice copy set — test discovery boundary

- `tests/__init__.py`
- `tests/test_discovery_boundary.py`
- `tests/test_chunker.py`
- `test_chunker.py`
- `tests/test_research_answer_binding.py`
- `tests/test_research_answer_policy.py`
- `tests/test_reset.py`
- `AGENTS.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/COMMANDS.md`
- `session.files.md`

Copy this set only; preserve local configuration and runtime `adventures/` and
`data/`. The preceding participant wording smoke passed. Use explicit `-t .`
for full discovery: tests now have package identity, manual chunker imports
perform no corpus inspection, and shared fixtures import through `tests.*`.
Reset fixtures restore their temporary database setting even on failure.
Native full discovery now reaches a reproducible Windows restore-file denial;
it is not skipped or claimed fixed. Production database/reset behavior is
unchanged. Next gate: WSL full-suite run with no API key or model generation.
Do not run real factory-reset/restore commands or copy any runtime data.
Three discovery-boundary tests passed. Native full discovery reached 1,132 tests
but was not clean: Windows restore-file denial and an intermittent API-test error
remain open. Do not interpret this copy set as a production fix for either.

## Latest slice copy set — participant proposal wording

- `pipeline/adventure_participant_action.py`
- `pipeline/adventure_participant_action_generation.py`
- `tests/test_adventure_participant_action.py`
- `tests/test_adventure_participant_action_generation.py`
- `tests/test_adventure_commands.py`
- `AGENTS.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/COMMANDS.md`
- `session.files.md`

Copy this set only; preserve local configuration and runtime `adventures/` and
`data/`. The preceding source-frame compatibility smoke passed with one candidate
and no state writes. Its action-like wording was a quality issue. This slice adds
proposal-style generation guidance and quotes/escapes original review wording
under an untrusted label; no summary/action rewrite, grammar authority, schema,
profile/budget change, retry, or write behavior was introduced. Next gate: one
participant-generation/review smoke without recording or committing anything.
That WSL wording gate passed; the newer discovery copy set above is current.
Local verification: 404 focused tests passed; full discovery still stops at the
pre-existing root/test-folder `test_chunker.py` import collision.

## Latest slice copy set — participant source-data framing

- `pipeline/adventure_participant_action_generation.py`
- `pipeline/adventure_participant_action_coordinator.py`
- `tests/test_adventure_participant_action_generation.py`
- `tests/test_adventure_participant_action_coordinator.py`
- `tests/test_adventure_commands.py`
- `AGENTS.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/COMMANDS.md`
- `session.files.md`

Copy this set only; preserve local configuration and runtime `adventures/` and
`data/`. The preceding whole-fact selection compatibility smoke passed with
valid no-action output and unchanged state. This slice serializes participant
sources as bounded untrusted JSON data, checks UTF-8/source bytes before provider
use, and reports invalid source only as `input_invalid`. It changes no output
schema, profile budget, authority, retry, canonical state, or memory behavior.
That WSL source-frame compatibility gate passed on 2026-10-14 with one review-only
candidate and unchanged state; the newer wording copy set above is current.
Local verification: 402 focused tests passed; full discovery still stops at the
pre-existing root/test-folder `test_chunker.py` import collision.

## Latest slice copy set — whole-fact participant size selection

- `pipeline/adventure_participant.py`
- `pipeline/assistant.py`
- `tests/test_adventure_participant.py`
- `tests/test_adventure_participant_action_coordinator.py`
- `tests/test_adventure_commands.py`
- `AGENTS.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/COMMANDS.md`
- `session.files.md`

Copy this set only; preserve local configuration and runtime `adventures/` and
`data/`. The preceding count-only context-control WSL smoke passed. The new
selector omits whole already-filtered facts when needed to fit the unchanged
view character ceiling; it preserves smaller views and all complete state.
Context inspection adds only a bounded size-omission count. No persistence,
provider/profile budget change, retry, or autonomous action was introduced.
That compatibility gate passed on 2026-10-14 with valid no-action output and
unchanged state. Oversized cases run in temporary unit fixtures, not installed adventures.
Local verification: 398 focused tests passed. Full discovery remains blocked by
the pre-existing root/test-folder `test_chunker.py` import collision.

## Latest slice copy set — participant context usage

- `pipeline/adventure_participant.py`
- `pipeline/assistant.py`
- `pipeline/command_help.py`
- `tests/test_adventure_participant.py`
- `tests/test_adventure_commands.py`
- `tests/test_command_help.py`
- `tests/test_api.py`
- `AGENTS.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/COMMANDS.md`
- `session.files.md`

Copy this set only; do not copy runtime `adventures/` or `data/`, or replace local
configuration. The preceding participant benchmark/ledger WSL smoke passed.
The new exact control reports only category counts and view character size from
mounted projections; no generation, refresh, event/transcript read, policy
change, or state write occurs. Local focused verification passed 394 tests;
full discovery remains blocked by the existing `test_chunker.py` import collision.
That WSL control/help gate passed on 2026-10-14; the newer copy set above is current.

## Latest slice copy set — participant lifecycle benchmark

- `pipeline/adventure_participant_eval.py`
- `pipeline/experiment_ledger.py`
- `starfur.py`
- `tests/test_adventure_participant_eval.py`
- `tests/test_experiment_ledger.py`
- `AGENTS.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/COMMANDS.md`
- `session.files.md`

Copy this set only; preserve local configuration and do not copy runtime
`adventures/` or `data/`. The WSL registration-access, installed participant
thinking-off, and proposal-phase cancellation/recovery checks passed. The helper
reported an already-registered no-op; no replacement/backup creation is claimed.
Earlier pending-smoke notes below are historical and superseded for these checks.
The new seven-case benchmark uses synthetic responses and temporary workspaces;
only explicit `--record-ledger` appends a bounded result. No key, API server,
model load, actual story generation, or production-memory access is needed.
That WSL CLI/ledger gate passed on 2026-10-12; the newer copy set above is current.
Local verification: 367 focused adventure, ledger, provider, application, and
API tests passed (including the new CLI path). Required full discovery remains
blocked by the existing root/test-folder `test_chunker.py` import collision.

## Latest correction copy set — persisted transcript lock compatibility

- `scripts/restore_action_smoke.py`
- `tests/test_action_smoke_registration_repair.py`
- `AGENTS.md`
- `CHANGELOG.md`
- `docs/COMMANDS.md`
- `session.files.md`

The exact-case helper now accepts the normal optional regular
`.transcript.write.lock` file and preserves, backs up, and rechecks its bytes.
It neither claims that a writer is stopped nor removes/acquires the lock.
Unexpected files, linked inputs, and detected changes remain refused. Stop all
StarFur writers, rerun preview, and apply only after preview passes. Copy no
runtime `adventures/` or `data/`; live repair verification remains pending.

## Latest slice copy set — proposal cancellation and Action Smoke repair

- `pipeline/assistant.py`
- `tests/test_chat_provider.py`
- `scripts/restore_action_smoke.py`
- `tests/test_action_smoke_registration_repair.py`
- `AGENTS.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/COMMANDS.md`
- `session.files.md`

Copy this set without copying `adventures/` or `data/`. The exact-case repair
helper defaults to read-only preview; stop all StarFur writers before its
separate `--apply` step. WSL runtime registration is not repaired by these source
edits. Proposal interruption now retains an already completed reply and returns
the CLI to the prompt with a bounded notice, without retries or partial proposal
writes. Live WSL repair verification, proposal-phase cancellation/recovery, and
the preceding participant thinking-off smoke remain pending. Other runtime
stores, grants, and provider defaults are unchanged.

## Latest documentation copy set — FoxFire Dispatch / ATS Career

- `ROADMAP.md`
- `ROADMAP.v4.md`
- `ROADMAP.v5.md`
- `CHANGELOG.md`
- `session.files.md`

That slice was documentation only: adds the later optional ATS adventure category
and its manual-to-adapter-to-bounded-autonomy gates. It added no smoke. The newer
recovery/cancellation slice above supersedes its unrepaired-code note; WSL
registration and live verification remain pending. Keep the preceding
source/configuration copy set below available.

## Latest slice copy set — structured limits and participant thinking-off

Copy these files for the current WSL participant-action smoke (older entries below are
retained as the cumulative manifest, not an instruction to recopy everything):

- `pipeline/providers.py`
- `pipeline/task_execution.py`
- `pipeline/assistant.py`
- `pipeline/adventure_turn_provider.py`
- `pipeline/adventure_participant_action_coordinator.py`
- `pipeline/research_provider.py`
- `pipeline/research_coordinator.py`
- `pipeline/research_relationship_coordinator.py`
- `config/assistant.json` (preserve local overrides; the only new setting is participant `model_thinking: false`)
- `tests/test_task_execution.py`
- `tests/test_task_profiles.py`
- `tests/test_chat_provider.py`
- `tests/test_adventure_commands.py`
- `tests/test_adventure_turn_provider.py`
- `tests/test_adventure_participant_action_coordinator.py`
- `tests/test_research_provider.py`
- `tests/test_research_coordinator.py`
- `tests/test_research_relationship_coordinator.py`
- `AGENTS.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `docs/COMMANDS.md`
- `session.files.md`

Structured generation now retains `provider_output_limit` without accepting
partial or complete-looking limited JSON, retrying, or publishing candidates or
reviews. The stock participant-action profile requests thinking-off with the
same context/output/residency. Other structured defaults remain unchanged.
The preceding mixed-paste/real-diagnostics smoke passed. Only the participant
profile change needs a live WSL/Ollama smoke; no Tavily key, research fetch,
transcript recording, staging, or commit is needed.
673 focused provider-free regression tests passed locally. The required full
discovery attempt was blocked by the pre-existing root/test-folder
`test_chunker.py` name collision; this slice does not repair those manual
scripts or claim that full discovery passed.

## Pipeline (65)

- `pipeline/adventure_participant_action.py`

- `pipeline/adventure_participant_action_generation.py`

- `pipeline/adventure_participant.py`

- `pipeline/adventure_participant_eval.py`
- `pipeline/experiment_ledger.py`

- `pipeline/assistant.py`
- `pipeline/adventure_turn_provider.py`
- `pipeline/adventure_participant_action_coordinator.py`
- `pipeline/application.py`
- `pipeline/command_help.py`
- `pipeline/command_input.py`
- `pipeline/resident_snapshot.py`
- `pipeline/sandbox_image.py`
- `pipeline/tool_broker.py`
- `pipeline/tool_audit.py`
- `pipeline/tool_contracts.py`
- `pipeline/tool_registry.py`
- `pipeline/tool_status.py`
- `pipeline/tool_web_policy.py`
- `pipeline/tool_web_response.py`
- `pipeline/tool_web_disclosure.py`
- `pipeline/tool_web_parser.py`
- `pipeline/tool_prerequisites.py`
- `pipeline/sandbox_supervisor.py`
- `pipeline/tool_grants.py`
- `pipeline/tool_execution_router.py`
- `pipeline/tool_web_preflight.py`
- `pipeline/tool_web_connector.py`
- `pipeline/tool_web_native.py`
- `pipeline/research_sources.py`
- `pipeline/research_claims.py`
- `pipeline/research_disclosure.py`
- `pipeline/research_prompt.py`
- `pipeline/research_coordinator.py`
- `pipeline/research_provider.py`
- `pipeline/research_review.py`
- `pipeline/research_selection.py`
- `pipeline/research_evidence.py`
- `pipeline/research_relationships.py`
- `pipeline/research_relationship_disclosure.py`
- `pipeline/research_relationship_prompt.py`
- `pipeline/research_relationship_coordinator.py`
- `pipeline/research_relationship_review.py`
- `pipeline/research_relationship_brief.py`
- `pipeline/research_brief.py`
- `pipeline/research_answer_policy.py`
- `pipeline/research_answer_binding.py`
- `pipeline/factual_research_policy.py`
- `pipeline/research_discovery.py`
- `pipeline/tool_web_search.py`
- `pipeline/tool_web_search_preflight.py`
- `pipeline/tool_web_search_connector.py`
- `pipeline/tool_web_search_runtime.py`
- `pipeline/tool_web_search_brave.py`
- `pipeline/tool_web_search_brave_native.py`
- `pipeline/tool_web_search_tavily.py`
- `pipeline/tool_web_search_tavily_native.py`
- `pipeline/task_profiles.py`
- `pipeline/task_routing.py`
- `pipeline/task_execution.py`
- `pipeline/providers.py`
- `pipeline/api.py`
- `pipeline/document_annotation.py`
- `pipeline/provider_workload_gate.py`
- `pipeline/provider_process_gate.py`

## Configuration (2)

- `config/assistant.json`
- `config/assistant_policy.md`

## Presentation (1)

- `presentation/apartment.html`

## Tests (70)

- `tests/__init__.py`
- `tests/test_discovery_boundary.py`
- `tests/test_chunker.py`
- `tests/test_research_answer_binding.py`
- `tests/test_research_answer_policy.py`
- `tests/test_reset.py`

- `tests/test_adventure_participant_action.py`

- `tests/test_adventure_participant_action_generation.py`

- `tests/test_adventure_participant.py`

- `tests/test_adventure_participant_eval.py`
- `tests/test_experiment_ledger.py`

- `tests/test_api.py`
- `tests/test_adventure_commands.py`
- `tests/test_adventure_turn_provider.py`
- `tests/test_adventure_participant_action_coordinator.py`
- `tests/test_application.py`
- `tests/test_command_help.py`
- `tests/test_command_input.py`
- `tests/test_assistant_context_stats.py`
- `tests/test_resident_snapshot.py`
- `tests/test_sandbox_image.py`
- `tests/test_tool_status.py`
- `tests/test_tool_web_policy.py`
- `tests/test_tool_web_response.py`
- `tests/test_tool_web_disclosure.py`
- `tests/test_tool_web_parser.py`
- `tests/test_tool_broker.py`
- `tests/test_tool_prerequisites.py`
- `tests/test_tool_contracts.py`
- `tests/test_tool_registry.py`
- `tests/test_sandbox_supervisor.py`
- `tests/test_tool_execution_router.py`
- `tests/test_tool_web_preflight.py`
- `tests/test_tool_web_connector.py`
- `tests/test_tool_web_native.py`
- `tests/test_research_sources.py`
- `tests/test_research_claims.py`
- `tests/test_research_disclosure.py`
- `tests/test_research_prompt.py`
- `tests/test_research_coordinator.py`
- `tests/test_research_provider.py`
- `tests/test_research_review.py`
- `tests/test_research_selection.py`
- `tests/test_research_evidence.py`
- `tests/test_research_relationships.py`
- `tests/test_research_relationship_prompt.py`
- `tests/test_research_relationship_coordinator.py`
- `tests/test_research_relationship_review.py`
- `tests/test_research_relationship_brief.py`
- `tests/test_research_brief.py`
- `tests/test_research_answer_policy.py`
- `tests/test_research_answer_binding.py`
- `tests/test_factual_research_policy.py`
- `tests/test_research_discovery.py`
- `tests/test_tool_web_search.py`
- `tests/test_tool_web_search_preflight.py`
- `tests/test_tool_web_search_connector.py`
- `tests/test_tool_web_search_runtime.py`
- `tests/test_tool_web_search_brave.py`
- `tests/test_tool_web_search_brave_native.py`
- `tests/test_tool_web_search_tavily.py`
- `tests/test_tool_web_search_tavily_native.py`
- `tests/test_task_profiles.py`
- `tests/test_task_routing.py`
- `tests/test_task_execution.py`
- `tests/test_provider_workload_gate.py`
- `tests/test_provider_process_gate.py`
- `tests/test_chat_provider.py`
- `tests/test_action_smoke_registration_repair.py`
- `tests/test_document_annotation.py`

## Documentation and policy (7)

- `AGENTS.md`
- `CHANGELOG.md`
- `ROADMAP.md`
- `ROADMAP.v4.md`
- `ROADMAP.v5.md`
- `docs/COMMANDS.md`
- `docs/SANDBOX_BACKENDS.md`

## Root adapter (1)

- `starfur.py`

## Manual inspection script (1)

- `test_chunker.py`

## Offline maintenance helper (1)

- `scripts/restore_action_smoke.py`

S9b exposes only aggregate session-local tool lifecycle counts. B12b documents
the optional distribution boundary. B9a adds only a pure guest-image expectation
and supplied-evidence compatibility contract. S11a/S11b add pure destination,
redirect, and connect-time address decisions without resolution or sockets.
S11c bounds sanitized response metadata and decoded text ingress without HTTP,
decompression, parsing, or trust elevation. S11d permits only no-data or
Core-classified public-data metadata; private and secret disclosure stay denied.
S11e prepares only plain text/Markdown as digest-bound `untrusted_external`
source data; instruction-like prose is not treated as trusted. No request
identity, proposal content, authority record, image access, backend operation,
installation, network request, private disclosure, or execution was exposed or
enabled. Exact one-use prerequisite receipts now close the descriptive-resource
gap at broker admission and are rechecked before launch. `web.fetch` is now
registered only as an inert URL-only, confirmation-required, prerequisite-bound
contract with reference-only results. Exact executor routing now prevents
cross-tool adapter fallback. Supervisor launches carry content-free commitments
to claimed prerequisites, and fake-only web preflight/connector tests prove URL
disclosure binding, pinned peer/TLS/Host selection, response quarantine, and
reference-only results. No native adapter is configured as a network executor,
and no public fetch command exists.
Native resolver, session-only prerequisite/quarantine stores, and pinned TLS
transport adapters now exist behind explicit trusted-local injection. The local
Assistant CLI can reserve an inert `web.fetch`, grant and approve it, prepare
short-lived exact DNS/disclosure evidence, execute it once, and inspect a
bounded quarantined artifact. Shared chat/API, passive views, providers,
prompts, memory, skills, and `sandbox.run` remain disconnected from execution.
The controlled WSL smoke passed: direct public text was quarantined, loopback
was denied before resolution, and shared chat/API refused tool control. Future
research use still requires a separate source-data framing/evidence boundary.
Provider-free S11k/S11l now supply that initial boundary: quarantined public
artifacts can become bounded digest-bound untrusted source packets, and future
provider output can be validated only as packet-local cited claim proposals.
Neither contract calls a provider, verifies truth, composes an answer, or writes
memory/learning/adventure/canon. Bounded source selection, disclosure approval,
corroboration/conflict handling, and final cited-answer policy remain pending.
S11m/S11n add a pure local-only provider disclosure decision and a matching
claim-prompt envelope. Hosted disclosure remains unsupported, internal
artifact/network/authority bindings stay out of the source frame, and no
provider is selected or called. The next coordinator crosses the live-model
boundary and is a focused smoke-test gate.
S11o adds the fake-provider-tested nonpublishing coordinator. It has no runtime
provider registration, retry/fallback, final-answer composition, citation
renderer, or state writes. The next application-wiring slice is the first live-
model boundary and requires the focused smoke test.
S11p wires one exact local-Ollama research task into the trusted local CLI for
explicit review of one quarantined public-text artifact. It returns only strict
packet-local cited claim proposals and cannot enter ordinary chat, publish an
answer, fall back, retry, or write any memory/learning/adventure/canonical
state. Shared chat/API remains denied. The WSL/Ollama smoke passed with cited
Python bytecode-ignore claims and no assistant proposal. S11q adds bounded
session-local `RR-...` review records with list/inspect only; review source text
is not retained and no approval/publication path exists. S11r adds pure bounded
selection of one to eight already-quarantined artifacts; this is not
corroboration or an answer. S11s adds citation-diversity labels only; source
and host counts are always presented as not verification. S11t adds a
provider-free unverified cited brief for an existing review record; it remains
outside normal chat and cannot publish an answer or state. S11u adds a separate
user-invoked unverified answer gate: reviewed cited claims can be displayed, or
the system reports insufficient support. Normal chat stays outside the boundary.
S11v adds the first pure classifier for explicit research, freshness-sensitive,
and high-stakes factual requests. All other normal chat remains explicitly
unclassified, fictional generation remains distinct, and the decision grants no
provider, tool, network, consent, publication, or state authority.
S11w wires only the mandatory-research outcome into normal chat before retrieval
or provider use. It responds honestly that automatic research is not connected,
does not create conversation/proposal state, and preserves fictional generation
unless verification is explicit. Automatic discovery and publication remain
outside this slice and require a focused WSL smoke before further automation.
S11x adds only a content-free eligibility/consent boundary: local discovery may
be eligible, public-web discovery requires exact broker confirmation, and
private/secret query disclosure denies. It retains no query text and creates no
tool, provider, network, source, or answer authority.
S11y adds an inert confirmation-required `web.search` descriptor and query-only
contract with exact search-service/disclosure prerequisites and reference-only
results. No command, executor, search provider, network request, result parser,
or automatic chat path exists.
S11z adds a distinct provider-free quarantined search-result artifact with up to
eight canonical public HTTPS candidates and untrusted titles. It contains no
query text/snippets/evidence/authority, and every URL still requires a separate
exact `web.fetch` path.
S11aa adds only a bounded session-memory exact-reference store for those search
artifacts. It has no list/query/persistence/application/broker path and creates
no search execution authority.
S11af/S11ag add the first concrete hosted-search backend behind that neutral
boundary. A strict Brave reducer and fixed-endpoint native HTTPS transport use
only a transient user-owned environment credential, reduce results to bounded
untrusted URL/title candidates, and remain disabled unless the trusted local
CLI is launched with `--enable-brave-search`. Normal startup performs no DNS or
HTTP, shared chat/API cannot control the tool, and the WSL live-key path remains
smoke-gated.
S11ab adds a pure exact search preflight over broker commitments, a short-lived
configured service record, and public-query disclosure metadata. It performs no
I/O and creates no prerequisite, connector, provider, or answer authority.
S11ah keeps Brave intact and adds Tavily as a second explicitly selected hosted
search backend. The CLI flags are mutually exclusive, credentials stay in
provider-specific process environment variables, and neither provider is a
silent fallback for the other. Tavily returns only reduced untrusted URL/title
candidates; its answer, snippets, scores, raw content, usage, and request
metadata are discarded. Both live WSL credential paths remain smoke-gated.
The explicit local research route now requires a provider-native structured-
output capability. Core supplies one exact packet-bound JSON Schema through
Ollama's top-level `format` field, while the existing strict parser remains the
final validation and citation gate. Text-only adapters fail closed; normal chat
is unchanged; no fallback, retry, provider payload retention, answer
publication, or state write was added. The WSL/Ollama research smoke is the
remaining gate.
Structured review provenance now carries only a question digest/byte count and
public source URL/fetch-time labels. The optional exact-question answer form
fails closed before a review can be reused for a different question; it adds no
automatic research, model call, network effect, or state write.
`tool search <public query>` is now the trusted-local fast path over the same
existing one-use hosted-search lifecycle. Its focused Tavily WSL smoke passed:
it returns only the usual quarantined untrusted discovery links and never
automatically fetches them or treats them as facts.
`tool search fetch <TF-search-id> <rank>` now fast-forwards one explicitly
selected quarantined discovery link through a fresh ordinary `web.fetch`
lifecycle, then still stops at a separately inspected artifact. Its focused WSL
smoke passed with an explicit `example.com` rank.
`tool research selected <TF-search-id> <rank>: <question>` now explicitly
chains one selected discovery rank through a fresh fetch and the existing local
nonpublishing cited-claim review. Its combined WSL/Ollama smoke passed with the
explicit `example.com` source, one cited review, and no memory proposal.
The local claim-relationship route has now passed its live smoke: a reviewed IANA source
produced two session-local cited claims, the first malformed relationship output
failed safely, and a later exact retry created one inspectable noncanonical
`RX-...` proposal. Its deterministic brief, empty proposal list, and empty
`ollama ps` result confirmed that no answer/verification/state was published and
the background model release request completed on the installed provider.
Ollama structured-output calls now consume a streaming transport internally so
Ctrl+C can close the response while Core still receives only one complete
strictly validated result. Explicit interruption bypasses ordinary candidate
failure wrapping and cannot publish partial participant/adventure/research
review state. Default participant actions are bounded to 4096 context and 256
output tokens; native WSL/Ollama interruption and foreground recovery remain
the live smoke gate. A separate provider-free resource-policy foundation now
models interactive/balanced/background envelopes and defers when exact backend
controls are unavailable; it is not wired to routing, monitoring, or execution.
The stock normal-chat output ceiling is now 1024 tokens after the initial
512-token live trial truncated visible Qwen output. A later 1024-token trial
also cut off; reasoning's contribution was not measured. Proposal and
structured adventure ceilings remain smaller.
Task profiles now carry descriptive workload labels for interactive chat and
participant work, balanced adventure generation, and background research;
route previews expose only the bounded label and no admission is implied.
Completed route traces and resident diagnostics now preserve that same bounded
label only; it is not evidence of enforcement or provider health.
Task profiles can additionally carry an opt-in bounded `model_keep_alive_seconds`
request. Routed Ollama calls forward it only when configured; absence preserves
the provider default. This is neither proof of model unload nor resource admission.
The stock participant-action and background-research tasks request `keep_alive=0`
after completion; normal chat, annotation, and ordinary adventure generation retain
their provider default. The WSL/Ollama participant-action smoke completed one
candidate and then showed no loaded model through `ollama ps`.
The trusted local manual `focus mode on/off/status` gate is session-local and
defers balanced/background tasks before provider use while keeping interactive
work eligible. It does not inspect foreground apps, alter priority, unload a
model, or persist a preference.
Document annotation is classified as background so Focus Mode defers a new
intake before a provider call; the application/API route honors that same
session decision before it constructs an annotator. It does not request
unload/reload per chunk.
The bounded resident snapshot and apartment may show only that selected
session's manual Focus Mode is on or off. This presentation marker is
session-ephemeral and has no task, process/window, budget, or enforcement
detail; it cannot alter the mode or trigger a provider call.
`provider-resource-eval` is the checked-in deterministic admission-policy
fixture: four closed provider-free cases can be recorded to the experiment
ledger as statuses/reasons only. It measures no real provider, host, routing,
reservation, or enforced resource limit.
`ProviderWorkloadGate` defaults to process-local exact-provider admission and
may explicitly compose `ProviderProcessGate` for one same-checkout, same-OS-lock-
domain capacity-one lease. Routed streams retain the lease through exhaustion
or close. Assistant/API startup exposes an opt-in flag; the WSL contention and
recovery smoke passed, while the default remains application-local pending
native-Windows validation and an explicit rollout decision. No queue, host monitoring,
throttling, process termination, provider-stop proof, Windows/WSL lock
interoperability, preemption, or model lifecycle claim exists.
