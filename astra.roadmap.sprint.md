# Modular tool security sprint plan

Date: 2026-09-08. Revision: authority and implementation-boundary refinement. Status: proposed implementation plan; no execution authority is enabled by this document.

The original pass inspected the current source, relevant tests, AGENTS.md, ROADMAP.md, ROADMAP.v4.md, ROADMAP.v5.md, docs/COMMANDS.md, benchmark/ledger code, presentation shell, and session.files.md. This refinement preserves that static evidence and clarifies the proposed interfaces and gates; it is not a penetration test or certification. No tests, providers, sandbox jobs, runtime migrations, or dependency installation were run for this document. The working tree was already extensively modified and untracked. Only this existing plan is authorized to change during refinement; even session.files.md is intentionally untouched.

## 1. Scope and threat model

Build an extensible Core tool broker whose adapters have deliberately limited authority. Preserve the existing application, provider, adventure, and memory boundaries. The first deliverable is a validated request contract; executable learning exercises require later OS-isolation gates.

Protect host files, credentials, network destinations, canonical memory, adventure logs, persona continuity, audit records, and availability. Treat model responses, websites, retrieved text, downloaded files, archives, Workshop content, generated code, and tool output as untrusted. A provider can propose an operation, but cannot supply its permission, actor identity, execution policy, or confirmation.

Assume Core, explicitly installed adapter code, the approval client, and the chosen isolation supervisor are trusted components. Arbitrary third-party Python imported into the Core process would bypass the broker; a Python protocol or registry does not isolate malicious code. Malicious local administrators and kernel/hypervisor compromise are outside the initial guarantee. A sandbox reduces exposure; it cannot guarantee that every exploit is contained.

Destroying a workspace cannot reverse an uploaded secret, a remote mutation, or an approved host-file overwrite. Apply controls at input, authorization, execution, output, and export. Read-only access also needs authorization: reading private content and sending it to a hosted model is a disclosure even if no local file changes.

### Existing commands and new tools

Existing explicit memory, proposal, persona, roleplay, and adventure commands remain Core-owned paths through `AssistantSession` and `AssistantApplication`, with their current validation, namespace, confirmation, and transaction rules. Installing the broker does not automatically wrap or secure those paths. Preserve their existing behavior while adding the new tool boundary.

An existing action needs a separate broker adapter before a model, retrieved document, tool result, or scheduled agent can select or parameterize it for execution. That adapter accepts a closed typed operation, derives the target namespace from trusted context, obtains the operation-specific grant/approval, and calls the existing Core service. Never send generated command strings through `AssistantSession.respond()` to perform effects. Reuse the underlying transaction rather than writing directly to its database or event log. Existing shared chat APIs are not upgraded into trusted approval channels by this reuse.

Every new model-reachable effect must pass through the broker. This includes exposing existing read operations: access to private memory or files and subsequent disclosure require policy even when no mutation occurs. Persona/adventure identifiers locate context; neither an identifier nor an installed package grants authority. Fictional state must not automatically become real-world memory.

### Four distinct security decisions

| Concept | Meaning and boundary |
| --- | --- |
| Authentication | Establish which enrolled client/local operator is making the request. Core creates an internal principal from verified transport or local-control context; merely generating an ID authenticates nobody. |
| Authorization | Decide whether that principal may perform this exact operation on these resources under the current policy. Scope, expiry, revocation, and use budgets are checked independently of model availability. |
| Confirmation | Capture the authorized user's explicit acceptance of one immutable request and its effects. Authentication or an existing scope grant alone does not confirm a mutation. |
| Provenance | Record where supplied data and outcomes originated. Source identity, model confidence, and an audit record do not authorize execution or prove an assertion true. |

Application validation enforces these contracts inside trusted Core. OS isolation constrains what executed code can actually access outside them. Both are needed before hostile code runs. A trusted in-process adapter must obey the contract, but the contract cannot contain an adapter that deliberately bypasses it.

## 2. Repository evidence and gaps

Labels: **Observed** describes inspected implementation; **Inference** describes consequences; **Recommendation** is proposed work. Tests cited here were read, not executed during this pass.

