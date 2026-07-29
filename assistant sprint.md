# StarFur — One-Week Functional Assistant Prototype Guiderail

## Target State

At the end of this sprint, StarFur should be a usable local-first assistant prototype with:

* persistent conversational memory;
* SQLite structured memory;
* Chroma semantic memory;
* selective memory storage rather than logging everything;
* memory provenance and auditability;
* a persistent furry persona;
* relevant-memory retrieval before responses;
* a basic distinction between temporary and durable knowledge;
* project/lore memory remaining isolated from personal memory;
* simple model routing;
* at least one specialist-model handoff, ideally coding;
* a single convenient launch interface, preferably a TUI;
* enough diagnostics to understand why the assistant remembered, forgot, retrieved, or routed something.

The goal is:

> **Working assistant with quirks to fix.**

Not:

> polished commercial release.

---

# STAGE 0 — Stabilize the Existing Memory Engine

## Goal

Do not build the assistant on top of an unreliable extraction pipeline.

## 0.1 Finish Current Structured-Memory Repair

Allow the currently dirty manuscript sources to complete analysis using:

* nested annotation validation;
* bounded retries;
* 2,048-token annotation ceiling;
* source retry semantics;
* fact-type classification.

### Acceptance criteria

A sync should eventually reach:

```text
Failed: 0
```

or leave only clearly diagnosed exceptional failures.

No:

```text
'str' object has no attribute 'get'
```

No 40,960-token runaway generations.

No global pipeline crash because one chunk produced malformed output.

---

## 0.2 Inspect Fact-Type Quality

Query:

```sql
SELECT fact_type, COUNT(*)
FROM entity_facts
GROUP BY fact_type
ORDER BY COUNT(*) DESC;
```

Sample each category:

* durable_fact
* behavioral_tendency
* physical_attribute
* procedural_system_rule
* temporary_scene_state

Verify that the model understands the distinction reasonably well.

### Do not over-tune yet

We only need classifications to be useful enough for retrieval policy.

---

## 0.3 Add Extraction Diagnostics

Codex-sized task:

Create diagnostics/reporting for:

* failed chunks;
* retry count;
* parse-failure reason;
* output-limit hits;
* unknown fact targets;
* duplicate-looking proposals;
* fact-type distribution.

Prefer reporting over automatic correction initially.

### Acceptance criteria

When something goes wrong, we should be able to determine:

> what failed?

> where?

> why?

> what data was affected?

without manually crawling logs.

---

# STAGE 1 — Establish Memory Domains

## Goal

Prevent personal assistant memory from contaminating fictional/project knowledge.

StarFur currently understands a project-specific canon domain.

The assistant needs separate memory domains.

Conceptually:

```text
STARFUR MEMORY
    │
    ├── Project Memory
    │      ├── fictional canon
    │      ├── software projects
    │      └── documents
    │
    └── Personal Memory
           ├── preferences
           ├── experiences
           ├── recurring context
           ├── people
           └── ongoing situations
```

## 1.1 Add Memory Namespace/Domain

Every assistant memory should belong to an explicit domain.

Example:

```text
domain = personal
domain = project:starfur
domain = project:crown-of-claws
```

Do not merge everything into one undifferentiated memory pool.

---

## 1.2 Define Personal Structured-Memory Schema

Do not reuse fictional `entity_facts` blindly.

Create assistant-oriented memory records.

A useful first schema might contain:

```text
memory_id
subject
memory_type
summary
details
importance
confidence
retention
source
created_at
updated_at
last_accessed_at
status
```

Possible `memory_type` values:

```text
preference
personal_fact
experience
project_context
relationship_context
ongoing_situation
goal
routine
```

Possible retention:

```text
session
short_term
long_term
```

### Important

The schema can evolve.

Do not attempt to model an entire human mind in version one.

---

# STAGE 2 — Build the Assistant Conversation Loop

## Goal

StarFur becomes something you can actually talk to.

Create a separate assistant entrypoint rather than forcing conversational behavior into manuscript annotation code.

Conceptually:

```text
python assistant.py
```

or eventually:

```text
python starfur.py assistant
```

Flow:

```text
USER
  ↓
retrieve relevant memory
  ↓
assemble context
  ↓
persona model
  ↓
response
```

At first, do not add model routing or tools.

Just establish persistent conversation.

---

## 2.1 Persona Configuration

Persona should be configuration, not hardcoded business logic.

Example:

```text
persona/
    default.md
```

