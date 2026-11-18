# Private annotation deployment verification — review draft

## C8e helper COMPLETED / NATIVE BLOCKED2026-11-18

Focused38 PASS(0.049s), full1,649 OK/one expected skip(26.036s), counter10/10.
Initial fake selector test expected wrong exception type, corrected to ValueError
and rerun without gate inflation. C4/C5 fixture compatibility preserved.
Exact8 coupled Windows/WSL source hashes verified. Read-only preflight acquired
the fixed Linux loader but its SHA256 no longer equals the reviewed bda779...
cec14 pin: assertion STOP before any fixture/unit/native command. Actual new
digest was not logged, so do not invent it. No cause established and no package/
service/config query/change performed. Native approval UNUSED but BLOCKED:
needs read-only current-artifact review and fresh expected-pin acceptance before
execution. Never repin to make a check pass, retry or infer artifact equivalence.
Preparation checkpoint may be locally committed; GitHub push remains held.

Roger approved preparation and, only after successful fake/full/security review,
exactly ONE native attempt. Shared loader helper adds explicit
--lookup-prerequisite and distinct starfur-c8 identity; no C4/C5 rerun.
Fixed generated 8KiB main retains C5 post-exec cwd/fd probes but no search tag;
fixed intermediate libfixture.so needs libfixture-leaf.so with no search tags.
Four sealed-root directories: positive has intended42+leaf7; decoy has decoy13+
leaf7; negative has main only; transitive has main+intended but missing leaf.
Fixed direct loader --inhibit-cache --library-path /<case> --glibc-hwcaps-mask
EMPTY_STRING /<case>/main; no shell/options from caller/model. Expected42/13/
127/127. Six pidfds cover unshare/init/four paused-before-exec canaries.
Existing rootless root/binfmt/socket/cwd guards, FS unshare, fd3 internal decoy,
unit epoch/cgroup/process binding, parent-state checks and exact cleanup remain.
One transient user unit1 CPU/256MiB/no swap/16 tasks/10s+2s grace, existing
controllers only. Exact measured Linux loader bda779ea9e9ad234f60315477d7cfd0bdde861cd8ddd9df8cdaf62f18c4cec14.
No installed vendor/CPU worker, model/GPU, private/Windows data, network workload,
compiler/download/install, config/service or GitHub action. Fixture-only scope
does not prove resident-interpreter SONAME reuse, real CPU compatibility, runtime
dlopen/code closure or descendant-exec enforcement. Native failure retains
fixture, verifies owned cleanup and STOPS, no automatic retry. Native UNUSED.

## C8d declared lookup requirements — COMPLETED / WSL VERIFIED2026-11-18

Recompute exact C8c profile from supplied inventory/forms, then require exact
same-hash SONAME coverage and planned destinations for all declared DT_NEEDED
edges. Fixed resident interpreter role/path/digest is not a regular alias copy;
other providers require /worker/<needed-name> library targets. Return only a
bounded requirements fingerprint/count and unchanged unresolved requirements.
This is not an actual resolution simulator or version/symbol/dlopen/CPU test.
No filesystem, materializer, native/runtime or permission caller. Focused26
PASS(0.016s), full1,645 OK/one expected skip(25.783s), counter8/10.
Real loader reuse, default search and descendant enforcement stay gated.

Next separately scoped step: propose/review synthetic direct-loader/transitive
dependency fixtures and an opt-in helper with existing one-unit resource caps
and exact pidfd/unit/root/cleanup bindings. Before any materialization/execution
approval must specify fixed generated inputs, measured loader digest, allowed
argv/mounts, positive/decoy/missing outcomes, caps and no-retry rules. No helper
or native approval exists yet. Real vendor binaries/model/private input remain
excluded. Do not infer a native grant from the latest general test authorization.

## C8c inert launch profile — COMPLETED / WSL VERIFIED2026-11-18

Roger approved C8b direction for inert contracts only. Pure supplied inventory
and exact per-member search-form fingerprints bind to fixed initial loader argv,
environment and unconditionally unresolved enforcement/compatibility/admission
requirements. Exactly one fixed entrypoint, CPU plugin and resident interpreter,
regular library destinations and no duplicate declared byte copies. Search/raw
digest/role/path/coverage consistency is descriptive, not fresh measurement.
No dependency resolution/SONAME closure claim; that is a separate next checker.
No argv knobs, renderer/model authority, readiness status, I/O, writer, native
unit or runtime caller. Focused22 PASS(0.018s), full1,640 OK/one expected skip
(26.483s), counter6/10; strict C1/C2/C7a
unchanged. User now requests10% five-hour cutoff, local commit at clean stop;
GitHub push held. Actual copying/execution still needs separate precise grant.

## C8b concrete lookup design — REVIEW COMPLETED / DESIGN APPROVED2026-11-18

Roger approved this DESIGN direction only: an explicit measured-loader
invocation and one private library directory, preserving all binary bytes.
No source/test/launcher implementation, copying, image construction, native
unit, actual loader execution, service/config change or private input is approved.
This is a refinement of option3, not a deployed/accepted search policy.

### Proposed final namespace and byte bindings

- One sole interpreter at /lib64/ld-linux-x86-64.so.2. Its observed SONAME may
  satisfy the exact ld-linux-x86-64.so.2 dependency as resident-interpreter
  identity, never by another alias copy. Real loader reuse must be tested.
- /worker/llama-server and /worker/libggml-cpu-x64.so are explicit entry/plugin
  roots. Missing SONAME on the CPU plugin is not an ordinary dependency-alias
  exemption: exact path/hash/role and bounded plugin selection remain required.
- The other12 SONAME-bearing library candidates each get exactly one regular
  file /worker/<SONAME>. Versioned vendor/system source basenames change only
  in a future disposable copy; bytes/digests never change. No symlinks or
  redundant version-name copies. Duplicate providers or target collisions deny.
- All15 candidate digests/identities remain historical observations, not a
  release allowlist. Before any future materialization require independently
  selected/approved pins, fresh whole-set acquisition under aggregate bounds,
  exact copied-byte hashes and final source checks, destination enumeration,
  immutable root seal and remeasurement through the exact launched namespace.
  No claim of cross-run coherence from the current observation receipts.
- /cwd is empty/read-only/lifetime locked with no outside FS-struct sharing.
  /build is absent, not an alternative source. No writable executable aliases,
  outside directory handles, host-root mounts or arbitrary executable extras.
  Any required proc/IPC/input mounts need separate exact exposure rules; do not
  copy C5's diagnostic proc layout into production or call it complete isolation.