| Reference | Observed implementation | Inference and recommended gate |
| --- | --- | --- |
| `pipeline/tool_registry.py`: `ToolDescriptor`, `ToolRegistry`, `build_core_tool_registry`; `tests/test_tool_registry.py` | Immutable ordered descriptions; `sandbox.run` is mutating and confirmation-required. No executor is registered. Registry output has a schema version, but individual tool input/result contracts do not. Title, identifiers, and registry count lack explicit size ceilings. | Useful F1 primitive, not a complete tool system. Bound metadata and add closed versioned operation schemas before accepting external proposals. |
| `pipeline/tool_permissions.py`: `PermissionGrant`, `evaluate_tool_permission`; `tests/test_tool_permissions.py` | Exact scope/access checks and a strict boolean confirmation. No target, owner, expiry, revocation, grant storage, or confirmation provenance. | A caller-supplied `confirmed=True` is not evidence of user approval. Keep this pure helper; a trusted controller must construct its inputs from stored request-bound approval. |
| `pipeline/sandbox.py`: `_relative_path`, `SandboxService.run`, `SandboxPolicy`; `SandboxTests.test_default_policy_denies_without_materializing_or_calling_backend` | Default denies without creating files. An explicitly enabled service writes a temporary workspace and calls an injected backend. Policy contains requested timeout and character/file limits. | No implemented process, RAM, CPU, output-stream, or network isolation. Do not describe existing tests as escape resistance. Backend enforcement must be proven separately. |
| `pipeline/sandbox.py`: `_relative_path` and workspace materialization | Paths use `PurePosixPath`, then host `Path.joinpath`. Checks cover POSIX absolute paths, parent traversal, and backslashes. | Windows drive/drive-relative names, alternate streams, reserved names, case aliases, and reparse behavior need explicit treatment before materialization is reachable. This is a static risk finding, not a demonstrated host overwrite. |
| `pipeline/sandbox.py`: `SandboxService.run`, `_report`, `SandboxReport.public_dict`; `SandboxTests.test_backend_errors_and_output_are_bounded_in_a_report` | Backend exception text enters a detail string; stdout/stderr/detail are public report fields. Materialization and temporary-directory cleanup lie outside the backend exception handler. Truncation appends a marker beyond the requested content cap. | Error strings may contain paths/secrets; large exception text can itself fail result construction. Define total serialized bounds, sanitized error codes, separate private artifacts, and cleanup failure states before exposing reports. |
| `pipeline/application.py`: `normalize_conversation_id`, `_SessionSlot`, `_locked_session_for`, `_evict_sessions_if_needed`; application concurrency/LRU tests | Opaque conversation IDs select ephemeral sessions; locks serialize a session; active requests pin its slot. IDs explicitly are not authentication. | Bind tool grants to a trusted principal plus a server-created session instance, never just a supplied conversation string. An async job needs its own lifetime and cancellation ownership. |
| `pipeline/api.py`: `OpenAICompatibleAPI.authenticate`, `StarFurRequestHandler.do_POST`, `_conversation_id_from_request`; API auth/isolation tests | API-key authentication is optional; a configured bearer is shared. Document prepare/annotate bodies have a transport size limit; the shown general POST path lacks an equivalent global ceiling. | Existing API chat capability is too broad to serve as proof of human tool approval. Gate new tool controls on authenticated, explicitly enrolled local control clients; bound ingress before JSON parsing and isolate approval from chat/connectors. |
| `pipeline/providers.py`: `ChatCompletionProvider`, `ChatCompletion`; `pipeline/provider_registry.py`; `pipeline/task_execution.py`: `RoutedChatExecutor` | Completion-only injection, text normalization, and explicit route execution exist. No provider tool-execution bridge exists. Provider registrations store a copied dictionary inside a frozen dataclass. | Keep language routing separate from tool authorization. Snapshot/freeze execution registrations; dataclass freezing alone does not freeze nested dictionaries. Installed in-process adapters remain trusted code. |
| `pipeline/persona_development.py`: `LearningRecord`, `PersonaDevelopmentState.apply_verified_learning`; persona development tests | A caller-supplied verified-success record with evidence can reinforce a persona-local skill. Evidence is bounded text, not independently authenticated execution evidence. | Introduce a Core verifier before connecting tools to learning. A generated “tests passed” string cannot certify itself or create shared personal memory. |
| `pipeline/experiment_ledger.py`: `append_benchmark_result`, `load_benchmark_results`; `tests/test_experiment_ledger.py` | Explicit JSONL append with allowlisted benchmark fields and fsync. Load checks schema version; no execution transaction, principal ownership, or cross-process audit lock is provided here. | Reuse aggregate evaluation conventions; implement a separate operational tool journal. This benchmark ledger is not a security audit/recovery store. |
| `pipeline/resident_snapshot.py`, `pipeline/application.py`, `presentation/apartment.html`; resident/API snapshot tests | Bounded resident read model and passive route summaries; shell uses textContent for displayed values and browser-memory bearer input. | Add aggregate tool activity later. Keep approval details/results on separately authorized read models; shell polling cannot grant or execute. |
| `docs/COMMANDS.md`, `pipeline/command_help.py`; repository references to `SandboxService`, `build_core_tool_registry`, `evaluate_tool_permission` | Routing and explicit memory/adventure controls exist; the tool primitives are not wired into application dispatch. | No user tool smoke test is needed for pure contract work. Reserve a deterministic tool namespace before adding a live entry point. |

## 3. Minimum interfaces and invariants

Proposed filenames below are design targets, not claims that files already exist. Keep one module per meaningful boundary; combine tightly related value objects when that is clearer. Avoid a generic plugin framework, arbitrary schema interpreter, or dependency-loading system.

| Boundary | Owns / minimum proposed interface | Must never own |
| --- | --- | --- |
| Descriptor/catalog | Existing `ToolDescriptor` supplies descriptions/effects. Immutable `ToolContract` binds `(tool_id, tool_version)` to Core-written argument/result validators, declared resource requirements, limits, and retry class. `lookup()` is deterministic. | Grant issuance, executable discovery/import, provider calls, or model/package-defined validators. Adding a tool never changes the authorization algorithm. |
| Proposal contract | `ToolProposal(schema_version, tool_id, tool_version, arguments)` and strict decode/validate/serialize functions; bounded immutable data only. | Ownership, scope, confirmation, effective policy, credential values, module paths, or executor selection supplied by a model. A tool-specific data field may contain source text but cannot select a host executable. |
| Invocation identity | Core-created `ToolInvocation` binds a request ID to an authenticated internal principal, server-created session-instance ID, persona, optional registered adventure, context generation, contract revision, and argument fingerprint. | Authentication by conversation string or acceptance of provider-supplied actor/namespace/approval claims. S1 needs only inert identity types for correlation; identity issuance begins later. |
| Grant controller | `ToolGrantStore` holds exact operation/resource grants with owner/context, expiry, remaining uses, policy/contract revision, and revocation generation; create/revoke/inspect require trusted controller inputs. | Inference of wildcard or parent-scope permission, persistent state in the first version, model/package authorization, or approval of mutations merely because a scope matches. |
| Approval controller | Prepare an effect preview; store `PendingToolApproval`; confirm/consume one nonce bound to request, resources, destination, policy, owner, and expiry. | Parsing approval from model prose, reusing approval for changed arguments, or treating connector bearer possession as human consent. |
| Broker lifecycle | `prepare`, `approve`, `execute`, `cancel`, `inspect`; orchestrates controller decisions, atomic execution claims, executor lookup, and outcome validation. Rechecks authorization immediately before dispatch. | Model interpretation, direct arbitrary host I/O, credential storage, namespace inference, or implicit effect retries. Locks cover transitions, not long-running model/job calls. |
| Executor adapter | One Core-installed adapter accepts the validated operation and effective policy, starts/cancels its bounded job, and reports outcome. Required enforcement capability must be checked before work. | Grant/approval creation, policy relaxation, dynamic executable plugin loading, or generic application/session/database access. An adapter for an existing Core action receives only its narrow authorized service interface. |
| Result contract | Versioned `ToolResult` validates request correlation, outcome, bounded counters, closed error category, and opaque artifact references. Private artifact access is separately owner-checked and expires. | Execution authority, model self-certified success, raw error disclosure, automatic prompt injection, or automatic memory/skill writes. Artifact references are not bearer permissions. |
| Audit/run journal | Append bounded intent/outcome events; recover execution status under locking and a defined durability policy. Keep result content in a separately controlled artifact store. | Raw arguments, paths, secrets, source text, stdout, or provider payloads in audit metadata; restoring grants from history; automatic job replay. The experiment ledger remains aggregate evaluation only. |
| Presentation read models | Core assembles allowlisted counts/status for resident snapshots and separately authorized request previews/results. Clients render and submit explicit control requests. | Inferring success from prose, granting on poll/render, leaking detailed arguments through the apartment summary, or serving arbitrary artifact paths. |

