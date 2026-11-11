# Private annotation deployment verification — review draft

## Targeted Astra N2b.2 review — 2026-11-11

REVIEW COMPLETED / ENFORCEMENT PENDING. Roger resumed Sol High implementation
after review. This is not a private-worker deployment or actual Windows probe.

Recommended candidate: establish an empty binfmt_misc instance owned by the
worker's new user namespace, not a bind mount of the ancestor registry. Upstream
Linux v6.18 load_binfmt_misc() selects the first instantiated registry in the
user-namespace ancestry; bm_fill_super() creates per-user-namespace state.
This avoids selecting ancestor WSLInterop F handlers while keeping ordinary
Linux ELF handling. Installed WSL behavior must be demonstrated, not inferred
from uname, an empty directory, or merely hiding /init. Never write to the
existing registry or change WSL configuration; unsupported isolation denies.
Source: https://raw.githubusercontent.com/torvalds/linux/v6.18/fs/binfmt_misc.c

Separate complementary gates: a minimal reviewed Linux executable/library
image with immutable executable bytes and non-executable writable storage;
private root/proc/network/PID lifetime; removal of outside handles; inherited
architecture-checked syscall policy denying host socket families (including
AF_VSOCK), namespace/mount mutation and alternate descriptor/IO bypasses.
Seccomp cannot inspect path strings and alone is not the sandbox. Retain only
required private networking and controlled IPC. Policy must survive real Linux
child exec; denying all exec does not satisfy Ollama runner requirements.
Sources: https://docs.kernel.org/6.18/userspace-api/seccomp_filter.html
and https://github.com/microsoft/WSL/blob/master/doc/docs/technical-documentation/interop.md

COMPLETED prerequisite: pin worker and fork-child pidfds before
releasing each test phase. Existing supervise() acquired handles only after
ready, weakening evidence on earlier startup failure. Focused fake tests must
cover phase order, failure, interruption, malformed diagnostics and PID drift;
then one separately bounded synthetic root verification, not an old retry.
Verification PASS:8 focused fake tests, native root smoke exit0, full1,459
OK/one expected skip. No N2b.2 native gate or production enforcement added.

Subsequent slices must distinguish (a) private-registry/kernel prerequisite,
(b) executable/socket/syscall enforcement and inheritance, and (c) integrated
deployment verification. A synthetic Linux canary is not actual Ollama/GPU or
complete Windows-interop evidence. No real Windows executable, relay or private
input is to be used just to discover whether a boundary works.

## N2b scope split — pinned interpreter finding (2026-11-10)

Read-only observation as roger in StarFur-Forge WSL:
`/proc/sys/fs/binfmt_misc/WSLInterop` is visible/enabled, uses /init, and has
the F flag. No registration write, /init execution, Windows data access or
relay connection was attempted. The kernel can keep an F interpreter open
across root/mount changes. Therefore an absent /init pathname in a new root
or a cleared WSL_INTEROP variable is not interop denial evidence. This is a
design prerequisite, not an observed escape or current StarFur vulnerability.

### N2b.1 approved synthetic restricted-root test — PASSED final retry

Final retry2/2 passed root, worker/child, capability and cleanup controls.
Fix preloads ctypes ABI declarations; no barrier removed. Earlier failed
attempts remain historical evidence. Full provider-free regression passed1,454
with one expected skip. N2b.2 conditional approval does not resolve its control
design; targeted Astra review required before any actual interop attempt.

#### Historical failure/retry notes (superseded by final pass above)

Retry1/2 identified a helper lazy-import bug in capability ABI declarations.
Declarations now preloaded before isolation; no runtime/library path restored.
A final retry2/2 is authorized, not a loop. Pause if it fails.

Roger authorized ordinary helper correction and at most two further native
attempts. No barrier may be weakened. Old fixture stays preserved; stop if two
more attempts fail or a security/configuration expansion is needed.

Native gate exited1 (fixture_not_ready); retained fixture requires diagnosis.
No N2b.2 run. No containment or cleanup pass is inferred. No automatic retry.

Roger approved .1 and then .2 conditional on .1 success, restated 2026-11-11.
No permission to risk Windows data, change global settings or weaken a barrier.
N2b.2 design uncertainty must be resolved before a live interop attempt.

Allow only an opt-in helper in StarFur-Forge WSL as roger, reusing the bounded
rootless user/network/PID/private-mount pattern. One fresh mode-0700 Linux /tmp
fixture contains the candidate root, a synthetic outside file/socket and an
inside marker. Use the trusted preloaded Linux test process; no copied host
root, executables from Windows, package installation, real relay, private data,
GPU, services, binfmt/config changes, or privileged host action.