### Proposed launch/search semantics (NOT an executable command grant)

Trusted Core would construct a fixed argument vector, never a shell string:
(/lib64/ld-linux-x86-64.so.2, --inhibit-cache, --library-path, /worker,
 --glibc-hwcaps-mask, EMPTY_STRING, /worker/llama-server, ...reviewed arguments).
EMPTY_STRING is a real empty argv element, not an empty search-path component.
No model/user text selects the loader, flags, library path, image or executable.
No --preload/--audit/--inhibit-rpath or caller-selected loader switches. Minimal
explicit environment excludes all ambient LD_*/GLIBC_TUNABLES and credentials.
Direct invocation intentionally changes entry invocation semantics; compatibility
with the pinned runner/plugin path/argv behavior must be verified, never assumed.

Primary glibc source documents direct interpreter invocation and the cache,
library-path and hwcaps options: https://codebrowser.dev/glibc/glibc/elf/dl-usage.c.html .
Lookup source also retains compiled default directories and loaded-object name
reuse: https://codebrowser.dev/glibc/glibc/elf/dl-load.c.html . These sources are
mechanistic context, NOT evidence that our installed interpreter has identical
behavior or that these flags exclude defaults/contain execution by themselves.

Require only exact no-search / DT_RUNPATH=$ORIGIN / the observed byte-exact
mixed DT_RUNPATH on separately pinned members; RPATH/lookalikes/unknown search
forms deny. Unknown other dynamic tags still require separate compatibility/
security coverage; recognizing a form is not accepting the whole ELF object.
The mixed form is preserved, not normalized: /worker is its origin, its build
directory must remain absent, and its empty component sees only immutable /cwd.
Absence of /etc/ld.so.cache, /etc/ld.so.preload and all unplanned executable
members/default-directory/hwcaps alternatives must be verified in the sealed
namespace. Flags supplement this namespace restriction; they do not replace it.
No default-directory file becomes implicitly trusted. Library/code resolution
must resolve to the exact planned bytes or fail, including explicit dlopen paths.

### Separate mandatory enforcement/compatibility gates

1. C1/C2/C7a remain unchanged. Future policy has its own version and descriptive
   contract, not a bypass of strict APIs or conversion of C8a labels to grants.
2. Resident interpreter identity versus DT_NEEDED must be bound distinctly from
   regular aliases. Avoid relying on incidental dependency order or duplicate
   ELF copies to make system libraries load.
3. Loader argv options are initial-process scope, NOT inherited exec policy.
   Before real inference/private input require an enforceable descendant-exec
   boundary or a separately reviewed proof that every allowed exec maintains
   the same namespace/code-resolution restrictions. A supplied boolean, trace
   or statement that the runner normally does not exec cannot satisfy this.
   If this cannot be enforced with unchanged binaries, stop and return the
   conflict to Roger/Astra; no permissive fallback or binary patch is implied.
4. Sealed disk inventory does not prevent anonymous executable mappings,
   memfd/proc-fd alternatives, generated code or malicious existing code.
   Production process/kernel containment and writable-input-to-code boundaries
   remain separate. Neither SONAME closure nor loader flags certify hostile-code
   safety, no-network/private IPC, CPU-only behavior or model-file safety.
5. No GPU/vendor devices/libraries, network fallback, host proxies or shared
   Ollama. No automatic backend/model fallback or repeated effect on uncertainty.
   Actual runtime plugin discovery, optional NSS/locale/config requirements and
   code loads must be bounded and tested; absence must fail safely, not trigger
   host mounts, downloads or broader package copies.

### Small next slices and acceptance gates

- C8c after Roger approves this DESIGN: pure proposed namespace/launch-profile
  contract binding exact image/member/search digests, roles, fixed argv choices
  and closed outstanding requirements. It returns a proposal/fingerprint only,
  never ready/eligible/permission. No image writer or runtime caller. Medium
  can implement this bounded inert contract; escalate unresolved design issues.
- Follow with a separate pure resolution-requirement checker over explicit
  edges/provider roles and destinations, preserving C7a. Reject duplicate/shadow
  copies, misbound resident interpreter, stale/missing digests, unsupported tags,
  build/cwd/cache/hwcaps extras, generic arguments and policy-version mismatch.
- Focused provider-free suite then full regression for each source slice. No
  native smoke needed merely to construct/check proposals. No filler gates.
- Only later, with a fresh exact materialization/execution grant: a test-owned
  sealed-root positive/decoy/missing synthetic gate for direct-loader/system
  dependencies, resident interpreter reuse, immutable cwd and descendant exec
  behavior. Specify caps, inputs/digests, cleanup and one-attempt/retry policy
  before creating a unit. Real binaries and synthetic inference are separate
  later approvals; no private documents before full admission/enforcement.

Decision requested now: approve this fixed-loader/one-directory direction for
inert contract work only, or retain kernel PT_INTERP launch and separately prove
the exact pinned loader's compiled default-directory layout. Recommendation is
the former for explicitness, not because its flags alone are an isolation layer.

## C8a exact search-form review — COMPLETED / WSL VERIFIED2026-11-18

Pure supplied ELF bytes only: distinguish no search, exact DT_RUNPATH=$ORIGIN,
the exact known DT_RUNPATH=$ORIGIN:/build/llama-server-cpu/bin:, and unsupported
forms. RPATH, empty/tag conflicts and lookalikes never normalize into RUNPATH.
Bound raw-file hash plus fingerprint of exact tag/text pairs; return closed
labels, not paths. Unknown other dynamic tags remain unassessed. This is a
precondition for any future exact-policy proposal, NOT that proposal's approval.
No change to C1/C2 denial, C7a subset or search-review categories. No native,
installed-file, image, loader, provider/private or GitHub action. Focused27
PASS(0.012s), full1,634 OK/one expected skip(26.441s), counter4/10.
Next C8b requires Sol High for concrete planned system-directory/loader-default/
mixed-tag policy DESIGN, not automatic acceptance or execution. Specify exact
input hashes/tag forms, interpreter role, complete final namespace, absent
cache/hwcaps/preload/audit/writable aliases, lifetime cwd, source freshness and
runtime-code constraints. Do not expand C7a or turn C8a labels into permission.
Native/real-image scope still requires a distinct precise grant and review.
Windows source edits stay in normal queued workflow;
the renewed testing grant excludes Windows system/unrelated-data effects.

## C7c candidate-source observation — APPROVED / COMPLETED2026-11-17