or:

```text
config/persona.yaml
```

Include:

* identity;
* tone;
* behavioral expectations;
* response style;
* relationship framing;
* boundaries;
* optional quirks.

Knowledge and personality remain separate.

The persona may say:

> “I remember you mentioning that.”

The persona file itself should not contain the remembered information.

---

## 2.2 Session Context

Maintain a small recent conversation window separately from permanent memory.

Example:

```text
RECENT CONVERSATION
last 10–30 messages
```

This prevents every sentence from immediately becoming long-term memory merely because it is needed for the current conversation.

---

# STAGE 3 — Selective Memory Writing *(Largely Complete)*

## Goal

The assistant should intelligently decide what information is worth remembering while keeping humans in complete control of what becomes authoritative memory.

The model proposes.

The application validates.

The human approves.

Flow:

```text
USER MESSAGE
      ↓
Grounded Extraction
      ↓
Schema Validation
      ↓
Persistent Proposal Queue
      ↓
Human Review
      ↓
Approved Memory
```

---

## 3.1 Memory Proposal Pipeline ✅

Implemented:

* grounded extraction using only user messages as evidence
* strict structured schema validation
* bounded retry/repair pipeline
* proposal normalization
* engine-owned metadata
* domain assignment
* retention policy
* importance/confidence validation
* rejection of malformed proposals
* explicit proposal semantics (`store=true`)

The LLM never writes directly to permanent memory.

It proposes.

The application decides.

---

## 3.2 Durable Human Review Workflow ✅ *(Completed)*

Assistant memories now pass through a persistent review queue.

Implemented:

* durable proposal storage
* pending / approved / rejected lifecycle
* proposal persistence across restarts
* proposal listing
* proposal approval
* proposal rejection
* transactional approval
* approved-memory linkage
* proposal provenance
* source proposal tracking

Nothing becomes authoritative without approval.

---

## 3.3 Proposal Idempotency & Reinforcement ✅ *(Completed)*

Repeated observations reinforce existing pending proposals rather than creating duplicates.

Implemented:

* deterministic proposal identity
* pending proposal deduplication
* proposal evidence tracking
* evidence count
* duplicate evidence prevention
* confidence reinforcement
* first observed timestamp
* last observed timestamp
* bounded confidence growth
* partial unique database constraints
* reviewed proposals remain closed

This allows repeated observations to strengthen confidence while preserving complete auditability.

---

## 3.4 Source Identity Stabilization *(Current Sprint)*

Current limitation:

Proposal identity still depends partly on LLM-generated summaries.

This means identical user messages can occasionally create different pending proposals if the model phrases the summary differently.

Next objective:

Use deterministic source-event identity so that:

```text
Same user message
        +
Different generated summaries
        ↓
Same proposal
```

while still allowing genuinely different user messages to generate separate proposals.

This intentionally avoids fuzzy semantic merging for now.

---

# STAGE 4 — Assistant Memory Persistence *(Mostly Complete)*

## Goal

Use SQLite for authoritative assistant memory while preparing for semantic memory integration.

Completed:

* assistant memory schema
* durable assistant memories
* transactional approval pipeline
* provenance preservation
* proposal → memory linkage
* source tracking
* structured assistant memory CRUD
* persistent memory domains
* grounded retrieval

Remaining:

* Chroma semantic memory
* dual-write policy
* conversational episode storage
* semantic namespace management

SQLite now answers:

> What does StarFur explicitly know?

---

# STAGE 5 — Memory Retrieval *(Partially Complete)*

## Goal

Retrieve only the information relevant to the current conversation.

Current pipeline:

```text
USER MESSAGE
      ↓
Structured Retrieval
      ↓
Context Assembly
      ↓
Persona
      ↓
Response
```

Completed:

* structured retrieval before responses
* domain-aware retrieval
* grounded assistant recall
* retrieval filtering
* provenance-preserving context assembly

Remaining:

* semantic retrieval
* retrieval ranking
* retrieval budgeting
* hybrid structured + semantic recall
* contextual ranking improvements

---

# STAGE 6 — Memory Inspection & Auditability *(Mostly Complete)*

## Goal

Memory should never become a black box.

Completed:

* proposal inspection
* proposal review
* proposal approval
* proposal rejection
* provenance inspection
* evidence inspection
* deterministic audit trail

Still planned:

* memory search
* memory correction
* memory supersession
* retrieval explanations ("Why did you remember this?")
* memory editing
* memory history visualization