The extension unit is one Core-installed contract plus one registered executor adapter and its regression/conformance tests. Registration is explicit at trusted application construction. New tools reuse broker, grants, audit, and public status contracts; they cannot install parallel permission engines. Third-party executable workers require the separate confinement/installation gate in S14. Do not implement that loader in the foundation.

Recommended initial ceilings: proposal transport 64 KiB; schema depth 8; catalog 64 tools; ID 80 characters; title 120; summary 600; pending requests 16 per session and 64 globally; audit event 4 KiB; diagnostic list 8 records. Treat these as initial policy choices, freeze them in tests, and revise explicitly. Sandbox input should use a separate bounded typed upload, with existing limits supplemented by UTF-8 byte ceilings (initially 1 MiB total); do not smuggle large files into generic tool JSON.

Use standard JSON plus handwritten validators for the first tool. Reject unknown versions, duplicate JSON keys, nonfinite numbers, boolean-as-integer values, excess nesting, trailing content, and oversized bodies. Deep-copy/freeze validated nested content. Public display labels require length/control-character limits. Internal fingerprints bind exact requests; never publish content hashes of private low-entropy data as if they were anonymous.

A descriptor must classify more than local mutation: private reads, network egress, credential use, and external writes are distinct effects. Execution of generated code remains confirmation-required even if its intended output is temporary. Effective policy is the intersection of Core limits, grants, user approval, and backend capability; unsupported enforcement means denial.

### Grant and provider rules

Initial grants are session-ephemeral. Bind each to the authenticated internal principal, server-created session instance, exact tool version/operation, typed resource identity, policy revision, expiry, maximum uses, and revocation generation. Persona/adventure context further restricts use; it never creates a grant. Resource resolution is Core-owned, including checking that a supplied opaque resource reference belongs to that principal. Recreated sessions, changed policy/tool versions, and revoked resources invalidate approval eligibility. A model change cannot broaden these bindings.

Only trusted controller code may turn stored confirmation into the existing evaluator's `confirmed=True`. In-memory locks/atomic claims must bind use-count consumption to one dispatch; do not count a duplicate status query as another execution. Persistent grants come after explicit restart, revocation, migration, and resource-revalidation tests. There is no implicit “always allow,” and a persistent grant alone still cannot replace required per-request confirmation.

Providers may supply a bounded proposal through a dedicated task adapter; they cannot choose the executor, principal, session, namespace, grants, scopes, or effective policy. Provider fallback may regenerate an unexecuted proposal within a finite budget. Any changed proposal needs fresh validation/approval; fallback must never replay an effect, evade a denial, or widen permission. Zero-provider operation retains deterministic inspection, status, denial, revocation, cancellation, and explicitly authorized manual operations; missing language generation cannot disable these controls.

### Execution and recovery

Use a closed lifecycle: proposed -> awaiting approval -> approved -> queued -> running -> completed/failed/cancelled/timed_out/outcome_unknown. Denied, expired, and stale requests are terminal without execution. Distinguish cancellation requested from confirmed process termination and cleanup completion.

Same request ID plus identical bound content returns its existing status/result; a conflicting reuse fails. Claim one execution atomically. Retries after uncertain external effects require reconciliation; do not promise exactly-once behavior across arbitrary remote systems. Before real effects, durably record intent. If audit storage is unavailable/full, deny new execution. If an effect succeeds but final journaling fails, retain an explicit uncertain/reconciliation state; never report a clean retryable failure.

Revoke queued jobs immediately; signal cancellation to running isolated work. Revocation cannot undo completed writes. On persona/adventure switches or session eviction, invalidate pending approvals and queued work for the old context; running work retains its original owner, is cancelled when supported, and cannot deliver results into the new context. App restart loses session grants and approvals, never resurrects them from run logs, and reconciles orphan jobs through a trusted supervisor. Bound both global and per-principal concurrency so many conversation keys cannot evade resource limits.

### Isolation, filesystem, and network policy

Prefer a disposable VM or equivalent separately verified isolation boundary for hostile generated code on the Windows/WSL prototype. A normal WSL process has host integrations and is not sufficient isolation. A shared-kernel container has a different threat model and requires an explicit reviewed acceptance decision. Backend selection and installed runtime details must be validated against current official platform documentation during implementation; this local-only review does not certify a particular product/configuration.

Do not expose host bind mounts, home directories, `/mnt/c`, daemon sockets, SSH agents, API tokens, inherited environment, or host network to the worker. Use immutable preinstalled toolchains and no job-time dependency downloads initially. Enforce CPU, memory, process count, writable disk, file count, output bytes, wall time, and total concurrent-job limits outside worker-controlled code. Terminate the entire job/process tree and confirm teardown. Disable backend auto-start until an operator explicitly configures it.

