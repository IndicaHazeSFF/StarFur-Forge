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