Roger approved the exact scope below. One read-only terminal acquisition
completed exit0,4,847,192 bytes across five files; root-owned single-link regular
files, anchored non-writable-to-others directories, bounds and final identities
passed. No bytes retained/copied and no code/loader/model executed. Full exact
identity/hash/dependency observation in maintained sprint. Loader digest equals
the prior C5 digest. Not approved deployment pins or immutable image evidence.
CPU plugin has no SONAME and mixed search; that forbids inferring a named alias,
not every explicit plugin role. Runtime plugin loading and source closure remain
unverified. Base library declares libggml-base.so.0 despite versioned basename;
an eventual regular-file destination must match actual requester requirements.

C7c.2 APPROVED / COMPLETED: bounded metadata-only entry/type and readlink
inspection in exactly /usr/local/lib/ollama and /usr/lib/x86_64-linux-gnu, only
basenames in these five observations' DT_NEEDED sets, max32 names/directory and
15s acceptance deadline. Readlink text is descriptive only, never followed;
no traversal to targets, recursive scan, contents/hash reads, copy, execution,
models/network/services/Windows/private data. Report missing/symlink/regular
labels and bounded safe target classification only. This would identify the
next exact regular-file source proposal; it cannot approve those sources.
Observed24 entries for12 names, six same-directory alias strings; final entry/
directory identities unchanged. No links followed or file contents read.
Directory0 vendor: libggml.so.0 -> libggml.so.0.15.3,
libllama-common.so.0 -> libllama-common.so.0.0.1,
libllama.so.0 -> libllama.so.0.0.1, libmtmd.so.0 -> libmtmd.so.0.0.1;
base alias points to already observed libggml-base.so.0.15.3. Directory1 system:
libstdc++.so.6 -> libstdc++.so.6.0.35; libc.so.6,libgcc_s.so.1,libm.so.6,
libpthread.so.0 are regular. These are observations, not trusted alias bindings.

C7c.3 APPROVED / COMPLETED2026-11-18: read/hash/ELF review of exactly nine new
candidate basenames: vendor directory /usr/local/lib/ollama:
libggml.so.0.15.3,libllama-common.so.0.0.1,libllama.so.0.0.1,libmtmd.so.0.0.1;
system directory /usr/lib/x86_64-linux-gnu:
libstdc++.so.6.0.35,libc.so.6,libgcc_s.so.1,libm.so.6,libpthread.so.0.
Same anchored no-follow root-owner/regular/single-link/mode and final identity
checks;64MiB/member,128MiB aggregate,15s acceptance deadline. No recursive
discovery, automatic substitute, link following, copying/loader/execution/
models/network/services/Windows/private files. Refusal/drift stops. This is
candidate observation only, not approved pins, complete closure or a seal.
All nine acquired successfully,15,665,512 bytes; final member/directory
identities unchanged during this run. Exact digest/identity/SONAME/dependency
records in maintained sprint. libggml.so.0.15.3 additionally needs libdl.so.2,
which was not in the approved list and was NOT inspected. The system libraries
have dependencies without origin search tags; C7a remains conservative and
inapplicable to a complete real image, not silently broadened. libc.so.6 also
declares the fixed PT_INTERP; that observation is not an interpreter-role grant.
Separate five/nine-file runs are NOT one fresh coherent snapshot. Any later
measured-image proposal must revalidate its exact full inputs under one budget.

C7c.4 APPROVED / COMPLETED2026-11-18: exact
/usr/lib/x86_64-linux-gnu/libdl.so.2 only, anchored no-follow regular/single-link/
root-owner/mode/final identity checks,64MiB maximum and15s acceptance deadline.
Read hash/bounded ELF metadata only; no symlink following/substitute/discovery,
copy/execution/model/service/network/Windows/private data. Stop on refusal.
This would fill one currently known metadata gap, not certify runtime dlopen
closure, CPU-only behavior, immutable image or private-disclosure authority.
Observed14,408 bytes, SONAME libdl.so.2, needed libc.so.6, no search tag;
all checks and final identities unchanged. No new dependency name appeared.
Cross-run15-file supplied metadata now covers13 distinct DT_NEEDED names with
unique observed SONAME candidates; no unmatched/ambiguous names. This does NOT
prove runtime-loaded closure or a fresh unified snapshot; no approved pins.

NEXT DESIGN GATE: concrete measured sealed-image lookup policy. Current C7a
models a narrow origin-only subset, not the installed system libraries' default
lookup or the CPU plugin's mixed RUNPATH. Define exact planned final regular-file
destinations/aliases, loader-specific default search influences, interpreter
binding, permitted byte-exact tag forms, empty immutable cwd, and absent cache/
preload/audit/hardware-variant/writable-code paths. Preserve C1/C2 and C7a as-is;
do not mutate observations or normalize away search components. Follow with
provider-free contracts/adversarial fixtures before any separately approved
materialization/native test. No additional installed-file reads are needed
merely to summarize current candidate-name coverage. Real image/runtime/dlopen/
CPU/private-disclosure enforcement remains incomplete and separately gated.

Original approved observation scope (consumed/completed, not ongoing discovery):

Next requires explicit installed-source selection. Proposed read-only scope:
exact /usr/local/lib/ollama/{llama-server,libllama-server-impl.so,
libggml-cpu-x64.so,libggml-base.so.0.15.3} and
/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 only. Use anchored no-follow
regular/single-link/root-owned/non-writable-to-others checks; deny any symlink,
change, missing/unsupported input rather than discover substitutes. At most
64MiB/member,128MiB aggregate and15s total acceptance deadline. Output only
redacted identity/digest/count/bounded dependency/search/SONAME observations;
no raw bytes/paths in public diagnostics. Kernel reads cannot be forcibly
cancelled by acceptance deadlines. No loader/ldd/model, link following,
recursive resolution/copy/materialization, network, service/config, Windows
or private-document access. Observation is not approved pins or immutable-image
evidence. Stop on refusal/drift; no substitute file or broader scan by inference.
This completed observation grants no further acquisition, native unit or image permission.

## C7b supplied member/layout binding — COMPLETED / WSL VERIFIED2026-11-17

Pure expected-member pins (logical target, independent caller-selected digest,
byte count, exact source mode and uid) must cover all inventory members once.
Supplied file/search/SONAME observations must match complete metadata and pins,
with no duplicate source inode. C7a checks the resulting proposed layout.
Bounded fingerprint includes source identities; source mode is not destination
mode policy. No I/O, current-file revalidation, handles, copy, seal, authenticity,
live freshness, CPU/deployment or consent authority. Focused27 PASS(0.016s),
full1,627 OK/one expected skip(26.137s), counter2/10.
Next must design explicit exact-source measurement/copy planning before any
materialization; existing C1/C2/mixed-search/native/disclosure gates unchanged.