---

# Memory Engine Milestone — Version 0.4 ✅

StarFur now has a fully human-in-the-loop memory architecture.

```text
Conversation
        │
        ▼
Grounded Extraction
        │
        ▼
Validation
        │
        ▼
Persistent Proposal Queue
        │
        ▼
Human Review
        │
        ▼
Approved Memory
        │
        ▼
Grounded Retrieval
```

Current properties:

* deterministic
* restart-safe
* human-approved
* provenance-preserving
* transaction-safe
* auditable
* evidence-backed
* domain-aware
* validation-first

---

# Immediate Roadmap

## Phase 4.3 — Source Identity Stabilization

Ensure identical source events reinforce existing proposals regardless of generated summary wording.

---

## Phase 4.4 — Approved Memory Deduplication

Detect when newly approved memories already exist.

Possible outcomes:

* ignore duplicate
* reinforce existing memory
* propose update
* propose conflict

---

## Phase 4.5 — Memory Evolution

Allow memories to change over time.

Support:

* active
* superseded
* historical
* uncertain

without losing provenance.

---

## Phase 4.6 — Semantic Memory Integration

Integrate Chroma alongside structured memory for conversational recall and fuzzy contextual retrieval.

---

## Phase 4.7 — Retrieval Ranking

Combine:

* semantic similarity
* importance
* recency
* memory type
* domain relevance
* access frequency

to produce natural, context-aware recall.


# STAGE 7 — Add POV/Perspective Foundation to Writing Memory

## Goal

Prepare StarFur for serious continuity reasoning.

Because the novel is multi-POV, add perspective metadata before deeper narrative reasoning.

Track:

```text
perspective_type
perspective_entity
perspective_confidence
```

Perspective may be:

```text
character
location
external
narrator
unknown
```

Do not assume all POVs are characters.

This lays the groundwork for:

```text
world truth
reader knowledge
character knowledge
```

Do NOT attempt full character-knowledge propagation yet.

---

# STAGE 8 — Add Basic Model Routing

## Goal

Stop requiring one model to be good at everything.

This is application-level MoE routing.

Architecture:

```text
USER
  ↓
Router
  │
  ├── general conversation
  ├── memory question
  ├── writing/lore
  ├── coding
  └── deep reasoning
```

Initial router can itself be a tiny model or deterministic classifier.

Do not overengineer it.

---

## 8.1 First Specialist: Coding

Coding is the perfect first demonstration.

Flow:

```text
User:
"Fix this StarFur parser problem."

Persona/router
      ↓
detect coding task
      ↓
retrieve StarFur project memories
      ↓
coding model
      ↓
technical result
      ↓
persona model
      ↓
in-character answer
```

The specialist does not need the persona.

The persona does not need elite coding ability.

The user experiences one assistant.

---

## 8.2 Model Configuration

Models must be configurable.

Example:

```text
router_model
persona_model
memory_model
coding_model
reasoning_model
embedding_model
```

Never hardwire StarFur around one specific local model.

---

# STAGE 9 — Create a Shared Application Layer

## Goal

Stop CLI commands, future TUI, and assistant mode from each implementing their own backend behavior.

Create shared services conceptually like:

```text
MemoryService
AssistantService
AnalysisService
RetrievalService
ModelRouter
ProjectService
```

Interfaces should return data/results rather than directly printing to terminal.

CLI becomes:

```text
CLI
 ↓
services
```

TUI becomes:

```text
TUI
 ↓
same services
```

Future web UI:

```text
Web
 ↓
same services
```

This is where Codex may deserve Luna-medium or Terra depending on complexity.

Do this only after assistant-memory behavior has become clear enough that we know what abstractions are actually needed.

---

# STAGE 10 — TUI

## Goal

Stop requiring command-fu for ordinary use.

Use something such as Textual.

Desired first screen:

```text
┌─────────────────────────────────────────┐
│              STARFUR                    │
├─────────────────────────────────────────┤
│ Chat                                    │
│ Memory                                  │
│ Projects                                │
│ Sync / Analysis                         │
│ Proposals                               │
│ Models                                  │
│ Performance                             │
│ Settings                                │
│ Exit                                    │
└─────────────────────────────────────────┘
```

Keyboard navigation:

```text
↑ ↓
Enter
Space
Esc
```

Provide:

* task progress;
* current model;
* current project;
* memory counts;
* recent failures;
* ability to inspect logs;
* ability to trigger sync;
* proposal review;
* assistant chat.

