# StarFur sandbox backend architecture and implementation plan

Planning date: 2026-09-09. Scope: repository inspection and this document only.
No tests, providers, external services, virtualization commands, installations,
or runtime-data operations were performed. Platform statements below are design
assumptions requiring current official-document verification before integration;
this offline review does not certify a Windows build or isolation product.

Evidence convention: **Observed** describes inspected source/tests or documents;
**Inference** describes consequences inferred by inspection, not reproduced
failures; **Recommendation** describes future work. Paths are repository-relative.
The existing checkout contains extensive tracked and untracked changes. Those
are the baseline, not changes attributable to this plan.

## Current architecture and security boundary

**Observed:** `pipeline/tool_contracts.py` supplies immutable, bounded proposal
and result envelopes, exact schemas, duplicate-key/nonfinite rejection, and the
initial `sandbox.run` contract with `retry_class="never"`.
`pipeline/tool_permissions.py:evaluate_tool_permission` evaluates exact scopes.
`pipeline/tool_grants.py:ToolInvocationIssuer` binds proposal digest, resources,
principal, session instance, persona/adventure labels, policy and expiry;
`SessionToolGrantController.claim` and
`pipeline/tool_approval.py:ToolApprovalController.claim` consume separate finite
authority records. These are application controls, not OS containment.

**Observed:** `pipeline/application.py:_new_session_slot` constructs a disabled
broker without a durable journal. `_local_tool_control` exposes inert local
preview/grant/approve/deny/cancel commands; it does not dispatch execution.
`docs/COMMANDS.md:Local Inert Tool Review` describes this correctly. Shared chat
cannot supply the internal trusted-control flag; API tests
`test_shared_chat_api_cannot_grant_or_approve_tool_requests` and
`test_tool_namespace_preempts_forged_document_context_extension` cover that
boundary. Conversation identifiers are routing keys, not authenticated owners.

**Observed:** `pipeline/sandbox.py:SandboxService.run` validates text input and
materializes a temporary host directory for an injected backend. Its default is
disabled. No native isolation backend exists. `SandboxPolicy` declares timeout,
input/output bounds and no network, but no CPU/RAM/process/disk ceilings or
supervisor cancellation protocol. `pipeline/tool_audit.py:ToolAuditLog` is an
in-memory audit; `pipeline/tool_runs.py:ToolRunJournal` is separate durable
intent/outcome storage. Neither is a tamper-proof security service.

The following are execution blockers, not evidence of a currently exposed
hostile-code executor. Their reproductions belong in future test-owned fixtures.

| ID / severity | Observed evidence and architectural consequence | Required action / gate |
| --- | --- | --- |
| F1 / high | `SandboxService.run` defaults missing `available` to true and only checks `supports_policy` when callable. A legacy injected backend can execute without affirming enforcement. `tests/test_sandbox.py:RecordingBackend` exercises that compatibility path. | Mandatory typed capability evidence; missing, malformed, false or stale enforcement denies before copy-in. Before any executable integration. |
| F2 / high | `ToolBroker.__init__` calls `reconcile()` on every injected journal. `reconcile` marks every unfinished intent unknown, regardless of whether its owner is live. `submit` accepts an existing journal intent and constructs a new awaiting-approval record without rejecting its durable terminal history. | One supervisor owns reconciliation under a lifetime lease; fence dead owner epochs and reject reuse of any admitted durable run ID. Never resurrect a historical run through fresh approvals. Before execution. |
| F3 / high | `ToolRunJournal._retain` deletes any two-record run, including unknown outcomes, and renumbers sequences. `_recover_pending_locked` accepts only prefix-compatible replacements. | Crash after writing a compacted pending file can conflict with the current log; eviction also loses replay evidence. Introduce crash-safe generations/compaction and a bounded admission/epoch policy that rejects old IDs after detailed retention expires. Preserve unresolved quarantine obligations. Before execution. |
| F4 / high | `_read_records` reads the whole file, checks lifecycle shape but does not compare outcome binding fields against its intent. Schema equality admits boolean `True` as version 1. Journal paths use ordinary host opens. | Bound bytes/lines/depth before parsing; strict integer versions and closed reason/state combinations; verify cross-record bindings; secure Core-owned directory/handles and fail on reparse/link substitution. Add storage fault tests. Before execution. |
| F5 / high | `ToolBroker.run_queued` holds its lock through synchronous `execute`. `cancel` cannot acquire that lock to interrupt it. Queued dispatch checks context but not expiry/revocation again after authority was consumed by `queue`. | Separate effect supervision from broker lock; define dispatch authorization deadline, cancellation token and revocation generation checked immediately before launch. Stop/fence running work on revocation. Before execution. |
| F6 / high | `run_queued` maps arbitrary executor exceptions to `failed`. `_journal_reason_for_state("outcome_unknown")` returns `restart_reconciliation`, which `record_outcome` rejects. | An exception after launch may mean an effect occurred. Make unknown a valid durable outcome with closed operational reasons; distinguish proven prelaunch failure from uncertain postlaunch completion. Before execution. |
| F7 / high | Broker verifies result invocation ID but validates its tool/version through the result-selected registry contract. Current registry has one tool. | Match invocation, operation, tool/version, policy and worker generation before accepting a result as more tools appear. Before modular execution. |
| F8 / medium | `SandboxService` copy-in/cleanup errors fall outside its backend exception handler; case-insensitive collisions are not excluded by exact-string duplicate checks. `ToolProposal` path validation is weaker than `SandboxFile`. `_report` appends a truncation marker after its byte cap. | Unify portable input validation before approval, cover file/directory and case collisions, normalize safe failures, count marker bytes, and cap streams while receiving them. Before native copy-in/output. |

