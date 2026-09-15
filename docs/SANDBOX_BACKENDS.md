# StarFur sandbox backend readiness

## Current status

StarFur has no executable sandbox backend. `sandbox.run` remains denied by
default. The current Hyper-V work is a read-only prerequisite inspector and a
non-executable reference profile; neither one creates authority or proves that
hostile code can be contained.

An explicit local inspection can be run from the repository root with:

```bash
python -m pipeline.sandbox_hyperv
```

Importing the module, opening the apartment, reading diagnostics, or starting
StarFur never runs this inspection. The command performs one fixed WMI/CIM query
through the conventional Windows-owned `powershell.exe`. It does not request
elevation, enable or disable Windows features, enumerate VMs, start services,
download an image, create a switch, change firmware, or launch a guest.

The output deliberately separates:

- `Host prerequisites`: whether the bounded facts appear compatible with the
  currently documented Hyper-V host prerequisites.
- `Execution backend`: always `unavailable` in B7 because the image, transport,
  supervisor enrollment, isolation conformance, and execution integration do
  not exist yet.

A successful host check must never be converted into a tool grant, approval,
backend observation, or executable broker selection.

## Verified platform baseline

Microsoft currently documents client Hyper-V for Windows 10/11 Pro and
Enterprise, not Home. The documented hardware baseline includes a 64-bit CPU
with second-level address translation (SLAT), VM Monitor Mode extensions,
firmware-enabled hardware virtualization, hardware-enforced DEP, and enough RAM
for the host and guests. Microsoft recommends `systeminfo.exe` as a manual
requirements check. Hyper-V is an optional Windows feature; enabling it is a
separate administrative operation and can require a restart. StarFur B7 never
performs that operation.

Primary references, checked 2026-09-11:

- [Hyper-V system requirements](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/host-hardware-requirements)
- [Install Hyper-V](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/get-started/install-hyper-v)
- [Win32_OptionalFeature states](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-optionalfeature)
- [Win32_Processor virtualization properties](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-processor)
- [Win32_ComputerSystem HypervisorPresent](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-computersystem)

The first reference guest remains an unselected Generation 2 Linux image.
Microsoft currently lists supported modern Linux guests and recommends newer
Generation 2 guests for the broadest feature availability. No distribution,
version, image source, checksum, toolchain, license, patch policy, or disk/RAM
allocation has been selected.

- [Generation 1 or 2 guidance](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/plan/Should-I-create-a-generation-1-or-2-virtual-machine-in-Hyper-V)
- [Supported Ubuntu guests](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/supported-ubuntu-virtual-machines-on-hyper-v)

## Reference profile boundaries

The B7 reference profile is intentionally inert:

| Field | Current value | Meaning |
| --- | --- | --- |
| Backend | `hyperv-managed` | Core-owned future backend identity |
| Isolation class | hardware VM (planned) | Claim requires later native conformance |
| Guest | Generation 2 Linux | Family choice only; image unselected |
| Network | disabled | No NIC or silent network fallback |
| Image revision | unconfigured | Execution must remain unavailable |
| Transport | Hyper-V socket candidate | Candidate only; compatibility/enrollment unverified |
| Supervisor revision | unconfigured | Execution must remain unavailable |

Microsoft documents Hyper-V sockets as a non-network host/guest data-stream
mechanism and documents Linux guest support when the required kernel options are
present. That makes them a candidate for later authenticated local transport,
not proof that StarFur has a secure channel. B8 must independently define and
test authentication, message framing, replay resistance, principal enrollment,
ACLs, size limits, cancellation, and disconnect behavior.

- [Build a Hyper-V integration service / Hyper-V sockets](https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/make-integration-service)

## B8a authentication boundary

`pipeline/sandbox_ipc.py` now defines only the inert, provider-free client
authentication contract. A bounded HMAC envelope binds a pre-enrolled Core
principal and key ID to one session instance, fixed `launch`, `query`, or
`cancel` operation, exact invocation fingerprint and worker generation, short
expiry, request ID, and nonce. Both request IDs and nonces are single-use in a
bounded cache that denies when full. A verifier must also receive the peer
principal from a trusted OS transport boundary; it may never copy that value
from the message, conversation ID, persona, provider, or API token.

This contract does not open a pipe or socket, store an enrollment key, authorize
a tool, create a grant/approval, contact Hyper-V, or execute anything. HMAC
authentication proves only possession of one enrolled client key. The native
service still requires separately approved installation, ACL-protected key
storage and rotation, trusted Windows peer-identity acquisition, restart-safe
replay protection, strict transport framing, and adversarial Windows/WSL tests.
Until those gates pass, no supervisor is enrolled and execution stays disabled.