## C7 review / C7a COMPLETED / WSL VERIFIED2026-11-17

Astra's read-only review found no basis to promote C5/C6 evidence into real
image readiness. Concrete gap: dependency-plan target and matching SONAME do
not prove the requester can reach that file via its own search path. C7a is
the recommended small pure contract, now verified. Inventory targets are
proposed final regular-file destinations; exact assignments cover all edges.
Each dependency must be at requester's parent/name, with matching supplied
hash/SONAME. Only no-search without dependencies or exact DT_RUNPATH=$ORIGIN
is within this provisional subset; RPATH/mixed/default lookup refuse. PT_INTERP
has its own fixed destination; it cannot be treated as an ordinary alias.
Reserved runtime/build destinations and duplicate declared byte copies refuse.
Result says internally_consistent_proposed_layout, never safe_to_execute.
Focused35 PASS(0.024s), full1,620 OK/one expected skip(27.724s), counter9/10.
Synthetic positive/transitive/fixed-interpreter and wrong-directory, missing/
different identity, borrowed ancestor path, mixed/RPATH, decoy/duplicate and
malformed/coverage cases passed. No filesystem or runtime caller.
Next C7b may define a disconnected acquired-member/layout binding contract:
exact current file observations and expected independent digests, sizes, modes
and destinations under aggregate bounds. It must not claim an immutable root
from stat metadata, copy files, select installed sources, accept mixed paths or
emit deployment readiness. Materialization still needs the fresh scope below.

Reviewed next requirements: independently pinned source digests; bounded
no-follow copy-in with streamed actual-byte hashes/source identity checks;
complete destination enumeration, modes and hashes; lifetime immutable seal
then remeasure through the exact launched root, excluding outside handles and
writable aliases. Exact RUNPATH bytes/tag/digest must be separately reviewed,
not accepted by mixed_or_unsupported category. No ambient cache/preload/audit/
environment/default/hwcaps influence; actual dlopen/CPU selection needs both
enforcement and bounded observed tests. Trace success is not enforcement.
Fresh explicit exact-input/digest/destination/limit/cleanup approval required
before test-image materialization; copy approval never implies execution.
Later real-binary/synthetic-input execution needs a separate precise grant;
neither grant implies private-input disclosure. Existing C1/C2 stay unchanged.
ABI reference: https://gabi.xinuos.com/elf/08-dynamic.html .

## C7 real-image execution/design gate — STILL PENDING2026-11-17

Pause before production-path acceptance, real-image construction or another
native unit. C5 approval is consumed; synthetic loader/cwd evidence and C6
descriptive hash/SONAME matches do not resolve these security questions:

- Define the exact immutable image/copy-in contract, independently anchored
  acquired source bytes, final source/target remeasurement and lifetime seal.
  Resolve regular-file alias materialization without following vendor symlinks
  or copying directories; prohibit extra/unmeasured members and outside handles.
- Decide exact SONAME requirements for aliases, including missing labels or
  interpreter exceptions. Default deny; never infer identity from basenames,
  supplied sidecars or all-match review labels. Keep C1/C2 denial until a
  distinct reviewed policy is explicitly accepted, not by changing strict APIs.
- Specify exact preserved RUNPATH cases and how unreachable build paths and
  empty components remain controlled for the whole lifetime. Exclude ambient
  cache/preload/audit/environment/default/hardware-variant lookup influence;
  a fixed two-library canary is not general loader-behavior coverage.
- Bound actual runner/plugin runtime dlopen and CPU/hardware-library selection;
  static DT_NEEDED and SONAME equality are not complete closure or CPU-only proof.
- Recommend the smallest next pure contract and adversarial fixtures, separating
  declarations, measured bytes, immutable enforcement, observed loading and
  private disclosure authority. List exact fresh approval needed before any
  materialization/real-library/native test. No setup/service/config/model/
  Windows/private-input/network change is authorized by this review request.

This is a narrow follow-up to C3's accepted option3 design, not a broad audit,
new strategy choice or added gate for the Murr apartment. Focused higher-security
review is needed before resolving these policy/implementation boundaries;
Sol must not turn current descriptive observations into loading permission.

## C6c declared alias comparison — COMPLETED / WSL VERIFIED2026-11-17

Compare one explicit dependency plan against exactly one same-declared-hash
SONAME observation per alias-provider target. No missing/extra/duplicate sidecar;
exact case-sensitive matches, differs or absent outcomes are review labels only.
No basename guessing, filesystem/link creation, source discovery or runtime
caller. Even all-match output proves neither trusted/immutable backing nor
dynamic resolution/version compatibility/dlopen closure/CPU/private eligibility.
Focused33 PASS(0.021s), full1,609 OK/one expected skip(27.183s), counter7/10.

## C6b same-acquisition identity review — COMPLETED / WSL VERIFIED2026-11-17

Explicit review_worker_elf_identity_file returns dependency/search/SONAME
observations from one bounded exact-file acquisition and parse, with equal
raw digests. Strict and earlier search-only contracts remain unchanged. Final
entry/handle/directory identities and deadline cover parsing; interruption
closes owned handles without closing the caller's trusted directory fd.
No arbitrary root selection, second-file identity inference, alias assignment,
loader/image/CPU acceptance or runtime caller. Test-owned synthetic files only;
focused40 PASS(0.021s), full1,602 OK/one expected skip(27.194s), counter5/10.

## C6a SONAME observation — COMPLETED / WSL VERIFIED2026-11-17

Small next dependency from C3's explicit alias/SONAME requirement: parse supplied
ELF bytes only, at most one bounded DT_SONAME and same-byte hash. No tag means
None, not a filename or identity inferred from DT_NEEDED. Duplicates (including
identical/empty), malformed offsets/tables/strings and path-bearing labels deny.
Existing search review and strict C1/C2 return contracts preserved. This new
review can describe SONAME alongside search tags without accepting either.
No file reader, alias-plan producer, image materializer, native loader, provider,
admission or private-input caller. Focused59 PASS(0.029s), full1,593 OK/one
expected skip(27.174s), counter3/10. Next explicit same-acquisition reader
composition must retain final identity/deadline/owned-handle checks.
Next actual alias comparison still needs explicit same-byte inventory binding;
measured image/runtime resolution/dlopen/CPU remain separate gates.