**Test evidence limits:** `tests/test_tool_runs.py` contains six cases for basic
round trip, same-process object recreation/reconciliation, expiry, truncated or
conflicting pending data, valid extension and simple retention. It does not
establish process-death recovery, disk-full behavior, retention crash safety,
concurrent brokers, or actual no-reexecution after restart.
`tests/test_tool_broker.py:test_optional_durable_journal_records_outcome_and_never_restores_authority`
asserts an empty restarted broker, not refusal of resubmission of that ID.
`test_concurrent_dispatch_invokes_executor_once` covers threads in one broker.
`tests/test_sandbox.py` uses fake backends; no containment claim follows.
User-reported passing WSL suites are valuable evidence for those cases only.

**Documentation discrepancies:** `ROADMAP.md` identifies itself as authoritative
v4; `ROADMAP.v4.md` and `ROADMAP.v5.md` identify successor proposals. Do not adopt
a new authority silently. The v5 Stage E/F/H headings still say later while
their bodies describe implemented foundations. S4/S5/S6 smoke labels in the
roadmaps/sprint lag reported test results, but S6's full crash matrix is still
unproven. “Completed journal foundation” must not imply completed execution
recovery. `AGENTS.md` has legacy health/models/chat-only API and CLI-only proposal
persistence claims alongside newer application/document paths. Its output and
policy-support descriptions also overstate F1/F8. `session.files.md` retains a
large historical copy list; this plan neither clears nor updates it.

## Recommended backend strategy

Keep Core's tool broker and a separate execution supervisor. Use one explicitly
selected Hyper-V adapter as the first Windows reference implementation. Keep
Windows Sandbox optional and manual until it independently passes conformance.
No automatic downgrade from an unavailable VM to WSL, containers or a host
process. Backend installation, host readiness, policy compatibility, invocation
authorization, and execution outcome are separate states.

Proposed interfaces, owned by trusted Core code:

| Interface / proposed home | Owns | Must never own |
| --- | --- | --- |
| `BackendDescriptor`, `EnforcementProfile` / `pipeline/sandbox_backend.py` | Stable ID/version, supported host/guest families, isolation class, bounded supported tasks and explicit enforcement dimensions | Executables, plugin import paths, grants, probing, automatic selection |
| `BackendObservation`, `BackendReadiness` / same module initially | Supplied evidence revision/age, configured/unsupported/unprobed/unavailable/mismatch state; pure readiness evaluation | Discovery side effects, approval, a claim that availability proves confinement |
| `ExecutionLimits` / same module | Explicit units and finite ceilings for wall time, CPU allocation/budget, RAM, process count, disk, input, streams, artifacts and concurrency | Inferred limits from dashboard metrics or model prose |
| Supervisor protocol / later `pipeline/sandbox_supervisor.py` | Admit/start/query/cancel/stop verification; opaque run and worker-generation identity, fencing, leases | General shell, arbitrary VM names/paths, user-selected management commands |
| Hyper-V adapter / later `pipeline/sandbox_hyperv.py` | Fixed operations on enrolled StarFur VM resources, enforcement/readback, bounded transport | Authority issuance or management of unrelated VMs |
| Journal/controller / `tool_runs.py`, `tool_broker.py` | Durable admission and outcomes, exact authorization, replay rejection | Permission restoration from journal or model-provided identity |
| Presentation projection / later application read model | Sanitized status, unavailable reason and supported actions | Paths, guest outputs, VM inventory, secrets, automatic probing or setup |