### B8b framing boundary

`pipeline/sandbox_ipc_transport.py` adds only an in-memory receiver for fake
transport tests. Each request has one four-byte network-order length prefix and
must decode to the exact B8a envelope. Fragmentation and multiple frames in one
read are supported within fixed connection byte/frame ceilings. Invalid or
oversized lengths, malformed envelopes, authentication failure, replay,
overflow, and disconnect with a partial frame poison the connection. An explicit
abort forgets buffered data but cannot claim a job was cancelled or stopped.

The receiver does not listen, connect, reply, persist replay state, or dispatch
the authenticated operation. A future Windows service must still acquire the
peer identity from protected OS facilities and independently implement ACLs,
key storage/rotation, restart fencing, response framing, cancellation, and
disconnect supervision before it can expose any readiness.

### B8c authenticated response boundary

The reverse channel is separately authenticated in
`pipeline/sandbox_ipc_response.py`. It uses a distinct service key identity and
binds every response to the exact request, enrollment, service and transport
revisions, invocation fingerprint, and worker generation. Only the existing
strict supervisor status, cancellation receipt, or completion type allowed for
that operation may be carried. Existing `ToolResult` byte and artifact limits
remain in force; public response metadata excludes result text and artifacts.

Response authentication proves only that the enrolled service key produced the
matching message. It cannot turn an unverified stop into a verified one, provide
tool authorization, or establish backend readiness. Response IDs and nonces are
single-use in a bounded process-local cache. Durable restart replay protection
and protected service key storage remain native B8 requirements.

### B8d passive readiness boundary

`pipeline/sandbox_supervisor_readiness.py` can compare an expected Core profile
with explicitly supplied, short-lived evidence without probing anything. A
synthetic ready result requires exact backend, service, transport, and policy
revisions plus evidence for endpoint ACLs, separate client/service key storage,
OS peer identity, both authentication/framing directions, and restart-safe replay
protection. Missing, unsupported, unavailable, stale/future, mismatched, or
incomplete evidence returns a sanitized unavailable reason.

This compatibility result is not host attestation and supplies no authority.
It is not currently connected to startup, the application, diagnostics, the
apartment, or a backend. The actual host remains unsupported and no production
observation exists, so execution remains unavailable.

### B12a resident status projection

`pipeline/sandbox_execution_status.py` supplies one passive public status for
the optional subsystem. The default always reports `not_configured` and
`disabled`. An injected source may translate previously obtained readiness
evidence, but a ready transport still reports execution disabled until the later
native execution gates pass. A failing or invalid source becomes the closed
`observation_failed` state without exposing its exception.

The authenticated resident snapshot and apartment may display only the schema,
configured flag, closed host/supervisor/execution states, and sanitized reason.
They receive no backend/service/transport identity, endpoint, path, principal,
key, inventory, or evidence. Snapshot polling does not invoke the B7 probe and
cannot install, enroll, connect, authorize, or execute.

### B12b optional distribution boundary

The sandbox runtime is an optional component, not a base-product dependency.
StarFur Core, memory, adventures, providers, and the apartment must install and
operate when virtualization is unsupported, declined, unconfigured, or later
removed. Passive status is the only current installer-facing contract; it is
not an installation or backend-selection API.

A future installer must treat Windows feature enablement, privileged supervisor
enrollment, guest-image acquisition, and restart as separate explicit steps.
Declining or failing any step leaves execution unavailable without degrading the
resident. Updates and uninstall must address only StarFur-owned resources and
must never disable a shared Windows feature or remove unrelated virtual machines.
No current code installs, enables, downloads, provisions, enrolls, or uninstalls
any sandbox component.

### B9a guest-image compatibility contract

`pipeline/sandbox_image.py` defines the exact expected reference-image binding
and the shape of short-lived evidence that a later trusted verifier must supply.
The expectation covers a Generation 2 Linux x86-64 VHDX, SHA-256 digest,
toolchain revision, required signer, reviewed license policy, patch policy, and
their revisions. Missing, malformed, stale, mismatched, unverified, unapproved,
or stale-patch evidence denies.

This contract deliberately performs no verification itself. A `compatible`
result says only that the supplied evidence matches the declaration; it is not
proof of provenance, backend readiness, or permission to install or execute.
Actual acquisition, hashing, signature verification, protected evidence
creation, licensing review, and patch maintenance remain privileged setup work.

### S11a/S11b web-egress policy

`pipeline/tool_web_policy.py` is an inert policy seam for a later public-text
fetch tool. It requires one canonical HTTPS destination and separately supplied,
short-lived DNS evidence. Credentials, fragments, nonstandard ports,
noncanonical hosts, localhost, private/loopback/link-local/reserved literals,
and any resolved non-global address deny before a future connector can run.