## C5 NATIVE WSL PASS2026-11-17 — approval consumed

One explicit attempt exit0, no retry: valid-directory cwd EPERM probes held
in parent/fork/post-exec canary; exact mixed-path intended42/missing127 with
decoy13. Process/pidfd/unit/epoch/cgroup/resource bindings, sealed root/private
registry/socket controls, captured exits and complete fixture/unit/cgroup cleanup
passed; parent state unchanged. Reviewed coupled hashes in maintained sprint.
No installed plugin/model/GPU, Windows/private input, host network or existing
service changes. Fixture-level evidence only; C1/C2 still deny every search tag.
Full immutable image/SONAME/dlopen/actual CPU/private disclosure remain gated.
Helper backed up in ddf2cbd before execution; result records later/unbacked.
New cycle1/10. No extra native unit is authorized.

## C5b helper COMPLETED / WSL VERIFIED2026-11-17 — native passed above

Roger approved fresh C5 scope: prepare/test/review, then exactly one c5 unit
with unchanged C4 resource/cleanup/fixture limits. Explicit --cwd-prerequisite,
fresh c5 unit identity, no implicit C4 repeat. Native approval now consumed.
Before root detachment, verify exact x86-64 syscall/CLONE_FS header values.
After sealing root/drop caps but before installing guard/fork: require one
thread and successful unshare(CLONE_FS), ensuring no prior external FS sharing.
Base guard/root checks run, then chdir to empty read-only /cwd and install C5
guard. Parent and each forked canary issue valid-directory chdir/fchdir probes;
must get EPERM and unchanged cwd identity. Exec retains only fd3 pointing to
internal /decoy. Fixed ELF fstats fd3 as a directory, directly attempts chdir80/
fchdir81, requires raw -EPERM, gets/checks exact /cwd, then returns fixture value.
Positive42 and missing127 despite decoy13 use the exact fixed mixed RUNPATH.
No installed plugin or model is executed; pure tests cannot attest enforcement.
Focused44 PASS(0.083s), full1,584 OK/one expected skip(29.402s); cycle11 gates.
These gates precede source/hash review, scoped backup and one native attempt.
C4 fixture bytes remain identical by golden-hash assertions to the earlier native
checkpoint. Strict C1/C2 denial and all production/dlopen/private gates remain.
Command only after verification with measured exact loader SHA:
`/usr/bin/timeout --signal=TERM --kill-after=2s 40s .venv/bin/python -I -B -S scripts/private_worker_loader_smoke.py --expect-loader <sha256> --cwd-prerequisite`

## C5a inert cwd restriction — COMPLETED / WSL VERIFIED2026-11-16

Pure cBPF construction reloads syscall number at prior common ALLOW tail and
adds x86-64 chdir80/fchdir81 EPERM. Existing arch/x32/socket/namespace/clone
behavior preserved; unknown calls still allow. No installer/header reader or
runtime caller. This is not a production allowlist or evidence cwd is locked.
It cannot attest initial empty immutable cwd, outside FS-sharing exclusion,
kernel installation, fork/exec inheritance or complete library resolution.
Focused18 PASS(0.036s), full1,575 OK/one expected skip(25.854s), cycle9/10.
No native C5 approval existed at C5a; C5b approval above supersedes that status.
Bytecode interpretation is not native enforcement.
Rationale: C4 exact $ORIGIN tests do not cover the installed trailing-empty
search entry. Future separately approved C5 must bind fresh private-root/FS/
one-thread setup, immutable cwd and actual deny probes across descendants/exec;
then a fixed mixed-path synthetic fixture. No installed plugin execution or
acceptance by name, no silent widening of current C1/C2 policy.

## C4 NATIVE WSL PASS2026-11-16 — approval consumed

Single explicit attempt exit0. Helper coupled hashes/argv checked before exec;
source83ead1a1e50327fcb770d7260164025f103fb371595bfa114eec8f7d08f395af.
Expected loader bda779ea9e9ad234f60315477d7cfd0bdde861cd8ddd9df8cdaf62f18c4cec14,
254864 bytes. Observed intended42/missing127 with decoy13. Native assertions
verified exact unit epoch/MainPID/uid/cmdline/cgroup, kernel caps, namespace init/
canary pidfds before release, read-only root/private registry/inherited socket
guard, all exits, unit/cgroup/known fixture cleanup and unchanged parent state.
No failed fixture or lingering C4 unit/process. No retry/new unit approved.
No real model/GPU/private input/Windows access or shared-service change.
This does not attest real CPU libraries, mixed/empty search-path behavior,
complete dlopen closure or production policy. Next pure cwd-lock primitive
addresses Astra's lifetime-cwd prerequisite; native C5 remains separately gated.

## C4b helper COMPLETED / WSL VERIFIED — NATIVE PASSED ABOVE2026-11-16

Exactly one UUID-named temporary user unit under existing root user-slice,
R0 properties unchanged. Empty worker environment and null stdio. Supervisor
pins exact invocation/MainPID/cmdline/uid/cgroup before go; nested unshare init
and two canary children captured before root/exec release. Fixed Linux loader
source acquired no-follow/root-owned/single-link/same-device with2MiB/2s bounds,
pre/post identity and strict metadata; no dynamic discovery or arbitrary binary.
Only its hash-matched copy and generated ELF fixtures enter private4MiB tmpfs.
Private read-only empty binfmt registry, old-root detach, read-only seal, handle
closure, cap drop and inherited synthetic socket/syscall guard precede exec.
Positive exact $ORIGIN chooses42 despite decoy cwd; negative missing dependency
must exit127 rather than decoy13. This tests that exact fixture/loader only.
All pidfds/Popen, unit/cgroup/known fixture cleanup and unchanged parent registry/
controllers must be verified. Failures retain fixture; no native retry implied.
Final17 fake PASS(0.009s); full1,567 OK/one expected skip(25.794s), counter6/10.
Exact expected loader digest is required and checked before fixture/unit creation.
Final source/argv/lifecycle review covered fixed paths, sanitized environment,
caps, captured processes before release, failure teardown, phase-only diagnostics
and exact cleanup. Earlier15/1,565 runs preceded diagnostic hardening; reruns
do not inflate cadence. Single native attempt passed above; approval consumed.
Command only after exact copy/hash verification:
`/usr/bin/timeout --signal=TERM --kill-after=2s 40s .venv/bin/python -I -B -S scripts/private_worker_loader_smoke.py --expect-loader <exact-preflight-SHA256>`
The expected hash is mandatory and rechecked before fixture/unit creation; no
environment/default artifact selection. Read-only preflight measured254864 bytes,
SHA256 bda779ea9e9ad234f60315477d7cfd0bdde861cd8ddd9df8cdaf62f18c4cec14.

