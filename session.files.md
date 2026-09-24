# Pending copy manifest

## Pipeline (47)

- `pipeline/assistant.py`
- `pipeline/application.py`
- `pipeline/command_help.py`
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

## Configuration (2)

- `config/assistant.json`
- `config/assistant_policy.md`

## Presentation (1)

- `presentation/apartment.html`

## Tests (45)

- `tests/test_api.py`
- `tests/test_application.py`
- `tests/test_command_help.py`
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
- `tests/test_chat_provider.py`

## Documentation and policy (5)

- `AGENTS.md`
- `ROADMAP.md`
- `ROADMAP.v5.md`
- `docs/COMMANDS.md`
- `docs/SANDBOX_BACKENDS.md`

## Root adapter (1)

- `starfur.py`

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
lifecycle, then still stops at a separately inspected artifact. Its focused
WSL smoke remains required.