The policy neither resolves nor connects. A permitted destination carries the
exact address set that a future connector must enforce. Pure S11b decisions
independently revalidate every bounded redirect target using fresh target-bound
evidence, deny exact loops and excessive hops, and require the supplied
connect-time address to remain canonical, public, and inside that fresh set.
They do not follow redirects or prove that a socket connected. Proxy handling,
response/decompression limits, MIME parsing, grants, confirmation, provenance,
and private-data disclosure remain unimplemented. No private input may reach a
hosted provider or web destination under this contract.

### S11c bounded response ingress

`pipeline/tool_web_response.py` is an inert response boundary for the same
future connector. It accepts only sanitized HTTP status, media type, content
encoding, and optional declared length plus already-decoded byte chunks with
the exact encoded bytes consumed. It independently caps encoded and decoded
sizes, limits decompression expansion, checks declared and identity sizes, and
requires strict non-NUL UTF-8. The narrow initial allowlist is public text,
HTML, Markdown, JSON, and XML with identity or gzip encoding.

Core does not yet make an HTTP request or decompress, parse, sanitize, index,
or persist this material. A future trusted connector must provide truthful
byte accounting and enforce the S11a/S11b network decisions. Passing ingress
validation never makes fetched text prompt-safe, canonical, or authoritative;
prompt-injection handling, quarantined format parsers, provenance, disclosure
classification, and broker authorization remain separate gates.

### S11d outbound disclosure classification

`pipeline/tool_web_disclosure.py` accepts only content-free classification
metadata supplied by trusted Core policy: classification, source kind, byte
count, and content digest. The initial fixed policy permits no-data and
explicitly public classifications only. Private disclosure is unsupported and
secret-store material is forbidden; sensitive source kinds cannot be relabeled
public at this boundary.

This policy does not prove that its caller classified data correctly and does
not grant network or tool authority. A later private-data feature must bind an
exact destination, content digest, invocation, expiry, use count, and revocation
generation through the broker. A boolean, chat response, model assertion,
persona/adventure ID, or conversation key can never enable disclosure.

### Exact prerequisite admission

`pipeline/tool_prerequisites.py` closes the gap between a contract saying it
requires a resource and the broker admitting it. A trusted Core adapter may
issue a short-lived one-use receipt only for an opaque resource reference
already bound into the exact invocation. The receipt also binds the operation
fingerprint, requirement, evidence digest, policy revision, expiry, and
revocation generation. Broker queueing requires every declared prerequisite
atomically and rechecks the claims immediately before a supervisor launch.

This mechanism does not inspect or certify a backend, DNS answer, destination,
file, or VM. Those policy modules supply evidence to future trusted adapters;
models, packages, chat text, API fields, and public UI cannot issue receipts.
The receipt remains separate from permission grants and explicit approval.
Inert preview and approval may occur while a prerequisite is absent, but queue
and execution fail closed.

### S11f inert public-fetch contract

The Core catalog now describes `web.fetch` v1 as read-only but explicitly
confirmation-required under the exact `network.fetch.public` scope. A proposal
contains one canonical HTTPS URL only. It cannot supply headers, bodies,
cookies, credentials, disclosure labels, permission, confirmation, resolver
evidence, limits, retries, or an executor.

Admission declares independent `network.destination` and `network.disclosure`
prerequisites. Results are reference-only: response text cannot cross generic
stdout/stderr fields. Retry class is proposal-only, so a fallback may generate
a new proposal but can never replay a fetch effect. No CLI/API proposal path,
resolver, HTTP connector, artifact store, or execution adapter exists yet.

### S11g exact executor and launch binding

The broker now asks an injected supervisor to affirm the exact tool ID and
contract version before entering the running state. `pipeline/tool_execution_router.py`
can bind separate sandbox and web supervisors without treating general adapter
availability as compatibility. No provider or proposal may select the adapter,
and there is no cross-tool fallback.

The private supervisor launch carries content-free commitments for every
claimed prerequisite: requirement ID, opaque resource reference, and evidence
digest. The launch deadline cannot outlive those receipts. This lets a trusted
adapter rejoin the exact Core-held evidence without exposing it through public
status, but it is still not permission or proof that an effect occurred.

### S11h fake-only web connector seam

`pipeline/tool_web_preflight.py` binds the exact initial destination and URL
disclosure classification to the launch commitments, then reevaluates the
short-lived DNS and disclosure decisions. The URL is itself outbound data; it
cannot be omitted from disclosure accounting.

