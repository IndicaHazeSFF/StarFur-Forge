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
