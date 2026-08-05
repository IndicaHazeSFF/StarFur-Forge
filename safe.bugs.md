# Safe Bugs / Edge Cases

Issues that are non-critical and can be scheduled without blocking normal development.

## Ctrl+C during pasted or mid-turn terminal input

**Observed:** Pasting a long prompt into the interactive WSL assistant and pressing Ctrl+C at an awkward point caused a crash/traceback.

**Expected:** The interrupted turn should be discarded cleanly, with no partial response, proposal, conversation-history entry, or diagnostic state; return to the prompt (or exit cleanly if interruption occurs while waiting for input).

**Priority:** Low / edge case. Normal streaming interruption handling is already covered; add a focused regression test when convenient.