## C4a fixture foundation — COMPLETED / WSL VERIFIED2026-11-16

Roger approved C4 scope below, including one bounded synthetic native unit after
helper preparation/tests/review. At preparation, native approval was unused;
the single attempt subsequently passed above. Fixed ELF main
references one data symbol through a GLOB_DAT relocation; intended DSO contains
42, decoy13. No libc/constructor/arbitrary-code selector/compiler. Pure structural
tests are not live loader validation. Main uses exact $ORIGIN; mixed installed
CPU path remains denied. Installed readelf -h/-d observation of the exact Linux
interpreter (no execution) found GNU OSABI3/ABI0. Metadata inspector policyv2
supports only System-V/GNU ABI0; does not accept an interpreter or deployment.
21 focused PASS(0.004s), full1,557 OK/one expected skip(26.206s); cycle4/10.
At that fixture-only checkpoint no image/unit/loader had started. Later C4
native PASS and consumed approval are recorded above; no real worker deployed.

## C3d explicit review acquisition — COMPLETED / WSL VERIFIED2026-11-16

One caller-trusted directory fd/exact basename, no discovery. Strict inspect
entry stays unchanged and denies all search tags; separate review composes the
shared parser/classifier over identical acquired bytes before final identity/
expiry checks. Review may describe unsupported searches, never accept them.
Immutable file/search hashes must match; no raw paths/payload returned. Trusted
host observations, not hostile-host protection or accepted image provenance.
44 focused PASS(0.017s); full1,549 OK/one expected skip(25.232s); cycle2/10.
No actual installed files accessed; no native/image approval consumed.
Next native/image gate is NOT authorized here: review concrete helper, exact
artifacts, synthetic-only positive/decoy behavior, resource limits and cleanup
first; get separately scoped operator authorization before constructing/running
a reference image or creating another transient unit. R0 approval is consumed.
Do not infer full dlopen/CPU/security readiness from a loader canary pass.

Roger approved C4 on2026-11-16: prepare/review one explicit opt-in
synthetic loader helper, fake tests first, then exactly one temporary user-owned
managed unit with existing controllers only.1 CPU/256MiB/no swap/16 tasks/10s
runtime+2s kill grace. Test-owned generated ELF fixtures and one exact measured
Linux interpreter copied into a sealed fixture root; positive intended-library
and negative missing/decoy cases only. Reuse reviewed namespace/root/binfmt/
identity controls, no host network/Windows data/executables/private input,
Ollama/model/GPU, compiler/download/install or shared-service change. Exact
invocation/descendant membership/exit and unit/cgroup/fixture cleanup required;
stop on uncertainty, no repeat by inference. This is loader prerequisite
evidence only; loader/environment/search-policy completeness stays gated.

## C3c explicit declared assignment — COMPLETED / WSL VERIFIED2026-11-16

Supplied aliases (max128) name exact inventory targets; no host lookup, links,
normalization or loader resolution. Every declared needed label must map once
to a declared shared-object library/interpreter; exact fixed interpreter target
required when PT_INTERP is present. No recursive interpreter or unreachable
libraries. Explicit plugin roots are descriptive, not proof they will load.
Cycles are bounded by finite inventory traversal. Fingerprint binds declarations,
not actual SONAMEs/loader behavior or accepted image. C1/C2 denial unchanged.
Three required gates before completion: focused pure graph validation; composed
temporary-file acquisition/inventory/assignment seam including C2 refusal; full
regression PASS:8 focused(0.003s),2 integration(0.001s),full1,541 OK/one expected
skip(26.094s). Ten-gate scoped backup verified cb7883d771cd2648742e07b3205797970d429946;
new cycle0/10. No real library loaded, image or worker/unit launched.

## C3b proposed inventory — COMPLETED / WSL VERIFIED2026-11-16

Pure declarations only:1..64 immutable regular-file target descriptions, one
declared entrypoint,64MiB/member and256MiB aggregate. Logical POSIX components
reject traversal/host syntax, case collisions and file/directory prefix conflict.
Same raw hash binds supplied ELF/search metadata; sorted fingerprint commits
to declarations, never independently observed files or exact loading behavior.
Search classifications (including unsupported) remain descriptive, not accepted.
No file acquisition, alias resolution, dependency closure, CPU attestation,
materialization, sealed image, loading or public runtime caller.9 focused PASS
(0.009s), full1,531 OK/one expected skip(25.911s). Counter7/10. Next explicit
logical alias/dependency assignment; not an actual loader search simulation.

## C3 Astra review2026-11-16 — C3a COMPLETED / WSL VERIFIED

Review supports unchanged binaries only under a separately proved measured,
immutable image. Exact $ORIGIN is metadata, not eligibility. Installed mixed
RUNPATH stays denied: empty components require lifetime cwd restrictions, not
startup-only chdir; build paths cannot become reachable. Pin loader/runner/
plugin/aliases/digests; exclude ambient cache/preload/audit/environment/default/
hardware-variant paths and cover dlopen/descendants. Existing root/binfmt/
resource/syscall fixture passes are not loader evidence. C3a is supplied-byte
classification only;36 focused PASS(0.026s), full1,522 OK/one expected skip
(25.865s). Counter5/10; no new native/execution/image authority. Search strings
are parsed with zero DT_NEEDED too; no path normalization or raw path return.
Next: bounded explicit image inventory contract, not deployment promotion.
Before launch, separately authorized positive/decoy loader smokes remain gated.
References: https://codebrowser.dev/glibc/glibc/elf/dl-load.c.html#468
and https://gabi.xinuos.com/elf/08-dynamic.html . Review ran no workers/tests.

## C3 strategy selected2026-11-16 — detailed review above; execution pending

Roger chose option3: preserve binary bytes and use narrowly controlled library
resolution within a sealed image. Selection is COMPLETED as a design choice,
not proof or approval of the loading policy, image construction or execution.
Do not transform installed/disposable binaries or obtain alternative artifacts
under this selection. Existing C1/C2 denial stays intact until a specific
reviewed policy is accepted and verified. No source/runtime behavior changed.

Read-only installed `readelf -d` inspection (exit0, no ELF execution) found:
- `/usr/local/lib/ollama/libggml-cpu-x64.so`: DT_RUNPATH
  `$ORIGIN:/build/llama-server-cpu/bin:` (includes an empty search component).