Validate file paths lexically before normalization, then enforce actual containment using platform-safe filesystem operations. Test Windows drive-relative and absolute paths, UNC/device paths, alternate streams, reserved names, trailing dots/spaces, case collisions, mixed separators, NULs, parent segments, and file/directory prefix collisions. Avoid check-then-open races: use handle-relative/no-follow operations or an isolated copy-in/export broker with equivalent enforcement. Deny symlinks, junctions/reparse points, device files, sockets, and hardlink escape opportunities. A `resolve()` check by itself is insufficient when paths can change before use.

For explicitly granted folders, first copy bounded selected input into isolation. Export reviewed changes through a separate broker operation bound to exact destination identities and expected original content/version. Start with new-file creation, then guarded replacement; defer recursive delete/move. Keep Core code, config, credentials, `.git`, runtime databases, audit/grant stores, and adventure logs outside generic writable roots even if a broad parent was selected. Specialized Core APIs retain their own policies.

Web fetching gets its own restricted service. Begin with explicit HTTPS destinations, no cookies/accounts, redirects disabled, and bounded time/bytes/decompression. When redirects are later allowed, revalidate every hop. Enforce DNS/IP destination checks at connection time against loopback, private/link-local/metadata addresses and IPv4/IPv6 variants; prevent rebinding and implicit environment proxies. Treat returned HTML/scripts as inert data, parse dangerous formats in isolation, and never let a fetched page grant another request. A generic public-web grant must not allow access to local Ollama/StarFur services.

File-read permission does not imply permission to send its contents to a web endpoint or hosted LLM. Carry source/resource provenance through result handling; initially forbid automatic chaining of private-file results to external destinations. Any permitted disclosure requires an explicit destination-bound review. Secrets stay in a separate credential broker, supplied only to an approved narrow adapter for a specified origin/account; never put them in prompts, subprocess environments, logs, or worker files by default.

Archive import remains quarantined and bounded by entry count, path lengths, total expanded bytes, compression ratio, and nesting depth. Reject links, executables, special files, encrypted/unsupported forms, duplicate/case-colliding members, traversal, and implicit downloads. Exported artifacts are untrusted files too; inspect without following links or rendering active content. Workshop manifests remain declarative, with installation separate from per-run authority.

## 4. Ordered implementation slices

Every slice must preserve existing behavior, add meaningful adversarial regressions, and update docs/session.files.md only during its authorized implementation. New modules listed below are proposals. A smoke gate requires copying the full manifest to WSL and restarting the relevant service; pure contract slices can be grouped without manual testing. Skipped platform tests are unresolved gates, not passes.

The S1–S14 headings remain stable planning milestones. The sub-slices below separate acceptance gates within broader milestones; implement one sub-slice at a time. Suggested filenames and numeric ceilings are bounded starting choices, not a mandate to build speculative infrastructure. **Sol's initial assignment authorizes S1 only.** Grouping guidance for later work does not authorize automatically proceeding to S2.

### S1 — Bound and version the inert tool contract

- **Objective:** Extend the existing catalog with a frozen `ToolContract` and strict proposal/result envelopes for the sole initial tool, `sandbox.run`. Keep `ToolDescriptor` constructors compatible. Its v1 arguments describe bounded exercise data; validation never creates files. Correlation/identity types, if required, stay inert and contain no identity issuer, approval controller, or runtime store.
- **Files/interfaces:** `pipeline/tool_registry.py`; new `pipeline/tool_contracts.py`; `tests/test_tool_registry.py`; new `tests/test_tool_contracts.py`. Reuse existing exact permission evaluator without expanding it into a controller.
- **Prerequisites:** Current registry/permission/sandbox tests provide the baseline; no platform isolation choice needed.
- **Tests:** Unknown tool/version/fields; forged approval/identity/policy; duplicate keys; malformed JSON; size/depth/UTF-8 bounds; nested mutation after validation; malformed results; registry duplicate and limit checks; denied metadata remains inert. Spy on filesystem/process/provider boundaries to prove zero calls.
- **Security invariant:** A valid request is merely a proposal. Contract validation grants no authority and imports no executor.
- **Smoke:** None; focused provider-free tests suffice.
- **Defer:** Grants, approval UI, application dispatch, executor invocation, temporary materialization, audit persistence, web/filesystem tools.

### S2 — Session-owned grants and bound approvals

- **Objective:** Add a provider-free in-memory controller over the existing evaluator, with authenticated internal-principal/session-instance ownership, exact operation/resource/tool-version and policy-revision bindings, finite expiry/use budgets, revocation generation, and single-use approval binding. Inject trusted identity/clock inputs; this controller does not authenticate HTTP clients itself.
- **Files/interfaces:** New `pipeline/tool_grants.py`, `pipeline/tool_approval.py`; `pipeline/tool_permissions.py` only as needed for compatible integration; dedicated tests using injected clock/ID sources.
- **Prerequisites:** S1 contracts; add Core-owned invocation issuance and immutable context binding as part of S2 before granting/approving. Do not move runtime identity issuance into S1.
- **Tests:** Cross-session/persona/adventure attempts; same conversation string after recreation; expiry; revocation; modified target/arguments/policy; confirmation replay; invalid booleans; denied scope neighbor; grant exhaustion. Concurrent approval consumption must have exactly one winner.
- **Security invariant:** Models/packages never create grants or approval evidence. Storage remains memory-only and bounded; a local caller's ordinary boolean cannot authorize an external request.
- **Smoke:** None while programmatic and unexposed.
- **Defer:** Persistent grants, “always allow,” UI, process execution, broad scope inheritance.

### S3 — Broker lifecycle with disabled execution and bounded audit events

- **Objective:** Join contracts, grants, and approvals through an explicit state machine with a disabled executor. Introduce typed in-memory audit records and request deduplication.
- **Files/interfaces:** New `pipeline/tool_broker.py`, `pipeline/tool_audit.py`; executor protocol local to broker initially; `tests/test_tool_broker.py`, `tests/test_tool_audit.py`.
- **Prerequisites:** S1–S2.
- **Tests:** Denial without side effects; duplicate/concurrent dispatch; conflicting request-ID reuse; stale context; cancelled queue; invalid backend result; unavailable backend; injected secrets in errors; bounded event/report output. Disabled provider must not prevent deterministic broker inspection.
- **Security invariant:** No call to `SandboxService.run` yet. Approval and execution readiness remain separate. Audit outcomes cannot claim work occurred when disabled.
- **Smoke:** None until application integration.
- **Defer:** Durable logs, real execution, automatic retries, provider-generated requests.