Do not put business logic into the TUI.

It calls services.

---

# STAGE 11 — Assistant Quirk Hunting

## Goal

Stop building features temporarily and actually use the assistant.

Use it for several days.

Talk about:

* work;
* StarFur;
* random interests;
* writing;
* plans;
* frustrations;
* technical problems.

Record every moment where you think:

> Why did she remember that?

> Why didn't she remember this?

> Why did she bring THAT up?

> Why did she think this old thing was still current?

> Why did she store the same memory four times?

These failures become the next development backlog.

---

# STAGE 12 — Memory Deduplication

Expected early problem:

```text
User likes dark mode.
User prefers dark interfaces.
User generally likes dark UI themes.
```

These should not necessarily become three independent permanent memories.

Add semantic/structured duplicate detection.

Possible behavior:

```text
new memory
   ↓
similar existing memory?
   │
   ├── no → insert
   │
   └── yes
        ↓
   reinforce / update / propose merge
```

Never silently merge contradictory facts.

---

# STAGE 13 — Memory Evolution

A memory should be updateable.

Example:

Old:

```text
User currently works on Project A.
```

Later:

```text
User stopped Project A and moved to Project B.
```

Do not simply maintain both as equally current facts.

Eventually support:

```text
active
superseded
historical
uncertain
```

This becomes crucial for a long-lived assistant.

---

# STAGE 14 — Salience and the Proto-Synaptic Layer

Only after retrieval works reliably.

Add derived weights such as:

```text
importance
recency
frequency
emotional salience
association strength
```

These weights influence recall.

They are NOT truth.

Concept:

```text
Memory A ←0.91→ Memory B
Memory A ←0.43→ Memory C
```

Strong association means:

> these memories are often relevant together

not:

> these facts are canonically connected.

Eventually support spreading activation:

```text
StarFur project
    ↓
activates:
Codex
Python
local AI
memory architecture
```

This is the beginning of the synaptic layer.

---

# STAGE 15 — Assistant Behavioral Continuity

Now refine persona continuity.

Separate:

```text
Personality
Relationship state
Current mood/presentation
Memory
Knowledge
```

Memory should influence responses.

It should not rewrite the persona prompt.

Example:

```text
Persona:
supportive fox

Memory:
user had a rough shift yesterday
```

Response behavior may become gentler because of retrieved context.

But the durable persona remains independently configured.

---

# STAGE 16 — Prototype Acceptance Test

The prototype is considered successfully “fully stacked” when all of the following work.

## Persistent Conversation

Close StarFur.

Restart it.

Ask:

> “What were we talking about yesterday?”

It can retrieve meaningful context.

---

## Selective Memory

Tell it:

> “Remember that I prefer X.”

Restart.

It remembers X.

Tell it:

> “Forget X.”

It removes/supersedes the memory.

---

## Natural Recall

Mention something indirectly related to an older memory.

The relevant memory appears naturally without manually searching for it.

---

## Personal Context

Describe a frustrating event.

Later reference it indirectly.

The assistant understands what you mean.

---

## Project Context

Discuss an ongoing project.

Later return to the project without restating its entire history.

StarFur retrieves useful project state.

---

## Writing Context

Ask a question about the loaded writing project.

StarFur retrieves structured and semantic project memory without contaminating it with personal memory.

---

## Specialist Routing

Ask for coding help.

The request reaches the configured coding specialist.

The result returns through the persona.

From the user's perspective, the same assistant handled the whole interaction.

---

## Inspectability

You can inspect:

* stored memories;
* memory type;
* importance;
* provenance;
* creation/update time;
* retrieval behavior.

---

## Safety

The assistant cannot:

* execute unrestricted shell commands;
* silently promote arbitrary memories into authoritative project canon;
* destroy databases because annotation failed;
* mix personal memory with fictional canon accidentally.

---

# Suggested Seven-Day Development Cadence

This is flexible. Do not force a calendar milestone if an earlier stage reveals a real architectural problem.

## Day 1 — Reliability + Knowledge Quality

Finish the current annotation repairs.

Validate:

* failed sources;
* fact types;
* diagnostics;
* proposal quality.

Codex tasks:

* diagnostics;
* proposal normalization;
* database/schema hygiene.

---

## Day 2 — Assistant Memory Schema

Create:

* personal memory tables;
* memory namespaces;
* retention/importance metadata;
* migration tests.

Build basic memory CRUD operations.

---

## Day 3 — Conversational Assistant

