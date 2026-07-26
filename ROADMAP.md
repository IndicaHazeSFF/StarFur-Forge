# ROADMAP UPDATE — POV / Perspective Tracking

## Add after “11. NEXT PHASE — Extraction Validation”

# 12. POV and Perspective Tracking

**HIGH-PRIORITY NARRATIVE-MEMORY FEATURE**

*Crown of Claws* is fundamentally a multi-perspective novel.

The narrative regularly moves between:

* the three primary character viewpoints;
* Quiet Accord as an important non-character perspective;
* secondary or third-party viewpoints such as Murr Lavenfur;
* occasional other viewpoint characters;
* potentially external or narrator-level information.

Because of this structure, StarFur must distinguish between:

**what exists in canon**

and

**who actually knows or observes it.**

These are not equivalent.

A fact revealed during a Quiet Accord sequence may be established for the reader without being known by Elias, Maeve, Murr, or another character.

Likewise, information observed from one character's perspective should not automatically become knowledge possessed by every other character.

### Initial Perspective Tracking

The first implementation should identify and store the dominant perspective associated with a scene or chunk.

Possible metadata:

```text
Perspective Type:
    character
    location
    external
    narrator
    unknown

Perspective Entity:
    Maeve
    Elias Voss
    Murr Lavenfur
    Quiet Accord
    etc.

Perspective Confidence:
    confirmed
    inferred
    uncertain
```

Perspective should not be restricted to characters.

Quiet Accord is an important narrative perspective despite being a place rather than a person.

The schema should therefore reference general entities where practical instead of assuming:

```text
POV == character
```

### Perspective Provenance

Extracted knowledge should eventually retain perspective alongside ordinary source provenance.

Conceptually:

```text
FACT
   │
   ├── evidence
   ├── source
   ├── scene
   ├── chunk
   └── perspective
```

Example:

```text
FACT:
C.E.P.H.A.L.O.N performs X.

Source:
Chapter 9

Perspective:
Quiet Accord

Established for:
Reader / world-state

Automatically known by Maeve:
No

Automatically known by Elias:
No
```

This prevents StarFur from confusing reader knowledge with character knowledge.

### Perspective Detection

Perspective may initially be established through:

* explicit chapter/scene metadata;
* deterministic manuscript structure;
* character names and viewpoint cues;
* annotator classification;
* human confirmation where uncertain.

Where possible, explicit metadata should outrank LLM inference.

StarFur should not invent a viewpoint when the source does not establish one clearly.

### Future Character Knowledge State

Perspective tracking provides the foundation for explicit character knowledge.

Eventually StarFur should be able to represent:

```text
WORLD / READER KNOWLEDGE
        │
        ├── Elias knows
        ├── Maeve knows
        ├── Murr knows
        └── other characters know
```

Knowledge may propagate through events.

Example:

```text
Quiet Accord reveals information to reader
        │
        ▼
Reader knows

Maeve later discovers the information
        │
        ▼
Maeve knows
```

This enables StarFur to distinguish:

* world truth;
* reader knowledge;
* character knowledge;
* character belief;
* mistaken belief;
* lies;
* withheld information;
* revelations.

### Why This Matters

Perspective tracking enables questions such as:

> Whose POV is this scene?

> What does Maeve know about Ceph at this point?

> Has Elias learned this yet?

> Does Murr know what happened at Quiet Accord?

> Is this information known to the character, or only to the reader?

> Would this dialogue accidentally reveal knowledge this character should not possess?

This makes perspective tracking foundational for later:

* relationship interpretation;
* event extraction;
* timeline reasoning;
* revelation tracking;
* continuity audits;
* contradiction detection;
* scene preparation;
* writing assistance.

For a multi-POV novel, perspective is therefore part of provenance rather than merely presentation metadata.

---

## Renumber the existing major sections after this insertion

Current:

```text
12. Relationship Extraction
13. Event Extraction
14. Timeline Memory
15. Canon Audit and Contradiction Detection
16. Provenance as a Core Principle
17. Improved RAG
18. Query Planning
19. Writing Assistant Mode
20. Draft → Review → Canon Workflow
21. Web Interface
22. Separate the Engine From Crown of Claws
23. StarFur Service/API
24. General Personal Memory
25. Tool System
26. Voice
27. Personality Layer
28. Desktop Companion
29. Emotional/Animation Signaling
30. THE END GOAL
31. Development Philosophy
32. Milestone Map
```

Becomes:

```text
13. Relationship Extraction
14. Event Extraction
15. Timeline Memory
16. Canon Audit and Contradiction Detection
17. Provenance as a Core Principle
18. Improved RAG
19. Query Planning
20. Writing Assistant Mode
21. Draft → Review → Canon Workflow
22. Web Interface
23. Separate the Engine From Crown of Claws
24. StarFur Service/API
25. General Personal Memory
26. Tool System
27. Voice
28. Personality Layer
29. Desktop Companion
30. Emotional/Animation Signaling
31. THE END GOAL
32. Development Philosophy
33. Milestone Map
```

---

# Replace the Milestone Map from Phase 3 onward with:

## Phase 3 — Knowledge Quality & Perspective Foundations

**NEXT**

* validate full-corpus extraction
* improve entity recall
* improve appearance recall
* tune fact extraction
* semantic fact deduplication
* improve chunking where necessary
* improve RAG retrieval
* establish scene/chunk perspective metadata
* detect dominant POV
* support non-character perspectives such as Quiet Accord
* attach perspective provenance to extracted knowledge
* validate perspective detection against manuscript structure

## Phase 4 — Knowledge Graph

* relationship extraction
* relationship evidence
* relationship review
* perspective-aware relationships where relevant
* graph querying
* graph visualization

## Phase 5 — Narrative Memory

* event extraction
* participants
* locations
* consequences
* timeline
* temporal reasoning
* narrative-order versus chronological-order tracking
* perspective associated with events
* revelation events
* initial character knowledge-state tracking

## Phase 6 — Canon Intelligence

* contradiction detection
* continuity audits
* perspective-aware continuity checking
* character knowledge-state reasoning
* reader knowledge versus character knowledge
* detect premature knowledge/revelations
* draft/canon separation
* manuscript review
* scene preparation
* writing assistance

## Phase 7 — StarFur Engine

* separate engine from *Crown of Claws*
* project abstraction
* hybrid retrieval
* query planner
* perspective-aware retrieval
* local API
* reusable memory domains

## Phase 8 — Control Center

* web UI
* entity browser
* graph explorer
* perspective/POV browser
* proposal review
* performance dashboards
* system administration

## Phase 9 — Personal Assistant

* personal/project memory
* model-directed memory proposals
* semantic conversational memory
* structured personal memory
* memory retention/importance policy
* tool framework
* permissions
* application launching
* file interaction
* system information
* automation

## Phase 10 — Voice

* speech-to-text
* text-to-speech
* conversational voice mode
* interruption handling
* wake/sleep behavior

## Phase 11 — Desktop Fursona

* transparent desktop companion
* animation states
* emotion signaling
* lip sync
* Live2D/3D evolution

## Phase 12 — StarFur

**END-STATE VISION**

A persistent, local-first furry AI companion that can:

> understand your fictional worlds,

> distinguish world truth, reader knowledge, and character knowledge,

> understand whose perspective information came from,

> remember structured knowledge,

> help write and maintain those worlds,

> understand your projects,

> selectively retain useful personal memory,

> operate approved computer tools,

> converse naturally through text and voice,

> visibly inhabit the desktop,

> and retain a transparent, inspectable memory of what it knows, who knows it, and why.