Capabilities express specific enforcement, not a single `secure=True`. Evidence
must bind backend/image/supervisor/policy revisions. A guest's self-report alone
cannot prove host isolation. Unsupported limits deny. In-process adapters are
trusted code; Workshop must not supply them.

## Hyper-V reference backend plan

Use a managed VM with an immutable, verified base image and a fresh disposable
overlay per job. Start with one concurrent job and an offline, pinned Python
toolchain. A Linux guest is the recommended initial exercise environment; guest
choice and its maintenance/licensing must be confirmed before image creation.
Persistent supervisor/image caches are acceptable; reuse of a writable guest
across users, personas or jobs is deferred.

Client Hyper-V generally requires a supported Windows edition (such as
Pro/Enterprise rather than Home), compatible 64-bit CPU with SLAT and firmware
virtualization enabled, sufficient RAM/disk, and feature setup that may require
elevation/reboot. Exact supported editions, builds, architectures, servicing,
VM limits and coexistence with WSL2/security software require verification
before deployment. Do not infer Hyper-V management support merely from WSL2
working. Guest RAM, disk overlays, image downloads, cold starts and antivirus
inspection compete with Ollama and games; measure these costs before publishing
minimum requirements. No exact footprint or latency is promised here.

Verify these official references in the later explicitly authorized platform
research slice: Microsoft Learn's Hyper-V system requirements, VM processor and
memory settings, virtual switches, integration services, VM lifecycle APIs,
Hyper-V sockets, and guest support documentation. Starting reference:
https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/host-hardware-requirements
(not fetched during this pass).

Execution sequence: validate -> preview -> grant plus approval -> revalidate
authorization/readiness -> durably admit -> allocate fenced worker -> enforce
limits and verify transport -> launch fixed exercise -> collect bounded result
-> stop and verify worker termination -> finalize outcome and cleanup status.
Admission must precede every VM side effect. Persist enough bounded identity to
find an orphaned worker after a supervisor crash, without accepting VM identity
from a provider. A failed journal write prevents launch; uncertain completion
prevents replay. Cancellation acknowledgement differs from verified stop.

The Windows management component needs a narrow authenticated local protocol,
an enrolled principal and ACL-protected installation/storage. Running StarFur or
the Steam client as administrator is not acceptable. Avoid broadly adding users
to Hyper-V Administrators for routine operation; assess a narrow helper/service
whose verbs and resources are fixed. Administrative code cannot execute supplied
PowerShell/script text. Where platform APIs require a management subprocess, it
must use fixed trusted code and structured arguments; generated code runs only
inside the guest. The helper is part of the trusted computing base and requires
independent review.

The WSL prototype is a client of that Windows service. WSL localhost access,
Windows interop and knowledge of a conversation ID do not authenticate it. Design
the transport before implementation; prefer a narrow non-IP guest channel where
supported and verified. Do not open an unauthenticated host TCP management port
for convenience. Hyper-V sockets or other channels are candidates, not claims
of established Linux-guest compatibility. If secure bounded transport is not
demonstrated, readiness remains denied.

Initial guest policy: no virtual NIC, shared folders, clipboard, enhanced-session
drive sharing, USB/device/GPU passthrough, host sockets or inherited environment.
Copy only approved bounded text into the disposable guest using a framed channel
or read-only input medium. Never mount the project, home, Steam library, Core
database/journal, WSL filesystem, or credential stores. Run exercises unprivileged
inside the guest; keep the runner/toolchain separate from supplied source.

Enforcement responsibilities:

| Limit | Enforcement requirement |
| --- | --- |
| Wall time and cancellation | External host watchdog survives client disconnect; terminate the entire owned VM when guest shutdown stalls; verify stop |
| CPU/RAM | Hypervisor allocation/caps plus tested guest process controls; define CPU-rate versus CPU-time semantics explicitly |
| Processes | Guest process/cgroup mechanism for the full descendant tree; independent VM kill fallback |
| Disk | Bounded guest writable volume and host overlay quota/accounting; reserve headroom; differencing-file growth cannot fill host disk |
| Output/artifacts | Byte/frame/count limits at receiving boundary, including stderr, filenames and error framing; backpressure and abort on excess |
| Concurrency | Host admission budget across all conversations, not only each broker's per-session record limit |