`pipeline/tool_web_connector.py` is an orchestration seam tested only with
injected fakes. Its transport request is a no-body HTTPS GET pinned to one
approved public address, with matching TLS server name and HTTP host and with
automatic redirects, inherited proxies, cookies, and credentials disabled.
The returned peer address is rechecked before bounded response collection and
plain-text/Markdown quarantine. Successful generic results contain only one
opaque artifact reference.

At completion of this fake-only seam, no live adapter existed. Core still does
not configure the later native reference adapters. They must pass a controlled
public-site smoke before normal research use is enabled.

### S11i native web adapters

`pipeline/tool_web_native.py` supplies the first narrow reference components.
DNS resolution is explicit and bounded.
The session-only prerequisite store binds the exact resolved URL and public URL
classification; the quarantine store retains bounded provenance-bearing source
records only in memory.

The native transport creates its own certificate-validating TLS 1.2+ connection
to the selected public address while preserving the approved TLS server name and
HTTP Host. It sends one fixed-header bodyless GET. It does not use environment
proxy configuration, cookies, credentials, caller headers, or automatic
redirects. The initial adapter requests identity encoding only and accepts only
plain text or Markdown; duplicate/ambiguous framing, gzip, unsupported media,
oversized bodies, cancellation, and deadline expiry fail closed.

This is not a browser, crawler, general network client, or hostile-code sandbox.
It remains unreachable from shared chat/API paths and passive surfaces.

### S11j trusted-local orchestration

The interactive local Assistant CLI now creates one session-local native
composition. `tool propose web.fetch` only validates the canonical URL and
reserves opaque resource bindings; it performs no DNS or HTTP. After preview,
an exact one-use grant, and explicit approval, `tool prepare` performs the
bounded DNS lookup and records exact short-lived destination and URL-only
public-disclosure receipts. `tool execute` consumes all authority and evidence
once through the exact executor router. Success returns only an opaque
quarantine reference; bounded source text is visible only through the trusted
local `tool artifact` command and remains `untrusted_external`.

This path has no HTTP approval/execution endpoint, no model proposal path, no
provider/prompt bridge, no memory or skill write, and no `sandbox.run`
executor. It must pass the controlled WSL public-text and denial smoke matrix
before research escalation is considered.

### S11e quarantined text preparation

`pipeline/tool_web_parser.py` prepares only bounded `text/plain` and
`text/markdown` payloads. It canonicalizes Unicode and newlines, rejects hidden
or control formatting and excessive character counts, and preserves both the
response digest and a digest of the prepared representation. Every result is
explicitly labeled `untrusted_external`.

Preparation deliberately preserves text such as “ignore previous
instructions.” It is source data, not a command, and stripping a few phrases
would not make it safe. HTML, JSON, XML, scripts, and active content remain
unsupported until dedicated bounded parsers exist. A later prompt boundary must
frame prepared material as untrusted quoted evidence and keep it outside system,
policy, command, authority, and memory-approval channels.

### S9b aggregate tool status

`pipeline/tool_status.py` classifies existing session-local broker lifecycle
states into bounded counts. The resident snapshot and apartment can show pending
review, approved, queued, running, terminal, and total counts without revealing
which tool or request produced them. This is presentation only: reading it cannot
create a request or session, grant, approve, dispatch, cancel, probe, or execute.

## Explicit probe privacy and failure behavior

The fixed query reads only bounded operating-system edition/version/build,
architecture, optional-feature state, hypervisor presence, and CPU
virtualization/DEP capability flags. It does not read machine name, username,
domain, VM inventory, network configuration, paths, installed applications,
credentials, or user data. The public readiness report omits the raw host facts
and exposes only closed status/reason labels.

Malformed, duplicate-field, oversized, non-UTF-8, timed-out, unavailable, or
nonzero-exit probe responses fail closed as `probe_failed` or
`probe_unavailable`. Raw stdout, stderr, command errors, and exception text are
not returned. Windows Home, 32-bit architecture, disabled/absent Hyper-V, and
missing required hardware evidence do not produce prerequisite success.

The inspection is advisory application evidence only. It does not attest BIOS,
Windows, PowerShell/WMI, helper-service, guest-image, transport, hypervisor, or
isolation integrity. B8 and later native slices remain responsible for that.

## Distribution boundary

Hyper-V execution remains an optional component. StarFur Core, memory,
adventures, providers, apartment presentation, and zero-provider resident mode
must continue to install and run without Hyper-V, administrator privileges, a
guest image, or this probe. Future setup must obtain separate user approval for
feature changes, privileged helper installation, image acquisition, storage,
and restart. Uninstall must never disable a shared Windows feature or delete
unrelated VMs.
