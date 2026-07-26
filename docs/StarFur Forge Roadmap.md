# StarFur Forge — Grand Roadmap

**Project:** StarFur Forge
**Purpose:** Local-first AI knowledge, writing, memory, and eventually desktop-assistant platform
**Primary development environment:** WSL / Python / Ollama / SQLite / ChromaDB
**Current primary model:** Qwen3 8B
**Status:** Early functional prototype — core lore pipeline operational

---

# 1. The Original Idea

StarFur began with a comparatively simple problem:

> How can an AI writing assistant understand an entire fictional universe without requiring the entire manuscript to be placed into the context window every time?

The initial concept was essentially a local RAG system for *Crown of Claws*.

The desired workflow was:

**Manuscript → chunks → embeddings → vector database → retrieve relevant passages → local LLM**

The goal was to give a local model persistent access to the novel's canon while keeping inference practical on consumer hardware.

That relatively simple idea has since evolved into something considerably larger.

---

# 2. Stage One — Semantic Memory

## Goal

Allow StarFur to retrieve relevant portions of the manuscript based on natural-language questions.

## Components
## Preprocessing Layer — The Prechunker

Before Mr. Chonker operates on manuscript content, StarFur includes a higher-level preprocessing stage: the **Prechunker**.

The Prechunker solves a different problem from Mr. Chonker.

Its responsibility is to take a large source document—potentially an entire manuscript or other large input—and divide it into logical Markdown documents suitable for the rest of the StarFur pipeline.

Conceptually:

```
LARGE SOURCE DOCUMENT
         │
         ▼
    PRECHUNKER
         │
         ├── chapter detection
         ├── document segmentation
         ├── filename generation
         └── Markdown output
         │
         ▼
   INDIVIDUAL .MD FILES
         │
         ▼
    MR. CHONKER
```

The distinction is important:

**Prechunker performs document-level segmentation.**

**Mr. Chonker performs retrieval/analysis-level chunking inside those documents.**

For a novel, this means the Prechunker can transform a monolithic manuscript into files such as:

```
canon/chapters/
    01-routine.md
    02-approach.md
    03-classification.md
    ...
    15-margin.md
```

Mr. Chonker can then independently process each chapter into smaller semantic chunks suitable for embeddings and Mr. Annotator.

The architecture therefore supports:

```
RAW INPUT
    ↓
PRECHUNKER
    ↓
DOCUMENTS
    ↓
MR. CHONKER
    ↓
SEMANTIC CHUNKS
    ↓
┌─────────────────────┐
│                     │
▼                     ▼
MR. ANNOTATOR      EMBEDDINGS
│                     │
▼                     ▼
SQLITE              CHROMA
```

Although currently used for manuscript preparation, the Prechunker should remain **input-agnostic where practical**.

Future source types could include:

* complete novels;
* exported writing projects;
* large Markdown documents;
* worldbuilding documents;
* notes;
* reference material;
* other structured textual corpora.

This gives StarFur an explicit ingestion boundary:

> The Prechunker converts external source material into StarFur documents; Mr. Chonker converts StarFur documents into machine-usable chunks.

### Mr. Chonker — Markdown Chunker

Responsibilities:

* Read Markdown documents.
* Parse frontmatter.
* recognize scene boundaries.
* preserve headings.
* split prose into manageable chunks.
* avoid arbitrary mid-sentence cuts.
* provide limited chunk overlap.
* retain source and scene metadata.

Current default chunk target is approximately 1,200 characters.

### Embedding Pipeline

Chunks are embedded using:

**nomic-embed-text**

Embeddings are stored in ChromaDB.

This creates StarFur's **semantic memory**.

Instead of searching for exact words, StarFur can retrieve passages based on conceptual similarity.

### Initial RAG

A question is:

1. Embedded.
2. Compared against Chroma.
3. Matched to relevant canon chunks.
4. Supplied to Qwen.
5. Answered under strict grounding rules.

StarFur is instructed to:

* use supplied canon as authoritative;
* avoid inventing absent information;
* distinguish facts from inference;
* acknowledge when canon does not contain an answer.

