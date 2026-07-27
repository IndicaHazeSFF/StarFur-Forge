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

# STAGE 3 — Selective Memory Writing

## Goal

The assistant decides which conversational information may be useful later.

This is the critical assistant-memory feature.

Do not embed the complete conversation automatically.

Flow:

```text
USER MESSAGE
     ↓
conversation model
     ↓
memory proposal
     ↓
validation/policy
     ↓
SQLite / Chroma / both / neither
```

## 3.1 Memory Proposal Schema

The model should return or separately produce something conceptually like:

```json
{
  "store": true,
  "summary": "User prefers dark interfaces.",
  "memory_type": "preference",
  "retention": "long_term",
  "importance": 0.72,
  "confidence": 0.95,
  "semantic_memory": true,
  "structured_memory": true
}
```

The model does NOT receive unrestricted database access.

It proposes.

StarFur validates and writes.

---

## 3.2 Initial Memory Policy

Store information when it is likely to matter later.

Good candidates:

* durable preferences;
* ongoing projects;
* significant experiences;
* goals;
* recurring situations;
* relationships;
* user corrections;
* important decisions.

Usually reject:

* greetings;
* filler;
* jokes with no lasting relevance;
* temporary wording;
* routine acknowledgements;
* random conversational fragments.

Example:

```text
"Work was horrible tonight because my manager kept moving me
between stations and I couldn't finish anything."
```

Could become:

```text
Experience:
User had a frustrating work shift involving repeated station changes.

Possible associated topic:
work frustration
```

Not:

```text
User said "fuck this place" at 1:43 AM.
```

unless there is a reason that exact wording matters.

---

## 3.3 Human Control Initially

Start conservative.

Provide something equivalent to:

```text
Memory policy:
OFF
CONSERVATIVE
BALANCED
AGGRESSIVE
```

Prototype default:

```text
CONSERVATIVE
```

Also support:

```text
remember this
forget this
```

Explicit user commands override automatic policy.

---

# STAGE 4 — Write to Both Memory Systems

## Goal

Use SQLite and Chroma for what each is good at.

## Structured Assistant Memory — SQLite

Use for:

* explicit facts;
* preferences;
* projects;
* goals;
* durable experiences;
* metadata;
* retention;
* importance;
* provenance.

SQLite answers:

> What do I explicitly know?

---

## Semantic Assistant Memory — Chroma

Use for:

* conversational episodes;
* fuzzy recollection;
* broader context;
* associated language;
* experiences whose exact structured representation is insufficient.

Chroma answers:

> What past material seems relevant to this conversation?

---

## Combined Example

Conversation:

```text
"I've been messing with StarFur every night after work
because I really want this assistant prototype finished."
```

SQLite:

```text
Goal:
Finish functional StarFur assistant prototype.

Project:
StarFur

Importance:
high
```

Chroma:

```text
semantic episode containing the surrounding discussion
```

Later:

```text
"I'm tired but I still want to work on the fox."
```

Semantic retrieval finds the prior context.

SQLite confirms StarFur is an active important goal.

The persona receives both.

---

# STAGE 5 — Memory Retrieval Before Every Response

## Goal

Make memory naturally useful.

Pipeline:

```text
USER MESSAGE
     ↓
query interpretation
     ↓
structured lookup
     +
semantic retrieval
     ↓
ranking/filtering
     ↓
context assembly
     ↓
persona model
```

Do not dump every known memory into context.

Retrieve only what appears relevant.

---

## 5.1 Retrieval Budget

Define an explicit context budget.

Example:

```text
Recent conversation:     X tokens
Structured memories:     X tokens
Semantic memories:       X tokens
Persona/system prompt:   X tokens
```

This prevents memory growth from eventually destroying inference efficiency.

---

## 5.2 Retrieval Ranking

Initial ranking can combine:

```text
semantic similarity
importance
recency
memory type
current project
```

Later:

```text
association strength
frequency of access
emotional salience
persona interest
```

This is the eventual foundation for the proposed synaptic layer.

Do NOT implement full synaptic memory yet.

---

# STAGE 6 — Memory Inspection and Correction

## Goal

Never create a black-box memory assistant.

Provide commands roughly equivalent to:

```text
memory list
memory search
memory show
memory forget
memory correct
```

Eventually:

```text
memory why
```

could explain:

```text
Retrieved because:
semantic similarity: 0.84
importance: 0.76
project match: StarFur
```

### Acceptance criteria

You should always be able to answer:

> What does she remember?

> Why does she remember it?

> Where did it come from?

> How do I correct it?

---

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
