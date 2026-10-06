# Safe Bugs / Edge Cases

Issues that are non-critical and can be scheduled without blocking normal development.

## Ctrl+C during pasted or mid-turn terminal input

**Observed:** Pasting a long prompt into the interactive WSL assistant and pressing Ctrl+C at an awkward point caused a crash/traceback.

**Expected:** The interrupted turn should be discarded cleanly, with no partial response, proposal, conversation-history entry, or diagnostic state; return to the prompt (or exit cleanly if interruption occurs while waiting for input).

**Priority:** Low / edge case. Normal streaming interruption handling is already covered; add a focused regression test when convenient.

## Roleplay response exposed relationship-meter numbers

**Observed:** During an active Quiet Ember roleplay session, StarFur correctly
retrieved relationship memories but answered with internal values such as
`Trust: 49/100`, despite the story rules saying those numbers should not be
exposed in character.

**Expected:** Describe relationship state qualitatively in normal and roleplay
responses. Reveal numeric diagnostics only when the user explicitly requests
internal/debug details.

**Status:** Mitigated by deterministic roleplay-context redaction; verify with
the live local model before closing. Retrieval and roleplay state were otherwise
functioning correctly.

## Client disconnect after long document annotation

**Observed:** A 64-chunk `/v1/starfur/documents/annotate` request completed with
HTTP 200, but the client disconnected before the response body was written,
causing `BrokenPipeError` in `pipeline/api.py` while sending JSON. Terminal
progress also continued to show the completed-chunk count.

**Expected:** A timed-out or closed client must not produce a server traceback.
Completed annotation remains review-only and must not be reported as a failed
server operation merely because its response socket disappeared.

**Status:** Mitigated by making the JSON response writer absorb expected broken
pipe, reset, and socket errors. Asynchronous/pollable document jobs remain the
long-term solution for very large uploads.

## Repeated manual turn staging can create redundant state events

**Observed:** A terminal paste glitch submitted the same explicit
`adventure turn stage state` command five times. Core staged and committed five
identical state-change events.

**Expected:** Repeated identical manual state drafts could be detected as a
local no-op or presented with a confirmation, while preserving an explicit
escape hatch for intentionally repeated events.

**Impact:** Low. The event log remains valid and auditable, and the complete
state projection correctly resolves to the latest value. Use `adventure turn
abort` before restarting a mistaken staging sequence; correction/retraction
remain available after commit.

**Status:** Safe UX improvement; does not block adventure integrity or model
smoke testing.

## Qwen typed-mutation extraction returned an invalid envelope

**Observed:** During `adventure turn mutations generate`, Qwen (`qwen3:8b`)
occasionally produced output that failed the typed candidate schema with
`mutation_candidate_envelope_invalid`.

**Expected:** Provider output remains untrusted; invalid JSON/schema is rejected
without staging, persistence, or partial turn mutation.

**Status:** Core fail-closed behavior passed. Preserve as a model-portability
regression case; improve through task profiles, routing, and benchmarked model
selection rather than weakening validation.

## Gemma typed-mutation extraction returned empty content

**Observed:** During the same explicit generation task, Gemma returned no usable
message content and Core reported `response_empty`.

**Expected:** Empty provider output is rejected cleanly with no staged or
persisted mutation and an inspectable failure category.

**Status:** Core fail-closed behavior passed. Preserve as a provider/model
reliability case for latency, timeout, and portability evaluation.

## Qwen exact-reply smoke exposed a `/think` suffix

**Observed:** A live normal-chat recovery request asking for exactly `recovered`
returned `recovered /think` after the cross-process provider-capacity smoke.

**Expected:** Tasks that genuinely require an exact textual form need a bounded
task/provider contract rather than relying on ordinary conversational
instruction following. General response normalization must not blindly strip
arbitrary user-visible text.

**Impact:** Low for ordinary conversation and unrelated to provider admission;
the recovery request completed and capacity was released correctly. Preserve
this as a model-portability case for a future explicit reasoning/exact-response
mode.