Guest limits mitigate resource abuse; the outer VM and supervisor protect the
host if generated code defeats guest controls. No service may advertise a limit
whose failure behavior is untested. `pipeline/system_metrics.py` remains passive
presentation data, not the enforcement source.

Treat results as hostile data: match run/tool/version/generation; reject extra
fields, malformed/truncated frames, nonfinite values, control sequences and
oversized buffers before accumulation. Preserve evidence without interpreting
stdout as instructions. Backend success means the task finished; it does not
verify learning. `pipeline/persona_development.py` requires independent evidence
before skill reinforcement. Persona/adventure IDs label context, never grant
access; fictional knowledge cannot enter real-world memory through this path.

Cleanup uses enrolled resource IDs and verified containment, never wildcard
deletion of guessed VM names or directories. Quarantine uncertain resources and
report cleanup separately from task success. Destroying a guest cannot reverse
disclosed data or completed external effects, and deletion is not secure erasure.

## Windows Sandbox optional backend plan

Treat Windows Sandbox as a separate disposable pilot with its own capability
profile. It uses hardware virtualization and is available only on supported
Windows editions/builds. Closing discards the environment; a reboot inside some
versions can retain that running session's data. Neither restarting nor closing
is an acceptable substitute for explicit no-replay semantics.

Before a pilot, verify current Microsoft documentation for `.wsb` configuration,
CLI automation support and version limitations:
https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/
and its configuration documentation (not fetched here).
Networking, clipboard and other defaults must be overridden explicitly; disable
vGPU, audio/video input, printer redirection and unnecessary integrations. Do not
use writable host-folder mappings for output or map the repository. A read-only
mapping still discloses its contents and requires scoped input selection.

Its disposable workflow may simplify manual experiments but does not establish
automation, cancellation, per-process/CPU/disk enforcement, output collection or
service compatibility. If any required dimension cannot be enforced, classify
it manual-only and deny brokered `sandbox.run`. Never automatically select it
when Hyper-V is unavailable. A manual pilot uses synthetic data and never grants
production execution authority.

## Container/WSL/native-process disposition

A shared-kernel container has a different attack surface from a separate VM.
Docker Desktop may add a VM beneath containers; that fact alone does not attest
the complete mount/socket/network policy. Containers may later run inside the
reference disposable VM, or serve as explicitly lower-trust development fixtures.
Do not mount a Docker/Podman daemon socket, host filesystem, credentials or
privileged devices into a worker. Containers cannot satisfy this hostile-code
profile without a separately reviewed complete deployment.

WSL2 has virtualization but a normal WSL process shares its distribution and
often Windows integrations. Neither that process nor a native subprocess is
the accepted worker boundary. A subprocess may implement trusted host management
operations; it must not execute provider-supplied code on the host. Native Linux,
macOS, Windows Home and Steam Deck retain disabled execution until a separately
validated backend exists. This does not block their ordinary Core features.

## Steam/distribution impact

Make execution an optional feature. Core, resident presentation, ordinary memory,
adventures and configured chat providers must install/start without virtualization,
an image, the supervisor, administrator access or network access. Hyper-V adds
support and packaging work, but it need not become a base-product requirement.
Market optional sandbox prerequisites separately; do not promise identical tool
availability across operating systems. Existing zero-provider behavior remains
available independently of whether an execution backend exists.

Use a separately opted-in setup flow showing edition/firmware/feature/reboot,
download size, disk/RAM and privilege requirements. Never change BIOS settings,
Windows features, network switches, ACLs or group membership silently. Handle
setup cancellation/partial installation with execution disabled. Store worker
images, overlay data and journals separately from Steam-managed program files,
Workshop content and canonical saves. Do not put journals/credentials in Steam
Cloud or ship them in Workshop packages.

Pin and verify image/toolchain/supervisor versions, signatures/checksums and
update provenance; assess redistribution licenses and security patch ownership.
An update invalidates stale conformance/readiness evidence and drains or stops
owned jobs before replacement. Protocol/journal migrations must preserve unknown
outcomes and reject incompatible rollback. Workshop stays declarative; manifests
cannot select an executor, request elevation or install privileged adapters.