1. Verify every namespace and private propagation, exact scratch identities,
   and positive control on the outside canary. Create mountpoints only in the
   owned fixture; pivot to its minimal root, chdir to / and detach the old root
   in the private namespace. No mounting over real /proc, /run, /mnt or /init.
2. Close all outside directory/file handles and keep only the intended test
   IPC and bounded synthetic result handles. Drop capabilities, verify no
   new privileges, and run a synthetic fork child without exec. Check current
   root/mount identity, inside marker visibility and outside canary denial in
   both processes. Probe exact test paths only, never real Windows paths.
3. Verify parent mount/path identities and canary still unchanged, exact
   process exits and cleanup of known fixture entries. Limit to 55 seconds
   plus a 2-second watchdog kill window. Refuse unavailable primitive, unclear
   root/FD state, permission escalation, any unexpected reachability/effect
   or uncertain cleanup. No fallback to a less isolated test or actual interop.

Passing N2b.1 proves only the synthetic filesystem/root controls. The exact
helper and command must be reviewed before native execution; this plan neither
implements nor approves it. No native gate executed in this documentation slice.

### N2b.2 actual WSL interop barrier — reviewed candidate, enforcement pending

Require a worker-scoped prevention mechanism covering the pinned binfmt
interpreter, relay sockets, inherited descriptors and host socket families
without disabling ordinary WSL interop. A synthetic no-exec process cannot
establish this for Ollama, which must be able to launch its reviewed runner.
Before choosing a production control, review how to preserve only required
Linux child execution and prove all Windows relay paths denied. If this cannot
be shown on the supported kernel, deny private processing. Do not change
global binfmt, WSL configuration or existing clients to make a test pass.
Actual executable/host bridge probing, GPU and real inference remain outside
this proposed scope.