This behavior has been successfully tested.

Known canon questions produce grounded answers.

Unknown questions such as:

> What is Elias Voss's favorite food?

correctly produce an acknowledgement that canon does not establish the answer.

---

# 3. Stage Two — Structured Memory

Semantic search alone is insufficient for maintaining a complex fictional universe.

StarFur therefore gained a second memory system:

**SQLite structured memory.**

Current database concepts include:

* entities
* aliases
* appearances
* entity facts
* relationships
* events
* event participants
* proposals

This transforms StarFur from pure RAG into the beginnings of a **fictional-universe knowledge graph**.

---

# 4. Mr. Annotator

A local Qwen model analyzes manuscript chunks.

Its job is not primarily to write.

Its job is to **extract structure from prose**.

Current extraction capabilities include:

### Known entities

Recognize previously confirmed entities appearing in a chunk.

### Entity appearances

Record:

* entity
* source
* scene
* chunk
* surrounding context

### Entity facts

Extract durable statements such as:

> Elias Voss has bright, luminescent white fur.

Each fact retains:

* entity
* normalized fact
* original evidence
* source document
* scene
* chunk
* status

### Entity proposals

When the annotator encounters something that appears to be a new entity, it does not automatically promote it into canon.

Instead it creates a **proposal**.

This provides a human-review boundary between:

**AI observation**

and

**confirmed canon**.

Example discovered during the first full manuscript analysis:

**C.E.P.H.A.L.O.N**

was proposed rather than silently inserted.

---

# 5. Canon Markdown Generation

SQLite is not intended to become the only representation of canon.

StarFur maintains human-readable Markdown entity files.

Example:

```
canon/
    characters/
        elias-voss.md
        maeve.md
        ceph.md

    entities/
        the-system.md
```

These documents contain human-editable content plus StarFur-managed sections.

Managed regions use explicit markers such as:

```
<!-- STARFUR:FACTS:START -->

...

<!-- STARFUR:FACTS:END -->
```

StarFur may regenerate content inside managed regions.

Human-written content outside those regions is preserved.

This creates a hybrid system:

**Human-written lore + machine-maintained structured knowledge**

without allowing the AI to freely overwrite canon documents.

---

# 6. Incremental Synchronization

A major architectural principle of StarFur is:

> Do not recompute things that have not changed.

The sync pipeline maintains hashes and pipeline versions.

When:

```
python starfur.py sync
```

is executed, StarFur determines which manuscript files actually require processing.

An unchanged project can therefore complete synchronization almost instantly.

The desired pipeline is:

**Changed manuscript**

→ structured analysis
→ SQLite update
→ canon Markdown update
→ semantic re-indexing

while:

**Unchanged manuscript**

→ skip annotation
→ skip writes
→ skip embeddings

This behavior has been successfully demonstrated.

---

# 7. Performance Instrumentation

StarFur maintains its own performance history.

Performance data is recorded in:

```
data/perf.jsonl
```

and rendered into:

```
perf.md
```

Tracked LLM metrics include:

* operation
* model
* input characters
* wall-clock time
* Ollama execution time
* prompt tokens
* output tokens
* tokens per second

Observed Qwen3 8B generation performance on the current system has been approximately:

**~69 tokens/second**

during annotation workloads.

Long-term, this telemetry can support:

* model comparisons;
* optimization work;
* regression detection;
* hardware comparisons;
* graphical dashboards.

---

# 8. Unified StarFur CLI

StarFur is transitioning from a collection of development scripts into a coherent application.

Current commands include functionality equivalent to:

```
python starfur.py status

python starfur.py analyze <document>

python starfur.py entity "Elias Voss"

python starfur.py export

python starfur.py sync

python starfur.py ask "Who is Elias Voss?"
```

Interactive RAG is also supported:

```
python starfur.py ask
```

followed by:

```
Ask StarFur:
```

The CLI should remain the primary low-level administrative interface even after graphical interfaces exist.

---

# 9. FIRST MAJOR MILESTONE — Full Manuscript Analysis

**STATUS: REACHED**