Uninstall stops owned workers and offers explicit handling of images, journals
and saves. It never deletes unrelated VMs or disables a globally shared Hyper-V
feature used by WSL/other software. Optional component failure cannot make the
apartment unusable. No claim of Steam certification is made by this plan.

## Must fix before any execution

Resolve F1–F8 before enabling an executor on user machines. Extend durable records
with a privacy-reviewed binding fingerprint or equivalent opaque immutable
admission identity; the current tuple does not bind changed operation content.
Document this deliberate change to AGENTS.md's current digest exclusion; do not
store raw proposals/resources or use a fingerprint as permission.

Define restart ownership and admission epochs before deciding retention policy.
Unknown jobs remain fenced until an operator/supervisor verifies they stopped;
their replay guard cannot disappear through normal detail retention. A backend
exception, lost acknowledgement, worker crash or kill during launch must never
trigger automatic retry. Generating a fresh model proposal also cannot replay
an admitted effect. A new user-authorized run is an explicit new action.

Make journal persistence mandatory for an execution-capable broker and fail closed
when its storage cannot be trusted or written. Default inert CLI operation can
remain journal-free. Close arbitrary task-kind dispatch with a Core-owned fixed
exercise mapping. Enforce approval against the effective policy/input snapshot,
including any later change of backend, image, toolchain or disclosure policy.

Private reads and external disclosure require different grants. No private
input/output may reach a hosted provider because a local model fails. Tool
results cannot directly create memories, skills or adventure events. Continue
using reviewed Core adapters for those mutations.

## Must fix before Hyper-V integration

Freeze the supported host/guest matrix and documented enforcement profile; choose
the authenticated management and guest transports; establish image ownership,
patching and installation rules. Validate capability/readiness contracts using
fakes before probing the host. Enrollment must identify only StarFur-owned VM
resources and a protected storage root; readiness inspection cannot enroll them.

Native path handling must address junctions, symlinks, all reparse points,
hardlinks, UNC/device paths, alternate streams, case/Unicode collisions, path
replacement races and WSL/Windows path translation. Controlled copy-in takes an
immutable snapshot of approved bytes. Do not treat `resolve()` followed by an
ordinary open as sufficient race protection. Never host-mount a guest-created
filesystem to parse its output; use a bounded untrusted-data channel.

Initial network access is completely disabled. Later public web retrieval is a
separate brokered fetch capability. If a guest network profile is introduced,
enforce destinations outside the guest: schemes/ports, DNS answers and rebinding,
redirect revalidation, IPv4/IPv6, loopback/private/link-local/metadata ranges,
proxy variables, arbitrary DNS and host/service addresses. A destination
allowlist is insufficient without resolution/connect-time enforcement. No
credentials or inherited proxy/cloud/SSH variables enter guest input or logs.

## Must fix before Steam packaging

Prove base-product install and offline launch on unsupported systems; separate
optional feature requirements from store minimums. Verify non-admin runtime,
privileged helper IPC authorization, update/uninstall recovery, licenses and
security patch delivery. Audit the actual shipped configuration, including
network/clipboard integrations and image provenance. Require independent review
before shipping hostile-code execution or host exports.

Do not let a read-only apartment poll create a VM, probe the host or execute a
job. Explicit readiness probing gets its own bounded command/API authorization.
Public status exposes safe unavailable/starting/running/stopping/unknown counts,
not VM paths, guest output, raw errors, principal identifiers or inventory.

## Recommended implementation order

These refine S7a/S7b/S8 of `astra.roadmap.sprint.md`; they do not replace its later
filesystem, web, learning or persistent-grant gates. New paths are proposals.
Every implementation slice updates the appropriate docs/copy manifest when
authorized. This planning pass intentionally updates neither.