### S4 — Trusted control entry point and deterministic status

- **Objective:** Expose inert request preview, status, deny/revoke/cancel, and explicit approval through `AssistantApplication`. Begin with trusted local CLI control; keep actual execution disabled. Define a server-created principal/control-client context separate from conversation selection before enabling any HTTP approval endpoint.
- **Files/interfaces:** `pipeline/application.py`, `pipeline/assistant.py`, `pipeline/command_help.py`, `pipeline/capabilities.py`, `docs/COMMANDS.md`; later narrow `pipeline/api.py` control adapter; application/API tests.
- **Prerequisites:** S3; explicit API trust policy. Recommended initial boundary: CLI can approve; OpenWebUI/shared chat bearer can submit proposals but cannot grant/approve. A future separately enrolled local control client may approve.
- **Tests:** Reserved malformed tool commands never generate; quoted/document/model instructions never confirm; generic chat bearer cannot approve; no-key API cannot enable tools; existing-session lookup; provider-disabled mode; role/persona change; LRU cleanup. Before tool HTTP exposure add body/read-time limits, content-type checks, host/origin policy, and bounded request concurrency.
- **Security invariant:** No authentication from conversation IDs, persona names, or natural-language claims. Tool authority must be opt-in and unavailable on an unauthenticated/LAN-facing legacy setup.
- **Smoke:** Required: CLI preview/deny/status with provider disabled, plus API denial tests for the chosen control channel. Verify existing chat/apartment still work.
- **Defer:** Public approval on the shared chat endpoint, remote control, real jobs, richer dashboard.

### S5 — Harden sandbox materialization and result handling

**Implementation status:** Provider-free hardening is implemented locally;
native Windows/WSL smoke evidence remains outstanding.

- **Objective:** Fix the inspected path/result issues and establish safe text-only copy-in rules before any executor can use temporary workspaces.
- **Files/interfaces:** `pipeline/sandbox.py`; small platform path helper if needed; `tests/test_sandbox.py` plus platform-specific tests.
- **Prerequisites:** S1; S4 need not block pure hardening, but no new live entry point may precede S4.
- **Tests:** All path cases from section 3; UTF-8 byte bounds; reserved names and collisions; write/cleanup exceptions; invalid/huge backend output; no exception secrets; cleanup on failures; no files when backend is absent. Real temporary test directories only.
- **Security invariant:** The default backend denies before materialization. Catching errors is not confinement. Separate detailed authorized artifacts from safe status/error metadata.
- **Smoke:** Required on native Windows and WSL for filesystem behavior; no hostile code execution.
- **Defer:** OS execution, exports, archives, network. Unsupported safe filesystem operations fail closed.

### S6 — Durable execution journal and recovery contract

- **Objective:** Persist bounded intent/outcome records with locking, validation, crash recovery, and bounded retention before enabling real effects. Keep security audit separate from the experiment ledger.
- **Files/interfaces:** Extend `pipeline/tool_audit.py`; new `pipeline/tool_runs.py`; consult `pipeline/adventure_events.py` locking/recovery patterns without storing tool events in adventure logs; recovery tests with injected failures.
- **Prerequisites:** S3; define storage root owned only by Core.
- **Tests:** Truncated/corrupt journal, concurrent writers, disk full, intent/outcome crash gaps, uncertain completion, duplicate retry, expired owner session, startup reconciliation, bounded retention. Do not replay jobs on restart.
- **Security invariant:** Durable records cannot restore permission. Append-only is an application policy, not tamper-proofness against the host owner; a hash chain alone would not fix that.
- **Smoke:** Required with disposable run storage: interrupted test job, restart, unknown/reconciled outcome, no repeat execution.
- **Defer:** Remote audit service, full payload logging, production data repair.

### S7 — Specify and validate one OS isolation backend

- **Objective:** Select one supported backend and freeze an enforcement profile after reviewing current official platform documentation. Prefer VM isolation for hostile generated code; specify exactly which Windows/WSL integrations are absent. Add capability checks and an external job supervisor with cancellation.
- **Files/interfaces:** New `pipeline/sandbox_backend.py` and one platform adapter, or a separate minimal worker service; `pipeline/sandbox.py` protocol adaptation; dedicated backend docs and integration tests.
- **Prerequisites:** S5–S6; operator choice/installation of isolation runtime. No implicit installation or privilege escalation.
- **Tests:** Disposable canaries outside the guest; denied host roots, network, inherited credentials, daemon sockets; child-process termination; RAM/CPU/process/disk/output ceilings; timeout; worker crash; supervisor restart; cleanup failure. Fake backends validate wiring only.
- **Security invariant:** All required limits must actually be enforced. Missing enforcement denies the job. User code cannot alter the supervisor or read Core storage.
- **Smoke:** Mandatory on the actual selected runtime before claiming isolation. Do not run escape tests on personal data; use disposable environments and harmless probes.
- **Defer:** Other backend platforms, shared-kernel acceptance without review, arbitrary host shell, guest network, GPU passthrough, live package downloads.

### S8 — First brokered learning exercise

- **Objective:** Connect `sandbox.run` through the broker to the validated backend. Start with one Core-defined exercise kind and fixed toolchain/entry point; bounded supplied source may run inside isolation, with no user-supplied shell command or host path.
- **Files/interfaces:** `pipeline/tool_broker.py`, `pipeline/sandbox.py`, new `pipeline/tool_sandbox.py`; trusted application control; exercise fixtures and end-to-end tests.
- **Prerequisites:** S4–S7 passed; real execution explicitly enabled by the operator.
- **Tests:** Approve once; execute once; deny/revoke; timeout/cancel; broken backend; stale context; duplicate request; provider disabled; no remaining processes/files after cleanup; returned artifacts never auto-open or alter memory.
- **Security invariant:** No grant alone starts work. The broker issues the effective policy; no automatic production export or learning reinforcement.
- **Smoke:** Mandatory end-to-end, using a harmless fixed exercise in disposable storage.
- **Defer:** Free-form commands, autonomous loops, arbitrary dependencies, filesystem/web chaining, automatic skill updates.