StarFur has completed its first full lore-analysis pass across the current *Crown of Claws* chapter corpus.

The first full run processed:

**15 chapters**

without pipeline failure.

Initial structured-memory results included:

```
Entities:      5
Aliases:       2
Appearances:   44
Relationships: 0
Events:        0
Proposals:     9
Facts:         21
```

These numbers are not yet considered optimized extraction results.

They establish something more important:

> The architecture survives a real manuscript workload.

This marks the transition from **prototype plumbing** to **knowledge-quality development**.

---

# 10. ★ CURRENT POSITION ★

## WE ARE HERE

The fundamental StarFur pipeline now exists.

```
RAW MANUSCRIPT
     │
     ▼
PRECHUNKER
     │
     ▼
MR. CHONKER
     │
     ▼
QWEN / MR. ANNOTATOR
     │
     ├───────────────┐
     ▼               ▼
  SQLITE          PROPOSALS
STRUCTURED
  MEMORY
     │
     ▼
CANON MARKDOWN
     │
     ▼
 EMBEDDINGS
     │
     ▼
  CHROMADB
     │
     ▼
    RAG
     │
     ▼
   QWEN
     │
     ▼
STARFUR ANSWER
```

The system can currently:

* ingest manuscripts;
* chunk prose;
* recognize known entities;
* record appearances;
* extract source-backed facts;
* propose unknown entities;
* maintain structured memory;
* generate/update canon documents;
* maintain semantic memory;
* answer grounded questions;
* refuse unsupported answers;
* skip unchanged work;
* measure its own LLM performance.

The next development phase should focus primarily on **knowledge quality and richer structure**, rather than additional basic plumbing.

---

# 11. NEXT PHASE — Extraction Validation

Before adding substantial new systems, inspect the first full lore dump.

Questions to answer:

### Entity recall

Is Mr. Annotator recognizing all important named entities?

### Appearance recall

If a known character appears in a chapter, is that appearance reliably recorded?

### Fact quality

Are extracted facts:

* actually canonical;
* durable;
* useful;
* correctly attributed;
* sufficiently specific?

### Duplicate facts

Identify semantically equivalent facts extracted from multiple chunks.

Future fact consolidation may merge:

> Ceph has structural inlays along his temples and neck.

and:

> Structural inlays trace Ceph's temples and neck.

without destroying separate evidence records.

### Chunk quality

Inspect empty or low-yield chunks and chapters.

Determine whether:

* the text genuinely contains no structured lore;
* the chunker created poor boundaries;
* the annotator prompt is too conservative.

---

# 12. Relationship Extraction

**NEXT MAJOR STRUCTURED-MEMORY FEATURE**

Relationships transform the database into a real graph.

Example:

```
Elias Voss
    │
    ├── works_with ──► Maeve
    │
    └── member_of ───► Organization
```

Relationships should contain:

* subject entity
* relationship type
* object entity
* description
* evidence
* source
* scene
* chunk
* confidence/status

A controlled relationship vocabulary should initially be preferred.

Possible predicates include:

* works_with
* reports_to
* commands
* member_of
* owns
* controls
* created
* allied_with
* enemy_of
* parent_of
* child_of
* located_in

The vocabulary can expand as actual manuscript requirements emerge.

---

# 13. Event Extraction

Facts describe state.

Relationships describe connections.

**Events describe change.**

Example:

```
EVENT
Relay Station Breach

Participants:
  Elias Voss
  Maeve

Location:
  Relay Station

Outcome:
  ...
```

Events should eventually support:

* participants;
* locations;
* sequence;
* chapter/scene;
* cause/effect;
* consequences;
* event aliases;
* timeline placement.

This enables questions such as:

> What happened before the breach?

> Who was present?

> When did Maeve first meet Elias?

> What changed after this event?

---

# 14. Timeline Memory

Once events exist, StarFur can develop explicit temporal reasoning.

Potential structure:

```
Event A
   │
   ▼
Event B
   │
   ├── simultaneous_with → Event C
   ▼
Event D
```