- `/usr/local/lib/ollama/libggml-base.so.0.15.3`, `llama-server` and
  `libllama-server-impl.so` under that same directory: DT_RUNPATH `$ORIGIN`.
- Bounded directory-name/type inspection also found versioned library symlinks
  and separate CUDA/Vulkan directories; none was copied, followed or loaded.

Observed fact: C1 `inspect_worker_elf()` rejects every RPATH/RUNPATH, including
empty values, and C2 composes that unchanged policy. Inference: these installed
CPU-side artifacts cannot currently supply an accepted sealed image. Static
DT_NEEDED completeness would still not establish runtime dlopen closure or
CPU-only behavior. No native execution/security boundary failed in this check.

Do not silently permit `$ORIGIN`, drop the trailing empty component, use an
ambient LD_LIBRARY_PATH, edit installed binaries, copy vendor directories or
call a declaration-only image plan deployment evidence. C3 source not started.
The earlier alternatives were a separately measured sanitized disposable copy,
a separately approved suitable artifact, or a narrowly proved sealed-image
loader policy. Roger selected the latter; the first two are not authorized.
Review must specify exact permitted resolution, immutable measured inventory,
alias/SONAME binding, loader/environment/cache/default-directory behavior,
cwd handling and runtime-loaded modules. Empty/build-directory entries cannot
be dismissed or treated as `$ORIGIN` by normalization. If preserving the installed
bytes cannot satisfy a proved sealed policy, refuse and return the conflict to
Roger rather than switching strategy or broadening search paths silently.

Recommended Astra review scope: inspect C1/C2, the accepted restricted-root,
binfmt/syscall/resource evidence and exact metadata above; recommend the smallest
safe option3 image/search/alias contract, feasibility and deterministic tests.
Read-only review only;
no runtime/config/package changes, model calls, units or execution. Preserve
default search-path denial until a specific design is accepted. Sol then
implements the agreed provider-free slice. This is a worker integration gate,
not an added dependency for the basic Murr apartment.

## C2 exact ELF-file observation — COMPLETED / WSL VERIFIED2026-11-15

Provider-free focused14 PASS; full1,513 OK/one expected skip(25.307s).
Cycle3/10; exact source copy verified, completion records pending next backup.

Read one explicit basename under a caller-trusted POSIX directory handle, never
discover an installed root or follow package aliases. Require exact owner and
regular single-link same-device file, no group/other writes or special mode
bits; enforce64MiB maximum and supplied byte/time acceptance bounds. Recheck
fd/entry/directory identity after parsing; return immutable dependency/stat
metadata only. Preserve caller fd, close owned fds on refusal/interruption and
refuse success after uncertain cleanup. Deadlines fence acceptance, not blocked
kernel read cancellation; this is trusted-host measurement, not isolation.
No actual installed artifact, copy/materialization, launch, service, GPU/model
or private input in the first tests. Package symlink/alias handling and complete
DT_NEEDED/dlopen closure remain separate reviewed image-plan responsibilities.

Foreground note: reported Fortnite disruption during development remains an
unresolved manual acceptance failure. R0 did not cap the whole development
workflow. Avoid attributing cause or claiming a performance fix without measured
correlation and operator-owned frame-time validation.

## R0 scoped resource-unit gate — COMPLETED / NATIVE WSL PASS2026-11-15

Single authorized native attempt exited0 with explicit PASS: kernel caps,
worker/fork-child identity and cgroup membership, observed Result=timeout,
both process exits, unit/cgroup disappearance, known fixture cleanup and unchanged
root/app controller snapshots. No retries/new units. No model/private input/GPU,
Windows data, network workload or existing-service changes. Not hostile-code
isolation, exhaustion/performance or private-disclosure evidence. Native gate
adds one after verified ten-gate backup a08a9f0, current counter1/10.
Image/dependency closure and production deny-by-default policy remain gated.

Helper foundation COMPLETED / WSL VERIFIED:10 focused tests and full1,499 OK/
one expected skip. These are provider-free/fake checks; no unit/cgroup created.
Separately approved one-unit native gate passed after verified backup.

Roger approved the previously proposed one-unit synthetic gate. Exact helper:
scripts/private_worker_resource_smoke.py; never normal regression discovery.
Use root of the existing user manager (-.slice), not app.slice: read-only native
preflight found cpu/memory/pids already enabled at root, but app.slice children
only memory/pids. Refuse missing root controls instead of enabling any ancestor.
Snapshot root/app controllers before/after. This placement stays inside the
approved user-owned unit; no system unit, install/enable, sudo or persistent config.

One UUID-named --collect Type=exec unit, explicit empty worker environment via
trusted env -i, NoNewPrivileges=yes, null stdin/stdout/stderr, no network/model/
GPU/Windows access. Kernel cpu.max must be100000/100000, memory.max268435456,
memory.swap.max0,pids.max16. RuntimeMax10s,TimeoutStop2s,KillModecontrol-group,
SendSIGKILLyes,Restartno. Bind exact invocation ID/MainPID, pidfd/start time,
command line, UID/no-new-privs and kernel cgroup before fixture-file release.
One fork child must be pinned in that exact cgroup, then both wait with SIGTERM
ignored to exercise kill grace. Observe Result=timeout before collection,
both pidfd exits, unit/cgroup disappearance and unchanged parent controllers.
Remove only known test-owned fixture entries on success; preserve failed fixture.
An early failure can stop only the captured exact invocation, never an unknown
unit by name. No automatic retry on permission/security/cleanup uncertainty.

The 40s+2s outer watchdog is not a unit limit; the unit always has10s+2s.
This tests real configured resource controls, descendant membership and timeout
kill, NOT hostile-code isolation, adversarial exhaustion, model execution or
private-data admission. Other private worker gates remain. No default caller.
References reviewed: systemd-run, systemd.resource-control and systemd.service
official manpages; installed systemd259 help/version inspected read-only.

## CPU-only reference preparation — 2026-11-11

C1 COMPLETED / WSL VERIFIED:13 focused tests, full1,489 OK/one expected skip.
Diagnostic read-only installed-file inspection matches prior readelf metadata
(six direct dependencies), without executing Ollama. Initial narrow SONAME rule
denied the fixed loader dependency name; exact ld-linux-x86-64.so.2 compatibility
added and tested without accepting arbitrary loaders. Not dependency closure or
runtime validation. Corrective reruns do not add extra required-run counts.