### S9 — Provider proposals and presentation read models

- **Objective:** Add a dedicated bounded provider task producing strict tool proposals. Add sanitized tool-status counts to resident snapshots and a separately authorized review view. Preserve text-only ordinary chat and never execute tool-looking prose.
- **Files/interfaces:** New `pipeline/tool_proposals.py`; existing providers/task profiles/execution seams; `pipeline/application.py`, `pipeline/context.py`, `pipeline/resident_snapshot.py`, `presentation/apartment.html`; provider-fake and UI/API tests.
- **Prerequisites:** S4 and S8; permitted-tool selection must be derived from Core state before prompting.
- **Tests:** Prompt-injected documents/results, forged grants, unknown operations, truncation/empty/malformed output, provider unavailable, bounded model repair attempts, result disclosure policy, escaped terminal/HTML output, no side effects during rendering/polling.
- **Security invariant:** Provider fallback can regenerate a proposal, never replay an effect or broaden authority. A model's instruction to confirm is data. Detailed arguments/artifacts stay out of passive snapshots.
- **Smoke:** Mandatory one-model proposal -> review -> explicit approval -> harmless run, plus zero-provider manual path. No real user data required.
- **Defer:** Model self-approval, native arbitrary tool-call passthrough, chains that auto-consume outputs, approval inside an untrusted embedded page.

### S10 — Explicit filesystem capabilities and controlled export

- **Objective:** Add exact file/root read grants and bounded copy-in. Then, as a separately reviewed sub-slice, add new-file export and expected-version guarded replacements with previews/backups and revocation.
- **Files/interfaces:** New `pipeline/tool_filesystem.py`, `pipeline/file_grants.py`, platform-safe resource resolver; broker/controller extensions and filesystem tests.
- **Prerequisites:** S5–S8; trusted local file selection; destination identity and race-safe operations.
- **Tests:** Root boundary and sibling-prefix tricks; symlink/junction/hardlink races; Windows path cases; cross-mount access; protected Core paths; changed destination since approval; grant revocation; duplicate export after disconnect; conflicts/backups; private input cannot reach hosted provider without disclosure permission.
- **Security invariant:** Grant only the selected resource/operation. No arbitrary worker access to the host tree. External changes can have irreversible consequences even if the sandbox is destroyed.
- **Smoke:** Mandatory Windows/WSL test-owned directories with before/after sentinels outside the grant; read and write gates separately.
- **Defer:** Recursive deletion, arbitrary moves, filesystem-wide indexing, secret stores, unrestricted mounts.

### S11 — Web retrieval and quarantined parsers

- **Objective:** Add a restricted fetch adapter and sandboxed parsing. Start with explicit destinations and inert text; preserve source provenance and finite request budgets.
- **Files/interfaces:** New `pipeline/tool_web.py`, egress-policy helper; reuse document preparation/chunking after secure fetch; network fixtures and parser tests.
- **Prerequisites:** S4, S7–S10 disclosure policy; explicit destination/network grant.
- **Tests:** Fake resolver/socket boundary for SSRF/rebinding, IPv4/IPv6 local targets, redirect denial, compressed/oversized bodies, slow responses, proxy inheritance, malicious MIME, active content, credential stripping, prompt injection, no memory auto-approval.
- **Security invariant:** No browser cookies/accounts, host services, ambient outbound worker network, or unlimited crawl. Sanitizing text cannot replace destination enforcement.
- **Smoke:** Mandatory controlled non-sensitive fetch and blocked-destination probes after explicit network authorization; tests default to mocks/local test-owned services.
- **Defer:** Authenticated browsing, arbitrary browser automation, scraping schedules, web writes, credential broker integration.

### S12 — Verified learning handoff

- **Objective:** Convert trusted job attestations into bounded persona-local learning attempts. Verification must inspect a Core-owned test specification/result channel that generated code cannot rewrite; stdout alone is insufficient.
- **Files/interfaces:** New `pipeline/tool_learning.py`; `pipeline/persona_development.py`, `pipeline/persona_runtime.py`; verifier fixtures/tests.
- **Prerequisites:** S8 audit/result integrity; namespace policy established in S2.
- **Tests:** Forged success output, rewritten tests, partial pass, verification unavailable, replayed evidence, persona mismatch, failed attempt preserved without skill gain, adventure knowledge does not become real-world skill/user fact.
- **Security invariant:** Successful execution is not verified learning. A narrowly authorized learning policy may record attempts; skill reinforcement requires independent verification. Shared memory remains on its existing reviewed write path.
- **Smoke:** Required one passing and one failing exercise; inspect persona evidence/counts and verify shared memory unchanged.
- **Defer:** Durable persona storage migration, self-certification, autonomous curriculum, unreviewed shared-memory updates.

### S13 — Persistent grants and scheduled work

- **Objective:** After session grants are proven, add explicit user-managed persistence, visible expiry/revocation, tool-version/resource revalidation, and a scheduler using the same broker. Split persistence and scheduler into separate acceptance checkpoints.
- **Files/interfaces:** Grant store adapter/config schema; future scheduler module; Core-owned settings/control surface; restart/scheduling tests.
- **Prerequisites:** S6–S12 as relevant; no scheduler bypass to existing service internals.
- **Tests:** Corrupt/edited grant files, missing resources, changed tool/policy versions, incompatible app upgrades, queued revocation, schedule storms, provider outage, restart without surprise work, global budgets.
- **Security invariant:** Persistent scope authorization does not silently become blanket mutation confirmation. Any future bounded standing approval requires explicit design and user opt-in; current per-request mutation confirmation remains.
- **Smoke:** Mandatory restart/revoke/schedule tests in disposable state.
- **Defer:** Cross-device grant synchronization, broad “always allow,” automatic external-account writes.