This becomes particularly important for long novels, sequels, flashbacks, and multiple viewpoints.

Timeline data should distinguish:

* narrative order;
* chronological order;
* uncertain dates;
* relative ordering.

---

# 15. Canon Audit and Contradiction Detection

Future command:

```
python starfur.py audit
```

Possible output:

```
POSSIBLE CANON CONFLICT

Elias Voss

Existing:
Elias has white fur.

New:
Elias has black fur.

Sources:
chapter-01.md
chapter-19.md
```

The system should not automatically decide that every contradiction is an error.

Fiction legitimately contains:

* character lies;
* unreliable narration;
* mistaken beliefs;
* disguises;
* changes over time;
* retcons.

Therefore StarFur should primarily **surface potential contradictions for human review**.

---

# 16. Provenance as a Core Principle

StarFur should never become a pile of AI-generated lore whose origin cannot be determined.

Important knowledge should remain traceable:

```
FACT
   ↓
EVIDENCE
   ↓
CHUNK
   ↓
SCENE
   ↓
SOURCE DOCUMENT
```

The same principle should eventually apply to:

* relationships;
* events;
* timeline claims;
* inferred information.

This is one of the project's most important architectural constraints.

---

# 17. Improved RAG

Current RAG primarily uses semantic retrieval.

Future retrieval should become **hybrid**.

A question might trigger:

```
QUESTION
   │
   ├── Vector Search
   │
   ├── Entity Lookup
   │
   ├── Fact Lookup
   │
   ├── Relationship Graph
   │
   └── Timeline/Event Search
   │
   ▼
CONTEXT ASSEMBLY
   │
   ▼
   LLM
```

This should provide much stronger answers than vector search alone.

---

# 18. Query Planning

Eventually the model should classify questions before retrieval.

Example:

> What color is Elias's fur?

Route primarily toward entity facts.

> Who works with Elias?

Route toward relationships.

> What happened after the breach?

Route toward events/timeline.

> Describe the atmosphere when Elias entered the facility.

Route toward semantic manuscript retrieval.

The model should use the appropriate memory system instead of blindly vector-searching everything.

---

# 19. Writing Assistant Mode

Once StarFur understands canon reliably, it can assist directly with writing.

Possible modes:

### Canon lookup

> What does Maeve know about Ceph at this point?

### Continuity checking

> Does anything in this scene contradict earlier chapters?

### Scene preparation

> Give me the relevant canon before I write Chapter 23.

### Character context

> What emotional state was Murr in during her previous appearance?

### Draft review

Analyze new prose before it becomes canon.

Important distinction:

**Draft memory ≠ confirmed canon.**

StarFur should preserve this boundary.

---

# 20. Draft → Review → Canon Workflow

Long-term writing workflow:

```
DRAFT
  │
  ▼
STARFUR ANALYSIS
  │
  ├── new facts
  ├── new entities
  ├── relationships
  ├── events
  └── possible conflicts
  │
  ▼
HUMAN REVIEW
  │
  ▼
CONFIRMED CANON
  │
  ▼
STRUCTURED MEMORY
```

This effectively turns StarFur into a **continuity editor** as well as an assistant.

---

# 21. Web Interface

The CLI should remain available, but StarFur eventually deserves a graphical control center.

Possible dashboard sections:

### System

* Ollama status
* Chroma status
* database status
* current models
* memory statistics

### Performance

Graphs for:

* tokens/sec;
* annotation duration;
* embedding performance;
* chunks processed;
* model comparisons;
* historical performance.

### Entities

Search and browse the universe.

### Knowledge Graph

Interactive visualization:

```
Murr ─────► Maeve
  │
  │
  ▼
Elias ───► Ceph
```

Clicking an entity opens:

* summary;
* facts;
* aliases;
* appearances;
* relationships;
* events;
* evidence;
* source passages.

### Manuscript

Browse chapters and their extracted knowledge.

### Proposals

Review AI-discovered entities/facts/relationships.

---

# 22. Separate the Engine From Crown of Claws

This is a critical long-term architectural step.