Roger approved CPU-only disposable synthetic-input integration direction after
N2b.2a/2b. This supersedes the pending CPU-versus-GPU choice below, not the
remaining enforcement/launch gates. No GPU, download, shared-service change or
private input. Local read-only inspection (no Ollama invocation) found a Linux
x86-64 dynamically linked binary, CPU libraries alongside separate vendor
directories, and conventional installed model-manifest metadata. Do not copy
whole /usr, vendor directories, home directories or default host configuration.
Package library aliases require exact reviewed target/byte binding and image
materialization rules, not permission to follow arbitrary symlinks.

New pure document_job_worker_elf.py accepts supplied bounded ELF64/x86-64 bytes
and derives the fixed loader plus direct DT_NEEDED labels. No file acquisition,
ldd/loader execution, recursive resolution, dlopen closure, CPU attestation,
production ELF validity or launch authority. Unknown dynamic metadata is not
certified safe; any RPATH/RUNPATH denies. Native image inventory/closure stays
separate. Reference format definitions:
- https://gabi.xinuos.com/elf/02-eheader.html
- https://gabi.xinuos.com/elf/07-pheader.html
- https://gabi.xinuos.com/elf/08-dynamic.html

Resource prerequisite: current WSL shell is in a non-writable /non-systemd
cgroup. User manager and app.slice delegation already exist and are writable;
no configuration was changed or unit started. Do not try to migrate across
non-writable common ancestors or weaken limits. Proposed separately approved
next scope: one temporary user-owned managed unit launching only a synthetic
canary initially, enforce aggregate CPU/RAM/swap/task/wall limits, process-tree
kill and cleanup, no enable/install/persistence or existing-service change.
Keep credentials/ambient environments and raw output out of the unit/journal;
review exact executable, channel, property and lifecycle handling before use.
Actual Ollama/runner integration follows only after those limits and sealed
image/deny-by-default policy are demonstrated. No real inference launched yet.

Proposed R0 approval scope (not yet approved/run): one uniquely named temporary
user-owned managed unit, no sudo/install/enable/persistent configuration, synthetic
canary only, no model, GPU, Windows access or network connection. Cap one logical
CPU,256MiB RAM,zero swap,16 tasks,10-second runtime and2-second kill grace.
Capture/check exact unit/cgroup ownership and kernel limits before releasing any
bounded workload; validate descendant membership/kill and exact collection/cleanup.
No raw stdout/stderr to journal; sanitize test environment. Inspect the exact
helper/argv/properties before native use. If controller/delegation or any limit
is unavailable, deny; do not change existing services or relax limits. Separate
real CPU model inference would use separately reviewed limits/image/policy.

## Targeted Astra N2b.2 review — 2026-11-11

### N2b.2b synthetic inherited guard — COMPLETED / NATIVE WSL PASS

2026-11-11:25 focused tests(0.017s), native gate exit0(about0.82s), full1,476
OK/one expected skip(25.744s). Worker/child host-family socket-creation denial,
harmless namespace-call denial, fixed Linux exec and exact teardown passed.
No actual Windows, inference/GPU or complete production-policy proof added.

Exact fixture mode --syscall-prerequisite reuses N2b.2a root/registry/canary and
55s+2s watchdog. It installs one-thread/no-new-privileges x86-64 cBPF after root
sealing and capability drop, before fork. Header numbers are checked before
old-root detachment; reject foreign/x32 ABIs. Deny non-INET socket creation and
all new socketpairs, namespace/mount mutation, execveat, ptrace, process_vm,
pidfd_getfd, handle-open, bpf/perf and io_uring. Clone namespace flags deny;
clone3 returns ENOSYS for conventional clone fallback. Ordinary reviewed execve
and fixed Linux ELF remain allowed. No path-string seccomp filtering claimed.
Worker/child test AF_UNIX/AF_NETLINK/AF_VSOCK creation returns EPERM, private
INET socket creation succeeds without bind/connect, and harmless unshare(0)
is denied. Child then execs the same fixed exit42 canary. No host address,
Windows execution, relay, GPU/model or private data is probed. Parent registry,
mount/canary and exact process/fixture teardown must remain verified.

CRITICAL: this is a limited synthetic guard, not a production allowlist.
Unlisted/unknown syscalls still allow; tests explicitly retain that fact. No
private processing may rely on it as complete enforcement. Production syscall
surface, actual immutable executable/library inventory, drivers and all real
inference descendants remain separately reviewed/measured gates. No automatic
promotion, install/startup/application wiring or unsupported-platform fallback.

Next real integration scope requires Roger's decision/approval: recommend
CPU-only, synthetic input first to separate runner/process containment from
GPU/device/driver authority. GPU access would require a separate device surface
and performance validation. Neither option is authorized by the synthetic gates.
Before any real launch, review immutable binary/library/model inventory and a
deny-by-default production syscall policy; the permissive primitive above must
not be silently promoted. No ordinary shared Ollama/service reconfiguration.

### N2b.2a exact prerequisite scope — COMPLETED / NATIVE WSL PASS

2026-11-11:15 focused fake tests, native prerequisite exit0 (about0.70s),
full1,466 OK/one expected skip. Separate empty read-only registry, sealed root,
Linux ELF exit42 and unchanged parent/process/fixture cleanup verified. No
syscall/socket guard, Windows/real relay or actual inference proof added.

Opt-in root helper --binfmt-prerequisite runs as roger in one fresh Linux /tmp
fixture with the existing55s+2s watchdog. Parent reads bounded existing binfmt
status/entry observations (never register), requiring enabled status. Worker
creates a fresh binfmt_misc filesystem in its new user namespace, at /formats
inside the private fixture root, read-only/nosuid/nodev/noexec. Refuse same
filesystem device as the inherited registry, any interpreter entry, unavailable
status or mount failure. No registration/status writes or global mount change.
Seal private tmpfs root read-only after detaching old root; assert EROFS for a
synthetic create. Test child revalidates root/registry, then execs fixed132-byte
x86-64 Linux ELF containing only exit(42), no loader, network or user arguments.
Supervisor pins child before release and verifies expected exit; parent checks
unchanged registry/mounts/canary and exact process/known-fixture cleanup.
No MZ/Windows canary, /init call, real relay, provider/GPU or private source.
Any primitive failure stops; never fall back to inherited registry or change
host settings. This gate demonstrates an empty instance and Linux execution,
not actual Windows denial, runner compatibility or full N2b.2 enforcement.
Kernel-version text alone is not a pass. Separate syscall/socket, namespace
mutation and descriptor/alternative-path controls remain next dependencies.

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