References: [Linux binfmt_misc F behavior](https://docs.kernel.org/admin-guide/binfmt-misc.html),
[pivot_root](https://man7.org/linux/man-pages/man2/pivot_root.2.html),
[Microsoft WSL interop internals](https://github.com/microsoft/WSL/blob/master/doc/docs/technical-documentation/interop.md).

## N2 test-owned relay controls (2026-11-10)

N2a COMPLETED / NATIVE WSL PASS: synthetic masked/unmasked, descriptor and
cleanup controls only; no deployment proof. N2b remains pending separate scope.

Historical 2026-11-10 approval covered N2a only. Roger later approved N2b.1
and conditional N2b.2, then resumed Sol implementation after Astra review.
The newer approval does not authorize global configuration, real Windows
execution, relay access, GPU/models or private-data disclosure.

N1 proved synthetic TCP network/PID isolation, not pathname-socket or descriptor
containment. Network namespaces isolate abstract UNIX names, not access through
a visible socket pathname. Mount namespaces start with inherited mounts. WSL
interop can discover /run/WSL servers even without WSL_INTEROP; clearing an
environment variable is not an interop barrier.

Proposed approval is for N2a only: add/review/synchronize one opt-in helper,
then run it as roger in StarFur-Forge WSL using the existing unprivileged
user/network/PID/private-mount pattern. No sudo, installs, production sockets,
GPU, models, private data, Windows process launch, service/WSL configuration,
binfmt change, internet or host mount propagation. No broader authorization.
Use one mode-0700 test-owned temporary directory, fixed children within it,
one filesystem UNIX socket, a synthetic pipe and one private socketpair.
No persistent namespaces or new runtime components.

1. Parent establishes a positive connection to its exact synthetic socket.
   A network-namespace-only fixture may also connect to this synthetic path;
   this is an expected positive control, not an attempted production bypass.
2. A fresh isolated fixture checks distinct user/network/PID/mount identities
   and private propagation before any mount action. Bind a test-owned empty
   directory over the exact test-owned canary directory, within its own mount
   namespace only. Do not cover /run, /mnt, /proc or any system directory.
   Drop capabilities before running probes. Both worker and synthetic child
   must fail to reach the hidden canary; parent must still reach it and see
   unchanged mount/path identity. If prerequisites or mount checks fail, stop.
3. Mark only a synthetic sentinel descriptor inheritable in the test supervisor;
   launch with close_fds and explicit control-channel pass list. Worker must
   not inherit the sentinel (compare identity, not just descriptor number),
   and its synthetic child must not inherit the worker’s control endpoint.
   Use bounded socketpair messages; an opt-in synthetic SCM_RIGHTS packet with
   a test pipe descriptor must be refused with every received descriptor closed.
   Truncation must also refuse, not accept a prefix as a complete message.
4. At most 55 seconds plus 2 seconds for the watchdog, bounded per-I/O waits,
   no retries without isolation. Use exact process handles to verify exits;
   release descriptors, remove only the known synthetic socket/files and empty
   test-owned directories, and verify host canary/mount state unaffected.
   Stop for permission/elevation requirements, unexpected reachability,
   lingering descendants, uncertain cleanup or any production effect.

Intended invocation after the helper exists and its exact source/hash is reviewed:
`/usr/bin/timeout --signal=TERM --kill-after=2s 55s .venv/bin/python -I -B -S scripts/private_worker_relay_smoke.py`
from the WSL repository root. Execution is approved for N2a only. Required
gate is one native run; syntax and read-only prerequisite checks are not gates.

A pass would establish the listed synthetic controls only. No claim that all
host files, relays, aliases, or Windows interop are blocked. N2b requires a
reviewed restricted root and actual WSL relay/Windows-execution denial evidence
under separate approval; do not change global settings or probe real agents.
Actual inference children, driver/GPU access and private dispatch remain gated.

References:
- https://man7.org/linux/man-pages/man7/network_namespaces.7.html
- https://man7.org/linux/man-pages/man7/mount_namespaces.7.html
- https://man7.org/linux/man-pages/man7/unix.7.html
- https://github.com/microsoft/WSL/blob/master/doc/docs/technical-documentation/interop.md

## Accepted isolation/control direction — 2026-11-05

Roger approved the targeted Astra recommendation as DESIGN ONLY. Core depends
on a platform-neutral private-worker protocol and demonstrated enforcement, not
WSL APIs. First reference direction: isolated worker, dedicated Ollama and all
inference descendants in one private network namespace with loopback only, no
external interface/route; ordinary Ollama/OWU remain untouched. A narrowly trusted
supervisor establishes isolation before private input and supplies a private
inherited control socket pair. It is not a host HTTP proxy or generic relay.
The worker adapter talks directly to its measured Ollama within that namespace.
Namespace-qualified endpoint/process epoch replaces any assumption that Core's
127.0.0.1 is the worker's 127.0.0.1. Existing locality-v1 objects are not upgraded
or silently reused; a separately versioned deployment/transport policy is needed.

IMPORTANT D1 refinement: burn the exact dispatch slot BEFORE the first possible
Core-to-worker write of private bytes, not merely before the eventual HTTP body.
No replay after possible channel disclosure; post-call rejection cannot undo it.
Channel ownership comes from trusted launch/handle provenance and process epoch,
not IDs or SO_PEERCRED alone (socketpair credentials predate later exec/identity
changes). No arbitrary messages, destinations, file access, FD-passing requests,
tools or grants. Close all unrelated inherited handles; worker control handles
must not leak to Ollama/runners. Bounded schemas are data, not capabilities.

Network namespaces alone are insufficient: restrict filesystem host sockets,
Windows interop, mounts, inherited descriptors, capabilities and namespace escape;
review GPU/driver paths individually. Dedicated unprivileged execution and
descendant supervision require enforceable native tests, not configuration claims.
No global wsl.conf, service/firewall change, launcher installation, deployment or
live/private probe is authorized. Unsupported enforcement denies, with no shared-
daemon fallback. The accepted trusted-host/binary model is not hostile-code/VM
isolation. Preserve original retention, Focus Mode and physical capacity leases.

Native Windows later supplies equivalent authenticated IPC, isolation, lifecycle
and ACL/handle adapters; current POSIX store denies native Windows. Self-contained
packaging is not proof that required OS features exist. Keep protocol, Core
consent/storage and chunk validation reusable; do not retrofit WSL into Core or
claim the separate sandbox backend automatically satisfies private annotation.

Implementation order: bounded inert wire codec; fake-transport lifecycle/admission
with pre-IPC slot burn; separately reviewed supervisor/enforcement and deployment
evidence; separately authorized native synthetic tests (egress/host relay/children,
GPU, crash/cancel/restart, unchanged clients); then exact-attempt private dispatch.
No live smoke is possible from a pure codec. No initial retry/fallback.

Sources reviewed for the design (not installed-host evidence):
- https://man7.org/linux/man-pages/man7/network_namespaces.7.html
- https://man7.org/linux/man-pages/man7/unix.7.html
- https://learn.microsoft.com/en-us/windows/wsl/wsl-config

W1 wire foundation: pipeline/document_job_worker_protocol.py defines strict
64 KiB request/256 KiB result envelopes, closed controls/outcomes and equality
correlation only. No I/O, channel authentication, replay prevention, consent,
worker lifecycle, accepted deployment or application wiring is implemented.
Empty/length completions remain transport data, not extraction quality.

Status: DEDICATED-WORKER DIRECTION ACCEPTED / IMPLEMENTATION SECURITY GATES PENDING, 2026-11-01. This is a proposed implementation sequence, not evidence, permission, a deployment certificate or a public processing control. Selected location: StarFur-Forge WSL. Core assumes a trusted local OS/operator, not hostile-root isolation.

## Accepted worker direction — 2026-11-01

Roger accepted separately managed local annotation orchestration. StarFur owns
documents, fixed retention, chunk selection, checkpoints and explicit recovery;
Ollama receives bounded chunks only. Open WebUI is outside this job path. This
does not replace Ollama or authorize installation, service/configuration changes,
another daemon, automatic background work or concurrent GPU use. A worker is a
lifecycle boundary, not OS isolation. Shared resource admission remains required.

Targeted Astra review recommendations, not implemented evidence:

- Separately type/version server-declared listing identity, exact manifest-byte
  identity and measured blob identities. Never migrate old declarations into proof.
  Supported release decoder/trailing-byte semantics still need explicit fixtures.
- Separate measured executable/dependency/artifact identity from trusted operator
  deployment acceptance. Neither a hash nor version establishes trust. Relevant
  process/configuration/artifact drift invalidates acceptance.
- Public synthetic probes and runner correlation are bounded trusted-host
  observations, not future-behavior proof or network isolation. Post-call checks
  cannot undo disclosure. Require enforceable pre-disclosure checks; unavailable
  measurements deny. Freshness policy remains to be specified, not a magic TTL.
- Future one-use admission binds exact store-owner instance, job/source, attempt,
  deployment and effective settings. Consume before disclosure. Explicitly bounded
  retries may belong to the approved attempt, but initial private processing has
  no model fallback. Restart, uncertain interruption and drift cannot recreate
  consent or renew retention. Storage/inspection consent is not processing consent.

Critical integration fact: `AssistantApplication.bind_annotation_job_runtime()`
captures the ordinary default-session provider; `LoopbackAnnotationProvider` is
disconnected. Verification before that existing binding would not ensure verified
transport dispatch. The future private runtime must bind the exact accepted
transport while preserving Focus Mode, capacity, validation and checkpoint fences.
Do not swap ordinary chat's provider or connect processing by inference.

Next slice requires Sol High: define accepted-deployment identity and the exact
attempt admission/dispatch state machine, retry budget and invalidation. Avoid
more claimed-verification wrappers. Actual evidence producers, consent consumption
and private dispatch remain pending; deployment setup requires separate approval.

**Narrow design decision completed on Sol High:** M1 below may proceed as an
inert byte decoder before the separate trusted-evidence review. This is not
approval of steps 3–7 or a resolution of actual execution/freshness/consent.

## D1 — deployment acceptance and admission contract (design completed 2026-11-01)

This is an implementation contract under a trusted local OS/operator and accepted
provider implementation. It is not remote attestation or a claim to resist hostile
root, same-user injection or a malicious accepted binary. No code implements D1.

### Identity and acceptance

Keep four distinct internal records, none accepted from models, documents or APIs:

1. `ArtifactObservation`: exact trusted root/model mapping, raw manifest SHA-256,
   ordered descriptor digests/sizes and independently streamed blob hashes,
   no-follow file identities before/after reading, decoder policy revision,
   bounded measurement interval and configured hash budget. No source text.
   A server listing digest remains separately named declared metadata; never use
   it as the sole artifact key or equate it to a model blob. Private admission
   must not depend on emulating undocumented decoder read-ahead semantics.
2. `DeploymentAcceptance`: explicit trusted-operator acceptance of a measured
   executable/dependency set and supported release behavior, artifact observation,
   exact endpoint, model, fixed no-relay configuration and transport policy.
   Hash measurement does not itself approve the implementation. No blanket
   acceptance of future versions, mutable aliases, unknown dependencies or models.
   Initially process-local only: restart requires new measurement and acceptance.
3. `LiveDeploymentObservation`: current service/worker and runner identities
   (boot plus PID plus start identity, not PID alone), actual listener ownership,
   accepted executable/dependencies/configuration and exact local model artifacts.
   Independently correlate the connected peer/listener in the same WSL network
   namespace; an earlier socket-owner snapshot alone cannot authenticate a later
   connection. A failed/unsupported peer correlation denies private dispatch.
4. `AttemptAdmission`: opaque controller-issued process-local object, never a
   reconstructible public dataclass capability. Bind exact live store object and
   owner epoch, job/attempt, original source digest and preprocessing revision,
   domain/profile, ordered remaining chunk IDs/content hashes, deployment
   acceptance/revision, immutable effective generation settings and retry budget.
   Public status exposes closed states/counts only, not identity inventories.

Initial runtime evidence is *trusted-deployment local-execution observation*, not
cryptographic execution proof. A separately approved public synthetic probe must
correlate a newly managed worker/runner with accepted artifacts before private
admission. A pre-existing or uncorrelatable cached runner denies. No automatic
unload/restart/probe is authorized by this document. Later reuse is allowed only
within the same accepted process/artifact epoch with fresh per-dispatch checks.
No claim of OS egress isolation follows; that needs separately approved controls.

### Freshness and race limits

Full artifact hashing is an explicit bounded operation at attempt preparation;
never hash multi-gigabyte weights silently per chunk. Hash byte/time limits and
progress/cancellation must be approved in the verifier contract before live use.
Keep verified handles while needed. Revalidate pathname-to-handle identity,
size/link/ownership/stat change indicators before and after dispatch, plus actual
process, listener, configuration and accepted dependency identities. An expired
job, invalid clock, closed owner or changed identity invalidates admission.
Stat equality is a trusted-host change detector, not hostile-writer proof.

There is no reusable `fresh=True`/universal TTL. Observations are single-use inputs
to the next dispatch, acquired within its preflight under controller serialization;
they cannot be saved and later refreshed by changing a timestamp. Policy/capacity
deferral invalidates that preflight: reacquire observations before another explicit
step. A probe is tied to an exact process epoch, never a perpetual local flag.
Pre/post observations do not close adversarial TOCTOU; supporting hostile local
writers would require stronger isolation and a separate policy, not more checks.

### Admission state machine and disclosure boundary

`prepared -> awaiting_confirmation -> active -> completed | fenced`.
`prepared` and confirmation states convey no send authority. Preparation may read
authorized private local storage to build an internal plan; it discloses nothing
to a provider. Storage maintenance/inspection confirmations are not processing
confirmation. Trusted local CLI is the initial approval channel; shared API,
personas, job IDs, source instructions and provider output cannot confirm.

Create the store launch attempt before the exact attempt-bound preview; this is
intent only. Cancel/failure/crash fences that attempt without deleting checkpoints.
Preview identifies the local job and accepted deployment, chunk count, fixed
deadline and maximum calls/bytes; no document body in passive output. Bind an
opaque confirmation challenge to that exact immutable plan and owner instance.
An expired/replaced plan cannot be confirmed by guessing/reusing an ID.

Atomic confirmation consumes that one challenge and creates one active admission;
it is not a reusable grant. Initially budget **one provider call per remaining
chunk, no automatic retry, no model fallback**. A later explicit policy may permit
bounded repair calls, but must re-preview the budget and bind every call. An empty
or invalid response is not success and must not silently trigger another request.

For each explicit step:

1. Under the controller, reserve one exact planned chunk; refuse duplicate or
   concurrent steps. Validate active exact owner/attempt/source/settings/retention.
2. Apply ordinary Focus Mode and shared local/process capacity policy. Private
   work remains background; a second endpoint cannot evade the same physical
   resource budget. Deferral sends nothing and consumes no dispatch budget.
3. Acquire fresh deployment observations and prepare only that bounded chunk's
   request using fixed Core prompt/schema revision. The final transport accepts
   only the controller-issued exact dispatch object, never arbitrary messages
   plus an admission ID. Check rendered-byte/output ceilings before sending.
4. Recheck cancellation/identity and atomically burn the chunk's dispatch slot
   before the first possible Core-to-worker write of private bytes (including IPC,
   not just the downstream HTTP request). Never hold store
   or processor lifecycle locks across provider I/O. Controller cancellation and
   dispatch linearize: cancellation winning first prevents send; dispatch winning
   first means disclosure may already occur. Never claim cancellation undoes it.
5. The sealed direct loopback transport checks its connected peer before body
   write, sends once to the fixed route/model, and never retries/reconnects after
   possible disclosure. After return, recheck all bindings and expiry before the
   existing strict output validation and atomic chunk checkpoint.

Any failure/timeout/interruption after slot burn fences admission; the outcome
may be unknown even if no checkpoint exists. Never restore a burned slot. Already
validated checkpoints survive; explicit resume creates a new attempt and fresh
confirmation for remaining chunks only, within the original retention deadline.
No background loop or durable consent is introduced. On process restart, active
admission disappears and existing store recovery fences unfinished launch intent.

### Existing-interface changes required, not implemented

- `AnnotationJobProcessor.start()` currently creates launch intent and `step()`
  directly calls the injected runtime; neither is consent. A private controller
  must gate the exact processor run and wrap dispatch, not expose these as public
  processing controls. Existing fake-runtime tests retain their explicit test seam.
- `AssistantApplication.annotate_document_chunk()` currently uses default-session
  routing, three attempts and optional fallback. Do not pass the private transport
  through its `annotator=` test seam: that path skips ordinary capacity acquisition.
  Add a production-only exact private runtime assembly sharing Core policy and
  resource leases without overriding the ordinary default provider or its retries.
- `LoopbackAnnotationProvider` currently consumes declarative locality evidence
  and arbitrary allowed messages. Do not synthesize its legacy booleans from D1
  records or claim it enforces admission. Private dispatch needs the sealed
  attempt-aware adapter; keep legacy tests/contracts explicitly non-authoritative.
- No persistence schema change or upgrade of old fingerprints is required for
  process-local admission. If an audit record is added later, keep only bounded
  closed outcome/counts; it cannot resurrect authority or publish private digests.

### Accepted operator policy — 2026-11-01

Roger requires OS-enforced outbound-network blocking covering the private worker
and inference descendants before private dispatch, with native WSL verification.
Trusted-host observations/cloud-disabled settings alone are insufficient. Preserve
LAN/cloud destination denial and ordinary clients. Dedicated orchestration is not
enforcement. No service/firewall/configuration change is authorized. Require
egress blocking for the eventual private worker; permit
provider-free measurement/controller development independently, but do not enable
private dispatch before its backend and native WSL tests exist. Blocking policy
must cover the worker and descendants without disrupting ordinary Ollama clients;
driver/GPU/host-service allowances require explicit review, not blanket access.
The inference process must be inside the enforcement boundary: calling an
unrestricted shared Ollama daemon does not satisfy it. Deny non-loopback IPv4/IPv6,
DNS and relay paths; inherited sockets, Unix sockets, host agents and mounts are
not implicit exceptions. Required local control/GPU paths need narrow reviewed
rules. Unsupported enforcement denies private dispatch. Fake tests validate logic,
not actual kernel enforcement. Backend selection and setup remain separate gates.

### Ordered implementation and acceptance gates

M2: read-only POSIX artifact measurement using the existing manifest codec and
synthetic model trees. It returns observations only, not deployment acceptance or
locality booleans. No live service, probe or private document. Before coding, bound
config decoding, supported layer payload rules, exact root/model mapping, total
hash-byte/time budgets and filesystem ownership policy. Unsupported forms deny.
Sol High remains appropriate for no-follow/race/cancellation handling.

M3: process/dependency/listener observations and explicit operator deployment
acceptance with fake OS evidence; deny unavailable permissions/platforms. Live
read-only inspection and synthetic probes require separately scoped prerequisites.
M4: controller admission and exact-dispatch budget with fake stores/transports;
M5: policy/capacity-preserving private runtime; only then a separately approved
synthetic end-to-end worker smoke. No private-source smoke before all gates pass.

Required future tests: wrong owner/store/attempt/source/preprocessing/settings,
stale or duplicate challenge, concurrent step/cancel ordering, retention during
preflight/response/checkpoint, incomplete/changed artifacts, PID reuse/listener or
connected-peer replacement, cached/unrelated runner, zero-provider refusal,
Focus/capacity deferral with zero calls, one-call budget, burned-slot failure and
no retry/fallback, late output, crash/restart/new consent, redacted progress, and
unchanged ordinary chat/annotation behavior. Tests must assert zero private-byte
transport writes on every pre-disclosure denial, not merely absent checkpoints.

## M1 — implementation-ready pure manifest decoder (no attestation)

Implementation checkpoint: COMPLETED / WSL-VERIFIED, 2026-10-31. The pure codec
and synthetic tests exist; required focused/subsystem suites passed 7/177 tests
(one expected subsystem skip). This completes M1 only. The specification below
is retained as its bounded contract; actual evidence/consent gates remain pending.

Purpose: inspect an already-obtained bounded manifest payload without trusting
it or reading files. This is the concrete prerequisite in step 2, not another
wrapper around claimed verification booleans. The safe ordering deviation lets
independent schema work proceed while measured-evidence design remains gated.

- Proposed ownership: `pipeline/document_job_manifest.py`; tests in
  `tests/test_document_job_manifest.py`. Public entry point takes exactly `bytes`
  and returns immutable, repr-redacted structured descriptors. No filename,
  root, model selector, connection, secret, clock or evidence object is accepted.
- Version the decoder policy separately from any future locality/consent policy.
  Start with the narrow schema-2 Docker distribution manifest layout used by the
  reviewed v0.32.1 source; do not claim general Ollama/OCI compatibility.
- Accept 2..65,536 UTF-8 bytes. Decode one JSON object; duplicate keys,
  non-finite numbers, invalid UTF-8, recursion failure and trailing non-whitespace
  fail content-free. No raw data/exception detail in refusal or representation.
- Exact root keys: `schemaVersion`, `mediaType`, `config`, `layers`.
  Version must be the exact integer 2 (not bool); root media type exactly
  `application/vnd.docker.distribution.manifest.v2+json`.
- Exact descriptor keys: `mediaType`, `digest`, `size`. Digest is lowercase
  `sha256:` plus 64 hex digits; size is an exact positive integer, at most
  64 GiB per descriptor. Config has exact media type
  `application/vnd.docker.container.image.v1+json` and size at most 64 KiB.
- Accept 1..16 ordered layers, exactly one
  `application/vnd.ollama.image.model`. Other allowed layers are only
  `application/vnd.ollama.image.template`, `.params`, and `.license` (each full
  name retains the same `application/vnd.ollama.image` prefix). Config plus all
  layers must total at most 128 GiB. Reject repeated digests across config/layers;
  retain layer order. These are conservative parser ceilings, not hash budgets
  or claims of actual file sizes. More model types require a later policy change.
- Unknown fields, including `from`, `name`, remote hints or executable-looking
  extensions, deny rather than being copied or interpreted. No layer payload,
  template, license text, model configuration or external reference is opened.
- Output: separately named `raw_bytes_sha256` for the exact supplied byte buffer,
  config descriptor, ordered layer descriptors and validated declared total.
  That hash includes whitespace and is NOT the listed server digest by default.
  Do not add an API-digest-equality check, convert `BoundModelDeclaration`, create
  `AnnotationLocalityEvidence`, migrate persisted evidence or emit readiness.
  Validate directly constructible output contracts too; descriptors are data,
  never filesystem paths or capabilities.
- Tests: valid synthetic manifest; raw-byte whitespace sensitivity versus stable
  descriptors; strict key/type/media/digest/size/count/aggregate bounds;
  duplicate digests/keys; missing/multiple model layers; remote/unsupported
  fields; malformed/oversized/deep JSON; immutable/redacted output; actual socket
  creation forbidden. No live manifest, service/model, private source or runtime
  data is needed. No operator smoke is required for this pure slice.
- Required next acceptance: focused codec suite, then annotation-job subsystem
  suite on exact WSL copies. From current 8/10, two successful new required gates
  reach the normal scoped commit/push cadence; do not run extra optional gates
  just for the counter. Full regression only if integration/risk warrants it.

**Later authority-bearing gates remain unresolved:** independently reviewed
executable acceptance is not equivalent to a version endpoint or a measured
hash. Process/runner/artifact evidence must handle caching and replacement;
cloud-disable policy is not OS egress isolation. Choose actual evidence producers
and bounded pre/post revalidation at processing admission, not a magical fresh
boolean/TTL. Exact-job/attempt consent must be consumed before disclosure and
must not survive restart/drift/replay by inference. Missing evidence must deny.
Do not wire any of these based on M1 passing. Targeted review of those choices
remains required; unresolved ambiguities may need Astra or Roger's policy choice.

## Source-grounded identity distinction

The reviewed public v0.32.1 `buildModelListSummary` sets listing digest from `Manifest.Digest()` and size from `Manifest.Size()`. `ParseNamedManifest` derives the digest while decoding manifest bytes; config and layers carry their own blob digests. A listed digest therefore must not be compared directly with the hash of a GGUF weight file. Release source inspection does not attest the installed executable. No live manifest or weight file has been inspected/hashed by this plan.

Sources:
- https://github.com/ollama/ollama/blob/v0.32.1/server/model_list_cache.go
- https://github.com/ollama/ollama/blob/v0.32.1/manifest/manifest.go
- https://github.com/ollama/ollama/blob/v0.32.1/manifest/layer.go
- https://github.com/ollama/ollama/blob/v0.32.1/envconfig/config.go
- https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features

Moving `main` is not a version binding. A version endpoint is only a server declaration. The existing BoundModelDeclaration remains equality data, never local-artifact/execution proof.

## Proposed implementation sequence

1. Define separate manifest-byte identity, referenced-blob identities and measured deployment/attempt evidence. Preserve existing unknown/legacy evidence; do not reinterpret stored fingerprints or the existing locality model_digest silently. A schema/policy change needs explicit review. Keep measured identity separate from trusted administrative acceptance of the executable.
2. Add a pure bounded exact manifest decoder for a deliberately narrow supported release/schema. It consumes already-obtained bytes, rejects duplicate/unknown/remote/unsupported forms, returns only validated digest/size/media descriptors, and never returns system/template/message prose. Matching manifest bytes alone does not verify blobs or local execution.
3. Add a separately opt-in read-only filesystem verifier with exact trusted root/model mapping. It must use no-follow directory-relative regular-file handles, containment/ownership/link checks, bounded manifest/config sizes, explicit total hash-byte/time limits and stable pre/post file identity. Stream blob hashes; do not trust digest-shaped filenames. Reject remote model config and unsupported layers. Do not load a model, download, repair, migrate or scan unrelated files. Large-file hashing is a separately scoped verification cost, not an excuse to infer proof.
4. Add exact actual-server evidence acquisition under trusted operator control: service instance/start identity, installed-executable identity/trust basis, process-owned connected listener and cloud-disabled implementation/policy. Compare before/after acquisition and chunk work; invalidate on service/model/artifact drift and expiry. Never expose environment, logs, paths or raw manifests in public progress. No universal TTL or refreshed boolean is chosen by this draft.
5. Establish local-execution evidence using only a separately authorized public synthetic probe and OS/runtime correlation to the verified artifacts. `/api/ps`, names, loaded-model labels and success text alone are observations, not independent execution attestation. Do not set local_execution_verified just because the server is loopback or cloud-disabled. No private source may be used as a verification probe.
6. Separately design exact-job disclosure consent and one-use explicit processing admission binding the current store owner/attempt, original source identity, exact deployment/artifact/runtime revision and expiry. Storage consent, result inspection, conversation IDs and model prose cannot substitute. Resume/retry/restart/drift must not silently recreate consent or extend retention. Do not put private source text into public evidence objects.
7. Only after review and required deterministic tests plus applicable synthetic live gates connect a trusted local control/runtime. Shared chat/API and background processing remain disconnected until separately authorized. Preserve Focus Mode/capacity, interruption fencing and no verified-remote-stop claim.

## Decisions required before trusted evidence implementation

### Sol review clarification — 2026-10-31 (overall review still pending)

The release source binds the listed digest to bytes consumed by
`json.Decoder(io.TeeReader(...)).Decode`, not an explicit read-to-EOF whole-file
hash. Decoder buffering and trailing bytes/whitespace make unconditional
whole-file equality an unsafe assumption. Define supported encoding/trailing-data
rules and test actual release semantics before binding measured evidence. Retain
a separately named whole-file hash; never silently canonicalize/reinterpret a
declared digest or equate it with a GGUF layer hash. This understood design issue
does not indicate an observed deployment breach. No verifier is approved by this
note; executable trust, execution/freshness and consent questions below remain.

- What exactly should replace or version `AnnotationLocalityEvidence.model_digest` so manifest and blob identities cannot be confused? Existing data must retain its declared-only meaning.
- How will the installed executable be tied to the reviewed implementation under trusted-host assumptions, without pretending a server version string is attestation?
- What measurable local-execution evidence and freshness/revalidation policy is sufficient for this deployment, especially across runner caching and service/artifact changes?
- How is consent bound/consumed at the exact attempt boundary without granting background, replay or cross-job authority?

These are security-contract questions for targeted Astra review, not authority to implement permissive defaults. A non-loopback listening bind alone does not resolve any question above or violate the literal-loopback client-target rule.

## Required future verification, not yet run

For each implemented boundary: strict synthetic codec tests; disposable no-follow/link/path/file-change/hash-limit failures; service/process/target mismatch and restart/drift/expiry tests; pre-disclosure denial; exact-job/attempt consent replay/mismatch tests; late-output fencing and unchanged checkpoint/progress privacy; focused plus required full provider-free WSL regression. Define a minimal public synthetic live gate only when a runtime adapter exists and its authority is scoped. Do not run optional probes merely to reach the ten-test commit threshold.

Current user workflow verification is separate in user.smokes.md. Its CLI fixture success does not satisfy deployment evidence or private-job readiness.