Create:

* assistant entrypoint;
* persona configuration;
* recent-session context;
* semantic + structured retrieval before responses.

At the end of Day 3, try to have the first conversation with persistent recall.

This is the first **“holy shit, it remembers”** milestone.

---

## Day 4 — Selective Memory

Build:

* memory proposal logic;
* conservative automatic memory policy;
* explicit remember/forget;
* personal Chroma namespace;
* duplicate checks.

Spend part of the session actually talking to it.

---

## Day 5 — Routing + Specialist Models

Add:

* intent router;
* configurable models;
* coding specialist;
* persona rephrasing/presentation layer.

Test:

```text
casual conversation
→ persona

coding
→ coding specialist
→ persona

writing
→ project memory
→ persona
```

---

## Day 6 — Service Layer + TUI

Extract enough common application logic for:

* CLI;
* assistant;
* TUI.

Build first Textual control center.

Prioritize function over appearance.

---

## Day 7 — Abuse the Prototype

Do not spend the entire day coding.

Use it.

Try to break memory.

Talk naturally.

Switch topics.

Return to old topics.

Correct it.

Forget things.

Ask about projects.

Ask for code.

Ask about the novel.

Write down every shitty behavior.

Then turn those observations into:

```text
POST-PROTOTYPE QUALITY BACKLOG
```

---

# Codex Usage Strategy

## Luna / Light

Default for:

* schema additions;
* migrations;
* tests;
* diagnostics;
* one-feature implementations;
* CLI commands;
* individual TUI components;
* validation;
* config changes;
* documentation.

## Luna / Medium

Use for:

* multi-module assistant-memory work;
* routing;
* larger retrieval changes;
* service extraction.

## Terra

Reserve for:

* architecture audits;
* mysterious cross-system bugs;
* major refactors;
* cases where Luna identifies uncertainty or interacting architectural problems.

Do not pay Terra to change six lines.

---

# Git Discipline

Every meaningful feature:

```text
implement
   ↓
tests
   ↓
manual sanity check
   ↓
CHANGELOG
   ↓
commit
   ↓
push
```

Push to GitHub frequently.

Do not let a full evening of good work exist only inside the WSL VHD.

---

# Development Rule

At every stage ask:

> Is this data authoritative, derived, temporary, or presentation-only?

Those four categories should never be casually mixed.

### Authoritative

Human-confirmed project knowledge.

### Derived

AI-extracted facts, associations, rankings.

### Temporary

Session state, current mood, temporary observations.

### Presentation

Persona wording, animation, voice, emotional expression.

Keeping those distinctions clean will prevent an enormous class of future bugs.

---

# The Prototype We Are Actually Building

By the end of this sprint, the desired experience is roughly:

```text
You:
"Work was fucking awful."

Fox:
responds naturally
    ↓
recognizes potentially useful personal experience
    ↓
stores/selectively summarizes it
```

Later:

```text
You:
"I'm already annoyed and I haven't even gone in yet."

Fox:
retrieves the relevant earlier work context
    ↓
responds with continuity
```

Then:

```text
You:
"Anyway, look at StarFur's parser."

Fox:
retrieves project context
    ↓
routes coding request
    ↓
coding specialist works
    ↓
result returns to persona
    ↓
fox responds normally
```

Then:

```text
You:
"Did we establish whether this character knows X yet?"

Fox:
switches retrieval domain
    ↓
uses writing-project structured + semantic memory
    ↓
eventually POV/knowledge-state reasoning
    ↓
answers with provenance
```

The surface experience is:

> **one persistent assistant**

The architecture underneath is:

```text
Persona
   │
Router
   │
   ├── Memory
   │    ├── SQLite
   │    └── Chroma
   │
   ├── Projects
   │
   ├── Specialist Models
   │
   └── Tools
```

That is the week-one destination.

Everything beyond it—voice, desktop avatar, synaptic memory, sophisticated emotional modeling, autonomous tools, web dashboard, Live2D/3D—is iteration on top of a functioning cognitive core.

## Definition of Victory

At some point this week, you should be able to restart the program, talk to your fox, casually reference something from an earlier conversation, and have her correctly understand what you're talking about without you manually feeding that history back in.

At that moment:

**StarFur has crossed from a collection of AI tooling into a persistent assistant.**

# Advanced Companion / Character Cognition

This phase begins only after the core Assistant Mode pipeline is stable: structured personal memory, semantic recall, proposal/approval policy, session handling, model routing, and reliable provenance.