| Slice | Objective and concrete files/interfaces | Prerequisites | Security invariants | Tests and smoke | Windows/WSL requirements | Deferred |
| --- | --- | --- | --- | --- | --- | --- |
| B1 / first Sol assignment | Pure descriptors, limits, supplied capability observations and deny/readiness decisions in new `pipeline/sandbox_backend.py`, `tests/test_sandbox_backend.py` | Existing contracts; this plan | No I/O or authority; explicit backend only; missing/mismatched evidence denies | Immutable/version/bounds/NaN/boolean/stale/missing-limit/zero-provider tests; no manual smoke | Portable fixtures, no OS discovery | Supervisor, probes, journal changes, VM creation and execution |
| B2 | Repair strict journal parsing/bindings in `tool_runs.py`, `test_tool_runs.py` | B1 can proceed independently | Reject malformed/oversized/cross-bound outcomes; protected storage specification | Invalid schema/depth/encoding/reason/binding and path-substitution fixtures; no execution smoke | Native file semantics tested in temp roots | Live execution |
| B3 | Repair retention and replacement recovery in same modules | B2; epoch/admission design | No compacted-history ambiguity or deletion of unresolved obligations | Inject write/fsync/replace failures and full-disk conditions; process-kill recovery smoke required | Native Windows and WSL-local filesystem; `/mnt/c` unsupported unless separately validated | Production repair or migration shortcuts |
| B4 | Durable admission, replay fencing and single recovery owner in `tool_runs.py`, `tool_broker.py`, tests | B3 | Historical IDs cannot reenter dispatch; live owners never reconciled by another broker | Resubmit after restart/retention, conflicting input, two brokers/processes, expired sessions; disposable multiprocess smoke | Lock/lease behavior on both platforms | Permission persistence |
| B5 | Pure supervisor lifecycle/cancel/result contracts in new `sandbox_supervisor.py`; narrow broker adapter changes | B1, B4 | Recheck authority at launch; no lock held through effect; unknown remains unknown | Fake slow/crashing worker, revoke-after-queue, timeout, duplicate/mismatched result, client disconnect; no native smoke yet | Injected clocks/transport only | Platform operations |
| B6 | Align copy-in/output contracts in `sandbox.py`, `tool_contracts.py`, tests | B1, B5 | Mandatory enforcement match before files; byte caps at ingress; no path reinterpretation after approval | Case/file-directory collisions, materialization/cleanup faults, flood/framing tests; temporary filesystem smoke | Windows and WSL | Host export and guest mounts |
| B7 | Document supported platform and image/transport profile; explicit read-only readiness adapter in `sandbox_hyperv.py` and dedicated docs | B1; current official documentation; approved platform decisions | Probe cannot install, start or elevate; unsupported denies | Fake discovery errors then explicit native readiness smoke | Windows host facts; WSL sees only authenticated summary | Provisioning and generated code |
| B8 | Narrow local supervisor enrollment and IPC authentication in platform helper/transport tests | B5, B7; privileged setup approved | Fixed enrolled resources; no broad management verbs, secrets in messages or provider identity | Unauthorized/replayed/wrong-user/malformed IPC; native disposable enrollment smoke | Native Windows service; independently authenticated WSL client | General remote service |
| B9 | Provision verified base and disposable guest; fixed harmless runner only | B3–B8; setup/image approval | No NIC, shares, inherited secrets or user data; bounded owned resources | Verify boot/config/stop/restart/cleanup; canaries outside guest; mandatory native smoke | Supported Windows/guest version; WSL client disconnect covered | Provider-generated code, warm mutable workers |
| B10 | Enforce resource ceilings, bounded guest transport and orphan cleanup | B9 | Watchdog outside guest; kill all descendants; quarantine until verified stopped | CPU/RAM/process/disk/output floods, sleep, fake result, helper/VM crash, host restart; mandatory conformance smoke | Actual Hyper-V backend required; fakes insufficient | Host writes, guest network |
| B11 | Connect `sandbox.run` through reviewed `tool_sandbox.py` to broker/application | B2–B10 passed; explicit execution opt-in | Journal required; one approved fixed task, no automatic retry; tool result remains untrusted | Approve/run once, cancellation, revoke, unknown, provider-disabled operation; mandatory harmless CLI smoke | Native worker and WSL client round trip | Self-approval, auto-learning and HTTP approval |
| B12 | Optional backend status read model and distribution/setup documentation | B7 status contract; B11 for running states | Polling has no effects; unavailable remains visible | Privacy/API/no-provider tests; apartment visual and unsupported-host smoke | With and without optional runtime | Broad dashboard administration |
| B13 / optional | Windows Sandbox manual conformance pilot, separate adapter if justified | B1 profile; explicit pilot approval | No silent fallback; incomplete enforcement remains manual-only | Synthetic canaries, integrations disabled, close/reboot/cancel/output behavior; mandatory native smoke | Supported Windows Sandbox version only | Production adapter until every requirement passes |
| B14 / later | Controlled new-file export, then separately guarded replacement via planned `tool_filesystem.py` | B11 and sprint S10 grants | Exact destination/operation; immutable result reference; no overwrite without expected identity and approval | Link/race/collision/stale approval/retry and outside-root canaries; separate native export smoke | Windows and WSL path boundaries | Recursive delete, arbitrary moves, automatic export |

