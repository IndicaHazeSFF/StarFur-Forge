# Private annotation deployment verification — review draft

Status: COMPLETED PLAN DRAFT / SECURITY REVIEW PENDING, 2026-10-31. This is a proposed implementation sequence, not evidence, permission, a deployment certificate or a public processing control. Selected location: StarFur-Forge WSL. Core assumes a trusted local OS/operator, not hostile-root isolation.

**Narrow design decision completed on Sol High:** M1 below may proceed as an
inert byte decoder before the separate trusted-evidence review. This is not
approval of steps 3–7 or a resolution of actual execution/freshness/consent.

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