The objective is to evolve StarFur from a persistent assistant into a general-purpose framework for persistent characters with individual history, perspective, emotional state, relationships, and controlled personality development.

## 1. Subjective / Reconstructive Memory

Introduce a subjective memory layer above immutable evidence and authoritative knowledge.

StarFur should distinguish between:

1. **What happened** — immutable source events, conversations, observations, and provenance.
2. **What the persona remembers** — the persona's current reconstruction of those events.
3. **What the persona inferred** — interpretations and patterns derived from memories.
4. **How the persona feels about it** — affective associations attached to those memories.

Subjective memories may reconsolidate when recalled. A persona therefore normally remembers the latest reconstruction of a memory rather than repeatedly reconstructing directly from the original event.

Example:

Original evidence:

> User had a stressful shift because the workplace was understaffed.

Initial memory:

> User was frustrated by an understaffed shift.

Later reconstruction:

> Understaffed shifts seem especially frustrating to the user.

Later pattern:

> The user appears more frustrated by disrupted workflow than by difficult work itself.

Every reconstruction must retain a provenance chain back to previous revisions and ultimately the original evidence.

**Critical invariant:** subjective memory must never overwrite or corrupt ground truth.

This creates human-like imperfect memory while preserving machine-level auditability.

Different memory classes should reconsolidate differently. Durable facts should resist mutation. Episodic, emotional, relationship, and interpretive memories may evolve substantially.

---

## 2. Synaptic / Associative Memory Layer

Add an optional third memory system connecting structured and semantic memory.

Associations may track:

* related memories;
* people;
* places;
* topics;
* emotions;
* events;
* concepts;
* projects;
* relationship context.

Potential properties include:

* activation strength;
* salience;
* rehearsal/recall count;
* last activation;
* emotional weight;
* contradiction pressure;
* confidence;
* decay;
* association direction/weight.

Recall should be capable of activating related memories rather than retrieving each memory independently.

Repeated recall may strengthen associations while unused associations may gradually lose retrieval priority without deleting underlying evidence.

This layer should support the subjective-memory system by allowing the persona's history to develop interconnected patterns rather than remaining a collection of independent facts.

---

## 3. Affective State

Introduce persistent but dynamic emotional state separately from authoritative memory.

Avoid hardcoding emotions as permanent SQL columns. Use extensible state definitions and values.

Potential initial dimensions:

### Fast-changing state

* happiness;
* sadness;
* anger;
* stress;
* excitement;
* embarrassment;
* curiosity;
* playfulness;
* energy.

### Slow-changing relationship state

* affection;
* trust;
* comfort;
* familiarity;
* attachment;
* resentment.

Multiple apparently contradictory states must coexist. A persona may simultaneously have high affection and high anger toward someone.

State changes should primarily result from interpreted events rather than direct LLM manipulation of arbitrary values.

Example:

```text
dismissive comment
→ hurt +0.15
→ anger +0.10
→ happiness -0.08
→ trust -0.01
```

Short-lived affect should decay toward persona-specific baselines over time. Relationship variables should change substantially more slowly.

Current affect, retrieved memories, relationship state, persona, and current interaction should jointly influence generation.

The model should not normally expose numerical state values directly to the user.

---

## 4. Dynamic State Vocabulary

Do not assume developers can enumerate every useful psychological state in advance.

Represent emotional and behavioral dimensions as data rather than schema columns.

A persona may eventually determine that its existing state vocabulary cannot adequately represent a recurring experience and propose a new state dimension.

Example:

> Existing sadness/stress/anger dimensions do not adequately represent recurring embarrassment responses.

The persona may propose:

```text
state_name: embarrassment
category: mood
baseline: low
decay: moderate
reason: recurring reactions are poorly represented by existing dimensions
confidence: high
```

Application code validates the proposal.

Initially, human approval is required before adding the new dimension. Future conservative auto-approval may be considered.

The LLM must never independently execute arbitrary SQL schema migrations.

Possible state categories:

* mood;
* relationship;
* drive;
* social;
* self-model.

This allows a persona's psychological vocabulary itself to evolve through experience.

---

## 5. Perspective

Subjective memory + associations + affect should produce persistent perspective.

A persona should be capable of forming interpretations such as:

> The user does not seem to dislike difficult work itself; repeated interruptions to their workflow appear to frustrate them more.

StarFur must explicitly distinguish:

* fact;
* memory;
* inference;
* opinion;
* emotional reaction.