Guest code is introduced only after B10's containment evidence. B11 must not be
used as the first experiment to discover whether B10 works. B12 and a manual B13
can remain deferred while the Hyper-V reference path is validated.

## Smallest safe smoke-test matrix

| Gate | Minimal test-owned scenario | Required evidence |
| --- | --- | --- |
| Journal admission/recovery | Kill a writer at intent, pending write, compaction and outcome boundaries; start a second owner; resubmit the old ID | Valid history or explicit denial; no effect replay; live owner preserved; unknown retained/fenced |
| Unsupported/disabled | Clean base install, absent helper/image, provider disabled, unavailable virtualization | Core/apartment still start; no elevation/download/probe during passive reads; execution denied |
| Native isolation | One fixed fixture in a fresh guest with harmless outside-host sentinels | Only approved input visible; host roots, sockets, clipboard, devices, credentials and network inaccessible |
| Resource enforcement | Bounded synthetic busy loop, child tree, allocations, disk/output flood and sleep | Each ceiling stops the owned job within documented tolerance; host headroom and unrelated processes preserved |
| Authority/cancel | Queue then expire/revoke; concurrent duplicate; cancel during run; change persona/session | No stale launch; verified stop or explicit unknown; no renewed authority from reconnect |
| Crash/result | Disconnect WSL, stop client/helper, crash guest, lose completion acknowledgement, spoof result identity | Surviving supervisor fences/stops owned resources; bounded result rejection; no automatic repeat |
| Lifecycle | Host restart during job, image upgrade, partial uninstall, cleanup failure | Orphans reconciled without running tasks again; unrelated VMs/saves intact; quarantined resources visible |
| Distribution | Standard-user base launch without Hyper-V; optional setup declined; image missing | Normal companion features remain usable; optional execution truthfully unavailable |

Separate test results for native Windows, WSL-local storage and the actual
Windows-worker/WSL-client bridge. Skips are unresolved gates. Keep fixtures free
of personal data and credentials. Do not run exploit payloads on the user's
working environment. Later benchmark/experiment-ledger integration should store
aggregate case outcomes and backend/image/policy revisions only; security audit
and recovery records retain their own purpose and access policy.

## Open decisions requiring user approval

The user has already approved the strategic direction: optional Hyper-V reference
backend, optional Windows Sandbox pilot, and no distribution dependency. Do not
ask them to approve that direction again.

Before affected implementation gates, obtain the actual host edition/build and
supported guest choice, explicit feature/helper/image installation authorization,
acceptable disk/RAM/CPU/idle budget, image download/patching policy and helper
transport enrollment. A Linux guest with pinned Python, one job at a time and
fresh overlays is the recommended starting point, pending compatibility review.
Persistent grants, warm guest reuse, host export, networking and private hosted
disclosure remain separate later decisions. Initial private hosted disclosure is
disabled. No current decision authorizes BIOS changes or privileged setup.

## Recommended first Sol slice

Implement **B1 only**: provider-free backend descriptors, capability/readiness
contracts and denial behavior in `pipeline/sandbox_backend.py`, with focused
pure tests. Keep supplied capability evidence distinct from host verification;
represent unprobed/unsupported/missing enforcement explicitly. Readiness never
supplies a grant or approval and never automatically selects a fallback backend.

Acceptance: immutable bounded versioned data; exact supported task/profile
matching; unknown/expired/malformed observations and missing limit enforcement
deny; no implicit success from a backend name or boolean; portable zero-provider
fixtures. Existing disabled runtime behavior stays intact. No manual smoke test
is needed for this pure slice. Report journal blockers F2–F4/F6 as outstanding
before execution; do not silently expand this assignment to repair them.

Explicitly defer VM creation, privilege changes, real execution, installer
changes, automatic backend selection, OS probing, supervisor processes, host
copy-in/export, journal integration and provider tool calls. A contract passing
its tests does not certify isolation. Further slices require their own specified
dependencies and evidence.
