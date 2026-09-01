I'd write this down as Bug #1

Retrieved memories should dominate generation.

Pipeline should be closer to:

User question
      ↓
Memory search
      ↓
Relevant memories found
      ↓
Inject as authoritative context
      ↓
LLM response

instead of

User question
      ↓
LLM improvises
I'd actually tighten the prompt

Something like:

When answering a question that is supported by retrieved assistant memories:

Treat those memories as authoritative.
Do not replace, embellish, contradict, or invent alternative facts.
Persona may affect wording and tone only.

That's a surprisingly important distinction.


This also suggests a future confidence model.

If retrieval confidence is:

0.98

the LLM should have almost zero freedom to change the factual content.

If confidence is

0.32

it can say

"I think you mentioned..."

Huge difference.









Database constraint test:
- Invalid retention accepted by SQLite
- Result: FAIL at database layer
- Application validation may still exist

Database Constraint Test: PARTIAL PASS

PASS
- NULL summary rejected
- Required columns enforced

FAIL
- Invalid retention accepted
- Importance outside 0.0–1.0 accepted
- Confidence outside 0.0–1.0 accepted
- Status values likely unrestricted
- Memory types likely unrestricted











