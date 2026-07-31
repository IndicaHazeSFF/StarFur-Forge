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


Future Research & Long-Term Ideas

The following ideas are intentionally outside the current roadmap. They represent promising directions once the core assistant, memory architecture, and user experience have matured.

Persona Layer

Separate personality from assistant logic.

Current persona instructions are embedded within the assistant prompt. Future versions should move persona into its own configurable layer so that personality can be changed independently of memory retrieval, safety behavior, and reasoning.

Potential goals:

Swappable personas
Cleaner prompts
Better consistency on smaller models
Easier community-created personas
Neutral default persona for non-furry users
Persona Library

Allow users to install or create multiple personas.

Examples:

Neutral Assistant
StarFur (default)
Fox Mom
Technical Mentor
Creative Writer
Custom user personas

Personas should influence tone, style, and mannerisms without changing factual behavior or memory handling.

Adaptive Model Profiles

(The section you already added.)

Automatically tune retrieval budgets, summarization, and context allocation based on the currently selected model.

Context Manager

Introduce a dedicated context assembly system responsible for intelligently constructing prompts.

Responsibilities may include:

Context budgeting
Memory ranking
Memory compression
Conversation summarization
Persona injection
Token reservation
Context diagnostics

The Context Manager should become responsible for deciding what enters the model's context window.

Conversation Summarization

Replace extremely long conversation histories with progressively generated summaries.

Goals:

Reduce context usage
Preserve continuity
Improve small-model performance
Allow effectively unlimited conversation length
Memory Compression

Investigate methods for combining related memories into more compact representations.

Examples:

Merge duplicate preferences
Combine evolving goals
Summarize historical context
Detect obsolete memories

The objective is to maximize information density while minimizing context consumption.

Operational Memory

Investigate a fourth memory domain dedicated to assistant operation rather than user knowledge.

Possible responsibilities:

Active context budgeting
Retrieval diagnostics
Session state
Context planning
Prompt assembly metadata
Recently injected memories
Provider capabilities

This memory would not appear as user-visible long-term memory.

Multiple Provider Support

Expand beyond Ollama.

Potential providers:

LM Studio
OpenAI-compatible APIs
OpenRouter
Local custom providers
Future inference engines

Provider selection should be abstracted behind a common interface.

Open WebUI Integration

Provide an OpenAI-compatible API allowing StarFur Forge to operate as a backend for Open WebUI.

Goals:

Browser-based chat
Streaming responses
Multi-session support
Memory introspection
Proposal review
Full StarFur functionality outside the terminal
Desktop Launcher

Develop a graphical launcher for StarFur Forge.

Possible features:

Model selection
Persona selection
Provider selection
Memory statistics
Context diagnostics
Launch configuration
Profile management

The launcher should make StarFur accessible to non-technical users.

Telemetry-Based Optimization

Allow StarFur to anonymously (or locally) learn how different models perform.

Potential metrics:

Retrieval success
Context utilization
Average prompt size
Response latency
Memory usefulness
Summarization frequency

The goal is to improve default configuration automatically over time.

Plugin Architecture

Provide extension points without requiring modification of the core assistant.

Potential plugin categories:

Retrieval strategies
Persona packs
Memory processors
Exporters
External tools
Custom commands
Multi-Agent Research

Investigate specialized internal agents.

Possible examples:

Memory reviewer
Context planner
Persona manager
Retrieval optimizer
Proposal reviewer

These should remain deterministic components rather than autonomous independent assistants.

Distributed Knowledge Sources

Allow retrieval from multiple simultaneous knowledge domains.

Examples:

User memories
Novel canon
Project documentation
Git repositories
Local notes
External databases

All should participate in retrieval while preserving provenance.

Packaging & Distribution

Long-term release goals:

One-click installer
Automatic dependency setup
Model detection
Guided first launch
Configuration wizard
Portable mode
Cross-platform support