### S14 — Packages, media, and additional adapters

- **Objective:** Publish an extension checklist and add one capability family at a time: quarantined declarative package import; one-shot screen/mic/media; narrow credential-backed integrations. Each gets its own resource/disclosure policy and acceptance gate.
- **Files/interfaces:** Core registry/contracts/broker; future package installer and separate media/credential adapters; persona asset resolver only for already validated installed assets.
- **Prerequisites:** S7 isolation, S10 export, S11 parser/egress as applicable; credential storage reviewed before account tools.
- **Tests:** Archive hazards from section 3; unsigned/changed executable adapter rejection; no manifest-granted scopes; output injection; secret-free telemetry; sensor stop/revocation; content provenance; installed packages immutable and saves separate.
- **Security invariant:** Workshop remains data-only. Third-party executable extensions must use a separately confined worker protocol and installation approval; never `import` package-provided Python into Core. Signing identifies origin, not safety.
- **Smoke:** Required per adapter/platform. Steam distribution does not waive local validation or permission gates.
- **Defer:** Generic executable marketplace, continuous surveillance defaults, remote code loading, universal tool compatibility claims.

### Acceptance subdivisions for the broader milestones

Each sub-slice inherits its parent milestone's files, tests, invariants, and deferred work, limited to the objective below. The explicit dependencies in this table refine the broader parent ranges: independent public-web fetching, read models, or learning need not wait for unrelated adapters. A later sub-slice cannot be marked complete using only the preceding one's test results. S1–S3 are provider-free with no external I/O; S2–S3 may maintain bounded in-memory state. S5 and S6 use test-owned filesystem state; no live OS backend is permitted before S7's gate.

| Sub-slice / class | Objective and dependency | Required focused evidence / smoke gate | Remains deferred |
| --- | --- | --- | --- |
| S4a — Application/CLI | After S3, attach trusted invocation context and inert local preview/approve/deny/status. | Command precedence, session lifetime and provider-disabled tests; local CLI smoke. | HTTP approval and job execution. |
| S4b — API control boundary | After S4a and approval-channel decision, add separately enrolled control-client authorization plus bounded ingress. May wait until browser approval is actually needed. | Shared bearer rejected for approval; origin/host/body/read-time controls; authenticated API smoke. | Remote access, generic chat-based approval. S4a can support S8 via CLI without S4b. |
| S7a — Backend contract | After S5–S6, specify one enforcement profile and fake-supervisor lifecycle. | Capability mismatch must deny; cancellation/recovery contract tests. No manual execution smoke yet. | Installing/starting a backend or claiming isolation. |
| S7b — Native isolation | After S7a and explicit backend choice/installation, implement and validate that platform adapter. | Actual selected backend conformance, canaries, resource limits and teardown. Mandatory native-runtime smoke. | Other platforms and implicit host-process fallback. |
| S9a — Proposal adapter | After S4a/S8, route one provider task to strict untrusted tool proposals. | Fake-provider adversarial tests, then one live proposal-review-execution smoke. | UI expansion and automatic chaining. |
| S9b — Presentation | After S3/S4a status contracts, expose bounded tool counts/status; this may be brought forward independently of S9a. | Snapshot privacy tests and apartment visual smoke. | Approval UI unless S4b is separately complete; detailed public artifacts. |
| S10a — Filesystem read/copy-in | After S5–S8, resolve exact read grants and copy selected bounded files. | Windows and WSL containment/race tests; disposable-directory smoke. | All host exports and private-data disclosure. |
| S10b — New-file export | After S10a, approve an exact destination and create without replacing an existing file. | Exclusive-create/conflict/retry tests and separate export smoke. | Replacement, deletion and moves. |
| S10c — Guarded replacement | After S10b, bind replacement to expected original content/identity and a recovery policy. | Concurrent edit/rename, stale approval, backup/recovery tests and replacement smoke. | Recursive operations or promises of rollback for remote effects. |
| S11a — Web fetch | After S4 control and egress/disclosure policy, fetch inert bounded text from an explicit approved destination. | Mock DNS/socket/redirect/timeout tests; controlled fetch smoke. S10 export is not required for public-text fetching. | Complex parsing, credentials and private inputs. |
| S11b — Isolated parsing | After S11a and S7b, parse supported untrusted formats through a constrained worker and normal document preparation. | Malformed/expanded-input bounds and worker isolation tests; disposable parser smoke. | Arbitrary browser execution, archives until S14a. |
| S13a — Persistent grants | After session grant lifecycle and S6 recovery pass, add explicit persistence and resource/version revalidation. | Restart/revoke/corruption tests and disposable persistence smoke. No dependency on completing every web/learning adapter. | Scheduling and standing mutation approvals. |
| S13b — Scheduling | After S13a, S8 and the selected tool's conformance gate, submit scheduled requests through the same broker. | Queue revocation, clock/restart/budget tests and scheduled-job smoke. | Mutation scheduling without separately approved standing-consent design. |
| S14a — Declarative packages | After isolation, safe export and parser contracts, implement quarantine/manifest validation and installation. | Archive traversal/link/bomb/collision tests; package install/rollback smoke. | Executable plugins and media access. |
| S14b — One-shot media | After broker and resource-policy gates, implement one sensor/media adapter at a time. | Device/region grant, disclosure and immediate stop tests; per-adapter smoke. | Continuous capture and account credentials. |
| S14c — Credential-backed adapter | After separate credential-store review, add one narrow origin/account-bound adapter. | Secret canaries, origin binding, revocation and uncertain remote-effect tests; disposable-account smoke. | Generic account automation or worker secret access. |

S12 verified learning may follow S8 directly once its verifier contract is ready; it need not wait for S9–S11. Evidence must come from a verifier outside generated code's authority. Keep failed or inconclusive attempts distinct from skills, and route any separately requested shared-memory write through its existing reviewed Core policy. No tool result automatically changes personal memory or fictional canon.

## 5. Validation and operational handoff