Corrections should not simply erase previous interpretations.

Example:

```text
Persona believed X
→ user corrected X
→ persona revised belief toward Y
```

The fact that the persona previously misunderstood something may itself become part of its history.

This creates continuity of interpretation rather than simple fact replacement.

---

## 6. Persona Evolution / Self-Model

The initial persona file is a seed, not necessarily a permanently frozen personality.

After sufficient interaction history exists, a persona may propose changes to mutable aspects of itself based on accumulated experience.

Examples:

* becoming more direct during technical discussions;
* reducing repetitive affectionate gestures;
* developing stronger interest in a topic frequently shared with the user;
* changing conversational habits;
* adjusting behavioral preferences;
* revising its self-description.

Persona evolution should follow:

```text
persona seed
→ experiences
→ subjective memory
→ reflection
→ proposed self-change
→ sandbox evaluation
→ approval
→ stable persona revision
```

Core safety rules, permissions, provenance requirements, and immutable system constraints are not persona-editable.

Persona revisions must be versioned and reversible.

---

## 7. Controlled Self-Modification Sandbox

Allow personas eventually to propose modifications to their own behavior and possibly StarFur functionality without direct production access.

Use an isolated workflow:

```text
Stable Persona
→ clone state
→ Experimental Persona
→ apply proposed changes
→ behavioral evaluation/tests
→ compare against stable
→ human approval
→ promotion or rejection
```

For code-level self-modification:

```text
Persona identifies problem
→ creates engineering proposal
→ specialist coding model receives isolated branch/worktree
→ implementation
→ automated tests
→ diff/review
→ human approval
→ merge
```

The assistant must not directly rewrite production code, remove audit history, alter permissions, or bypass validation.

The objective is controlled self-improvement, not unrestricted self-modification.

---

## 8. Multi-Persona Architecture

Generalize Assistant Mode so StarFur can host multiple persistent personas.

Each persona receives a stable `persona_id` and independent mutable state.

Conceptually:

```text
persona/
├── murr/
│   ├── persona.md
│   └── config.json
├── maeve/
│   ├── persona.md
│   └── config.json
└── another-persona/
    ├── persona.md
    └── config.json
```

A persona registry should eventually track:

* persona ID;
* display name;
* persona/config paths;
* preferred model;
* enabled state;
* memory configuration;
* affect configuration;
* subjective-memory configuration;
* creation metadata.

Not all information should be duplicated into isolated databases.

Prefer namespaces/domains allowing:

* shared objective knowledge;
* persona-private knowledge;
* persona-specific subjective memories;
* persona-specific affect;
* persona-specific relationship state.

This allows two personas to experience the same event while remembering and interpreting it differently.

The persona must remain independent of the inference model.

**The LLM is not the character.**

The persistent character consists of persona configuration, memories, associations, relationship history, affective state, subjective interpretations, and accumulated development.

Models are interchangeable cognitive engines used to reason and generate responses.

This allows future model upgrades while retaining character continuity:

> Same character, better brain.

---

## 9. Character-to-Character Interaction

Allow multiple personas to converse with one another through a controlled conversation orchestrator.

A conversation session should contain:

* participants;
* shared recent transcript;
* topic/context;
* maximum turns;
* speaker-selection policy;
* termination conditions;
* user interruption support.

Avoid uncontrolled recursive conversations.

Possible termination conditions:

* topic resolved;
* no participant has sufficient activation to continue;
* maximum turn count reached;
* user interrupts;
* explicit stop request.

Speaker selection may initially use deterministic round-robin behavior and later use relevance, affective activation, interest, or conversational intent.

After a shared conversation, each participant independently processes the interaction.

Example:

Objective event:

> Murr and Maeve disagree about a decision.

Murr's memory:

> Maeve was being excessively cautious.

Maeve's memory:

> Murr dismissed a legitimate risk.

The same conversation therefore produces different subjective memories.

Private information must remain private unless explicitly communicated between characters.

If Persona A tells Persona B information originally learned from the user, Persona B's provenance should identify Persona A as the immediate source rather than falsely recording direct user evidence.

This permits organic information propagation, disagreement, differing confidence, and even gossip while retaining provenance.

---

## 10. Generated Prehistory

Allow personas to enter the system with a procedurally generated personal history rather than beginning existence at first user interaction.

The persona definition acts as constraints/seed material.

Generation pipeline:

```text
persona seed
→ broad life history
→ significant events
→ relationships
→ consequences
→ subjective memories
→ associations
→ preferences
→ affective baselines
→ initial self-model
→ first user interaction
```

Do not generate only a large prose biography.

Generate structured events first, then derive memories and consequences.

Potential historical domains:

* family;
* childhood;
* education;
* friendships;
* work;
* relationships;
* hobbies;
* successes;
* failures;
* losses;
* formative experiences;
* unresolved situations.

Important events may recursively generate related people and sub-events.

Example:

```text
Moved to a new city
├── struggled at new school
├── met close friend
│   └── friend introduced persona to astronomy
└── developed reluctance to ask others for help

Years later:
friend moved away
→ astronomy retains emotional association with friend
```

This gives preferences historical causes instead of representing everything as arbitrary traits.

---

## 11. Latent Prehistory and Discovery

Not every generated historical memory should be included in the active persona prompt.

Some memories should remain latent until semantic/associative retrieval activates them.

This allows the user to gradually discover the character's history through interaction.

Example:

Weeks after first meeting, the user asks about childhood friendships.

A relevant pre-user memory activates for the first time.

From the user's perspective, the character reveals something that existed before the question rather than generating a biography on demand.

This is important for creating the impression of a character who had a life before meeting the user.

---

## 12. Seeded and Reproducible Character Generation

Procedural prehistory must be reproducible.

Each generated persona should have a stable history-generation seed.

Same seed + same generator version should reproduce the same objective history.

This supports:

* debugging;
* testing;
* rerolling characters;
* games;
* large NPC populations;
* deterministic saves;
* historical regeneration.

Generation depth may eventually support presets such as:

```text
light
standard
deep
dwarf_fortress
```

Generation should create objective prehistory separately from subjective memory.

A generated event may therefore have:

```text
OBJECTIVE HISTORY
what happened

SUBJECTIVE MEMORY
what the persona remembers

SELF-MODEL CONSEQUENCE
what the persona concluded about itself/world

AFFECTIVE CONSEQUENCE
how the experience shaped emotional baselines
```

---

## 13. Game / NPC Backend

Design these systems generically enough that Assistant Mode is only one consumer.

The same cognitive substrate could support persistent game characters, party members, NPCs, and dating-sim characters.

A game integration could provide objective events:

```text
player abandoned prisoner
party escaped safely
NPC witnessed decision
```

Each observing NPC independently processes the event according to:

* personality;
* existing memories;
* relationships;
* values;
* current affect;
* associations.

Instead of:

```text
NPC_DISAPPROVAL = -5
```

the NPC may form:

```text
"He prioritizes protecting the group over helping outsiders when the two conflict."
```

Another NPC observing the same event may conclude:

```text
"He made a difficult decision that got everyone home alive."
```

This enables characters to disagree because of persistent perspective rather than scripted dialogue branches.

Authored games should retain deterministic control over world state, critical narrative facts, safety boundaries, and major story beats. StarFur provides cognitive continuity and connective dialogue rather than replacing authored narrative design.

---

## 14. Relationship Histories Rather Than Relationship Scores

Relationship statistics should describe current state but not replace historical context.

Two characters may both have:

```text
affection = high
```

while reaching that state through completely different histories.

One relationship may develop through kindness and emotional intimacy.

Another may develop through teasing, conflict, apology, reconciliation, and shared adversity.

Their behavior should differ because memory history differs even when current numerical state is similar.

Relationship behavior should therefore derive from:

```text
current relationship state
+
shared memories
+
subjective interpretations
+
current affect
+
persona
```

rather than a single affection meter.

---

## 15. Architectural Principle: Persistent Character Identity

Long-term, StarFur should treat the character as persistent state independent of any specific LLM.

A persona's continuity consists of:

* identity/persona seed;
* objective history available to them;
* subjective memories;
* semantic knowledge;
* associations;
* affective state;
* relationship history;
* preferences;
* self-model;
* personality revisions;
* provenance.

The inference model is replaceable infrastructure.

This permits upgrading or routing between models without resetting the character's identity or history.

The long-term objective is therefore not merely:

> an LLM that remembers the user.

It is:

> a persistent character whose accumulated history affects what they remember, how they interpret events, how they feel, what they believe, how they relate to others, and potentially how they choose to develop over time.

All advanced systems must preserve StarFur's existing core philosophy:

**LLMs propose and interpret; deterministic systems validate and persist; provenance remains recoverable; irreversible operations require explicit authorization.**