StarFur should eventually become a **general engine**, while *Crown of Claws* becomes one project loaded into it.

Possible structure:

```
StarFur Engine
    │
    ├── LLM
    ├── embeddings
    ├── memory
    ├── graph
    ├── RAG
    ├── tools
    └── API

Projects
    │
    ├── Crown of Claws
    ├── Another Novel
    └── Other Knowledge Bases
```

This makes StarFur reusable beyond a single fictional universe.

---

# 23. StarFur Service/API

The current CLI should eventually sit on top of a reusable application layer.

Possible local API:

```
POST /ask
GET  /entities
GET  /entities/{id}
GET  /relationships
GET  /events
POST /sync
GET  /status
```

The CLI, web UI, and future desktop assistant would all communicate with the same backend.

Architecture:

```
SQLite ─┐
Chroma ─┼──► StarFur Core
Ollama ─┘         │
                  ▼
              Local API
              /   |   \
             /    |    \
           CLI   Web   Desktop
```

---

# 24. General Personal Memory

Once StarFur is separated from *Crown of Claws*, its structured-memory architecture could support additional memory domains.

Examples:

* projects;
* preferences;
* computer configuration;
* recurring tasks;
* notes;
* documents;
* software projects.

These should be isolated into appropriate namespaces/databases rather than mixed indiscriminately with fictional canon.

---

# 25. Tool System

StarFur can eventually gain explicit computer capabilities.

Examples:

```
open_application("steam")

open_website(...)

search_files(...)

get_system_status()

play_music(...)

query_calendar(...)

create_note(...)
```

The LLM should **not** receive unrestricted shell execution.

Tools should be:

* explicitly defined;
* allowlisted;
* validated;
* permission-aware;
* logged;
* optionally confirmation-gated.

The model requests an action.

StarFur decides whether that action is permitted.

---

# 26. Voice

Input pipeline:

```
MICROPHONE
    │
    ▼
SPEECH-TO-TEXT
    │
    ▼
STARFUR
```

Output:

```
STARFUR
    │
    ▼
   TTS
    │
    ▼
 SPEAKERS
```

Voice should remain modular so STT and TTS engines can be replaced independently.

---

# 27. Personality Layer

The assistant eventually becomes more than Qwen's default personality.

Personality should be explicitly separated from knowledge.

Possible components:

* system personality;
* speech style;
* emotional state;
* relationship state;
* response verbosity;
* behavioral rules.

The assistant may therefore have a furry persona without contaminating factual memory or canon.

---

# 28. Desktop Companion

This is the eventual transition from:

```
python starfur.py ask
```

to an actual persistent assistant.

Initial implementation can be simple.

### Version 1

Transparent always-on-top desktop window.

Sprite states:

```
idle
blink
talking
thinking
happy
annoyed
sleeping
```

### Version 2

Animated 2D avatar.

Possible technologies:

* Live2D;
* sprite animation;
* custom rigging.

### Version 3

Full 3D avatar.

Possible features:

* skeletal animation;
* facial expressions;
* lip sync;
* gaze tracking;
* desktop positioning;
* VR integration.

---

# 29. Emotional/Animation Signaling

The LLM response can include internal presentation metadata.

Conceptually:

```
response:
  text: "Already opening it."
  emotion: amused
  animation: smug
  action: open_application
```

The user sees/hears:

> Already opening it.

Meanwhile the avatar receives:

```
emotion = amused
animation = smug
```

and the tool system receives:

```
open_application(...)
```

The presentation metadata should remain separate from spoken text.

---

# 30. THE END GOAL

StarFur ultimately becomes a:

# Local-First Personal AI Companion and Knowledge System

with:

* local LLM inference;
* persistent semantic memory;
* structured long-term memory;
* knowledge graphs;
* provenance;
* document understanding;
* project-specific knowledge;
* writing assistance;
* continuity checking;
* computer tools;
* voice interaction;
* personality;
* animated furry avatar;
* local API;
* web administration interface;
* performance telemetry.

Conceptually:

```
┌──────────────────────────────┐
│       DESKTOP COMPANION      │
│                              │
│      Animated furry AI       │
└──────────────┬───────────────┘
               │
      Voice / Text / Actions
               │
               ▼
┌──────────────────────────────┐
│        STARFUR ENGINE         │
│                              │
│ Personality                  │
│ Reasoning                    │
│ Query Planning               │
│ Tool Routing                 │
└───────┬────────┬────────┬────┘
        │        │        │
        ▼        ▼        ▼
     Ollama   Memory    Tools
                │
         ┌──────┴──────┐
         ▼             ▼
       SQLite        Chroma
         │
         ▼
  Knowledge Graph
         │
         ▼
   Project Memory
         │
  ┌──────┼──────────┐
  ▼      ▼          ▼
Crown   Personal   Future
  of    Projects   Domains
Claws
```

The furry desktop companion is therefore **not the core system**.

It is the face attached to StarFur.

The actual product is the engine underneath it.

---

# 31. Development Philosophy

StarFur should remain:

### Local-first

Core functionality should not require cloud services.

### Incremental

Do not recompute unchanged knowledge.

### Inspectable

Humans should be able to inspect what StarFur believes.

### Source-backed

Important knowledge should retain provenance.

### Human-authoritative

AI extraction proposes and organizes knowledge.

Humans determine canon.

### Modular

Models, embedding systems, databases, speech engines, and interfaces should remain replaceable.

### Safe by architecture

A probabilistic language model should never automatically receive unrestricted control over the operating system.

### Useful before impressive

Build working memory, retrieval, and tools before spending excessive effort on visual polish.

---

# 32. Milestone Map

## Phase 0 — Experimentation

**COMPLETE**

* Local LLM experiments
* Ollama
* OpenWebUI
* WSL environment
* model testing

## Phase 1 — Semantic Lore Memory

**COMPLETE**
* Prechunker / source segmentation
* Markdown ingestion
* Mr. Chonker
* embeddings
* ChromaDB
* basic RAG

## Phase 2 — Structured Lore Memory

**CURRENT / MOSTLY COMPLETE**

* SQLite
* entities
* aliases
* appearances
* facts
* proposals
* canon export
* managed Markdown
* incremental sync
* performance telemetry
* unified CLI
* first full manuscript analysis

# ★ WE ARE HERE ★

## Phase 3 — Knowledge Quality

**NEXT**

* validate full-corpus extraction
* improve entity recall
* improve appearance recall
* tune fact extraction
* semantic fact deduplication
* improve chunking where necessary
* improve RAG retrieval

## Phase 4 — Knowledge Graph

* relationship extraction
* relationship evidence
* relationship review
* graph querying
* graph visualization

## Phase 5 — Narrative Memory

* event extraction
* participants
* locations
* consequences
* timeline
* temporal reasoning

## Phase 6 — Canon Intelligence

* contradiction detection
* continuity audits
* draft/canon separation
* manuscript review
* scene preparation
* writing assistance

## Phase 7 — StarFur Engine

* separate engine from *Crown of Claws*
* project abstraction
* hybrid retrieval
* query planner
* local API
* reusable memory domains

## Phase 8 — Control Center

* web UI
* entity browser
* graph explorer
* proposal review
* performance dashboards
* system administration

## Phase 9 — Personal Assistant

* personal/project memory
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

> remember structured knowledge,

> help write and maintain those worlds,

> understand your projects,

> operate approved computer tools,

> converse naturally through text and voice,

> visibly inhabit the desktop,

> and retain a transparent, inspectable memory of what it knows and why.

---

# Guiding Question

Whenever a new feature is proposed, ask:

> **Does this make StarFur better at knowing, reasoning about, assisting with, or interacting with the things I care about—without sacrificing control over my data or computer?**

If yes, it probably belongs somewhere on this roadmap.

If not, it is probably feature creep.

---

# Current Checkpoint

**StarFur has successfully read its first complete real manuscript corpus.**

The foundation exists.

The next chapter of development is no longer primarily about proving that the architecture can work.

It is about turning that architecture into an increasingly capable intelligence layer—and, eventually, giving that intelligence a face.