Add `tests/fixtures/tool_security_cases.json` and a provider-free `pipeline/tool_security_eval.py` when S3 stabilizes. Record aggregate authorization, denial, stale/replay, cancellation, and privacy outcomes through a new explicitly allowlisted experiment-ledger case type; use `provider=none`/`model=none` where appropriate. Add separate backend conformance evidence at S7, recording backend/platform/policy revision and test skips. Report parser success, authorized execution, containment checks, and learning quality separately; a denied request can be a correct security pass.

Keep a small mandatory regression set throughout: no grant; forged confirmation; changed arguments after approval; cross-session/persona/adventure access; duplicate concurrent execution; cancellation/uncertain outcome; oversize/malformed output; secret canaries absent from public views; zero-provider controls. Provider-quality fixtures are public/test-owned and cannot be prerequisites for deterministic authorization.

Manual smoke gates follow the acceptance subdivisions: S4a/S4b, S5, S6, S7b, S8, S9a/S9b, and each later live adapter. S7a is a contract-only checkpoint. S1–S3 can be tested locally without asking the user to repeat CLI commands, but the initial Sol assignment remains S1 only. Stop at an actual platform/configuration or smoke-test gate, not after every value-object edit. Before executing a backend suite, explicitly verify it uses disposable resources and no live user memory, Chroma, credentials, or private documents.

Future security evaluation should include fuzz/property tests for parsers/path handling and fault injection for lifecycle transitions. An independent review is appropriate before enabling hostile code or host writes. Unit tests, a successful WSL smoke, and a clean audit each provide different evidence; none proves immunity from all attacks.

## 6. Roadmap alignment and decisions still needed

- **Observed documentation:** ROADMAP.md identifies itself as authoritative v4. ROADMAP.v5.md still identifies itself as a proposed successor; ROADMAP.v4.md is comparative/historical context. Preserve these files during this pass. This sprint plan does not silently adopt v5.
- **Observed mismatch:** v5's Current position and Stage E/F/H headings retain older “next/later” descriptions while their bodies record completed routing, H0, and initial tool slices. Update status prose during a later authorized documentation change; do not count a description primitive as a secure executor.
- **Observed mismatch:** AGENTS.md includes stale claims about health/models/chat-only API exposure and CLI-only proposal persistence alongside newer document/application endpoints and writers. Security work should reference the actual API/application methods and reconcile those statements explicitly before adding controls.
- **Recommended ordering:** Pure F contracts/grant/broker work can proceed now using existing provider seams. It need not wait for every specialist router. Gate dangerous execution on authentication, audit/recovery, and actual isolation; gate filesystem/network/media on their resource and disclosure controls. H0 remains usable independently.
- **Recommended scope:** All new model-reachable effects go through the broker. Existing trusted explicit memory/adventure commands continue using their tested Core controllers. Exposing any of them as a model tool requires a separate adapter and equivalent authorization; declaring the new broker does not retroactively gate every existing write.
- **Deferred independent decisions:** Durable persona learning policy, credential storage, automatic book/adventure-local notes, and executable plugin marketplace. None is required for S1–S3.

### Review decisions before implementation

These are recommendations and later gates, not unresolved blockers for S1. Record the operator's actual decision when each affected integration begins; writing this plan does not grant access.

| Decision | Recommended starting policy | Must be settled before |
| --- | --- | --- |
| Initial approval channel | Trusted local CLI; browser approval only through a separately enrolled control client. Generic chat/OpenWebUI credentials cannot approve. | S4a local trust binding; S4b for browser/API controls. |
| Supported isolation backend | One explicitly configured VM/equivalently isolated backend with verified enforcement; unsupported machines retain default denial. No normal host/WSL subprocess fallback. | S7b and any executable exercise. |
| Session versus persistent grants | Server-created session-instance binding first, based on a trusted authenticated principal. Persistence requires explicit settings and restart/revocation tests; no implicit always-allow. | S2 establishes session policy; S13a establishes persistence. |
| File export policy | Exact read/copy-in, then separately confirmed new-file exports; replacement requires expected-version checks and recovery policy. | S10a/S10b/S10c respectively. |
| Private data to hosted providers | Disabled by default. Any future exception must bind selected content, owner, destination/provider, purpose and request; require separate disclosure permission and confirmation, with no automatic fallback to another destination. | Any private result enters a hosted model/web request, even before S11. Local reads alone never authorize it. |

Result provenance must retain enough resource/disclosure classification for Core to enforce the last decision. If that classification is absent or ambiguous, withhold the private payload from external requests. Credential secrecy cannot be guaranteed by a redaction prompt.

## Recommended first foundational slice for Sol to implement

Implement **S1 only**. The registry and exact-scope permission evaluator already exist; extend them compatibly rather than recreating them. Add strict, bounded, immutable versioned tool proposal/result contracts and the inert v1 `sandbox.run` argument contract. Reject every authority-bearing input field and make all Core-generated invocation metadata structurally separate. Keep operation schemas finite and handwritten.

Likely files: `pipeline/tool_registry.py`, new `pipeline/tool_contracts.py`, `tests/test_tool_registry.py`, new `tests/test_tool_contracts.py`; add only narrowly required architecture/status notes to AGENTS.md/ROADMAP.md/ROADMAP.v5.md and list every changed file in session.files.md during implementation. Do not add user commands for interfaces that are still inert.

Run focused contract, registry, permission, and sandbox tests with provider-free fixtures, then the required repository regression checks using only test-owned state. If a broad suite has an unrelated failure, record it precisely rather than repairing unrelated code or calling production services. No live provider, network, executable backend, grant persistence, application dispatch, or temporary input materialization belongs in S1.

Acceptance: malformed/oversized/forged proposals fail closed; valid proposals remain inert; nested data cannot change after validation; public metadata/results obey explicit limits; existing constructors/default-deny behavior remain compatible. Report tests actually run, residual limitations, and that OS isolation has not been implemented.

**Sol implements S1 only, runs focused provider-free tests, and stops after reporting the result. No smoke test is required yet. S2 requires a subsequent implementation assignment.**
