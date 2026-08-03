# StarFur Forge Roadmap v4

**Status:** Resident Intelligence Platform with an executable Persona Runtime
**Last updated:** 2026-08-03

`ROADMAP.md` is authoritative. `ROADMAP.v3.md`, `ROADMAP.v2.md`, and `ROADMAP.original.md` are preserved historical versions.

## Mission

StarFur Forge is a local-first Resident Intelligence Platform: a persistent environment where one or more companions remember responsibly, develop bounded interests and skills, perceive the user's world with permission, and assist through transparent state, tools, and providers.

The language model is a replaceable reasoning provider. The companion is the continuity system around it. A persona is not a giant prompt; it is a validated runtime whose current state is rendered into model context.

## Core architecture

```text
Shared environment
        |
StarFur Core
  |-- memory, provenance, retrieval, associations
  |-- Persona Runtime
  |     |-- static identity
  |     |-- dynamic personality
  |     |-- momentary state
  |     |-- behavior and attention rules
  |     |-- context renderer
  |-- providers and capability routing
  |-- tools, permissions, scheduler, learning sandbox
  |-- vision, media, resident apartment state
        |
Presentation clients
  |-- terminal / OpenWebUI / API
  |-- future TUI / dashboard / desktop apartment / phone / Steam
```

## Architectural invariants

- Persona, memory, policy, retrieval, providers, tools, and presentation remain separate concerns.
- Persona configuration is declarative and validated by default; user-provided files do not execute arbitrary code.
- Static identity is stable and user-controlled. Dynamic traits change slowly through explicit, explainable transitions. Momentary state can change per turn and decays or expires.
- State never silently rewrites canonical memories. Learning records observations, evidence, outcomes, and confidence separately from source memories.
- Only bounded, relevant state is rendered into model context. The model never receives an unbounded internal database or hidden chain of thought.
- Behavior rules may shape tone, attention, initiative, examples, and interaction style; engine policy still controls factual grounding, safety, provenance, and permissions.
- Autonomous work requires a sandbox, resource limits, logs, and user-visible outcomes. No background task may change production files, memories, or external systems without permission.
- Shared core memory can serve multiple personas. Persona-specific state is namespaced and does not alter shared factual truth.
- Tests use temporary SQLite, fake providers, fake collections, and deterministic clocks where possible.

## Completed foundation

### Manuscript and Crown of Claws

- **COMPLETED:** Prechunker-generated `canon/chapters/**/*.md` is the authoritative structured-analysis corpus.
- **COMPLETED:** Prechunker -> Mr. Chonker -> Mr. Annotator with defensive chunking, nested validation, bounded output, retries, and failure isolation.
- **COMPLETED:** Source cleanup, provenance preservation, fact durability classification, conservative ownership, semantic index invalidation, and targeted chapter reanalysis.
- **COMPLETED:** Crown of Claws structured entities, appearances, facts, proposals, aliases, canon export, and existing incremental sync behavior.

### Shared memory and retrieval

- **COMPLETED:** Additive domains, separate lore/assistant memory, assistant CRUD, validated types/retention/status, provenance, soft forgetting, correction, and compact public references.
- **COMPLETED:** Durable proposals with review lifecycle, evidence, approval linkage, exact-evidence identity, reinforcement, duplicate-evidence idempotency, inspection, and bulk approval confirmation.
- **COMPLETED:** Domain-scoped association graph with explainable one-hop retrieval context.
- **COMPLETED:** Deterministic retrieval, diagnostics, benchmark fixtures, evaluation metrics, and fixture-only semantic/hybrid adapters.
- **COMPLETED:** Conversational memory introspection limited to active canonical memories and approved provenance.

### Runtime and presentation

- **COMPLETED:** File-backed persona layer with neutral fallback and separate engine policy.
- **COMPLETED:** Read-only ContextManager, bounded session context, streaming, clean interruption rollback, context statistics, phase timing diagnostics, and runtime model selection.
- **COMPLETED:** Validated Ollama generation options, user-observation-only proposal provenance, and speculative-statement safeguards.
- **COMPLETED:** Ollama `ChatProvider` boundary with legacy fake-client compatibility.
- **COMPLETED:** Local OpenAI-compatible API and functional OpenWebUI integration.
- **COMPLETED:** Confirmation-gated factory reset/restore with backup safeguards and lore/assistant separation.

## The Persona Runtime

The current persona file is a compatibility input. The target architecture is a runtime that computes behavior context from three state layers:

### 1. Static identity

Slow-changing, explicitly configured facts such as name, species, core values, ethics, boundaries, relationship framing, and stable speech identity. Static identity is not rewritten by ordinary conversation.

### 2. Dynamic personality

Slowly changing traits such as interests, habits, relationship familiarity, trust, skill confidence, preferences, curiosity, and communication tendencies. Every change requires a source, reason, timestamp, bounded rate of change, and inspectable history.

### 3. Momentary state

Short-lived state such as mood, energy, attention, current activity, focus, urgency, social availability, and emotional response. Momentary state is derived from recent events and context, decays, and must not become permanent memory without an explicit observation/proposal path.

The runtime produces a `BehaviorContext`, not a final answer:

```text
identity + dynamic traits + momentary state + active memories
        |
attention selection and behavior rules
        |
compact model context packet
        |
ContextManager -> provider
```

Behavior rules may select warmth, verbosity, humor, curiosity, interruption style, examples, and clarifying-question behavior. They must not override engine policy, invent facts, expose private state, or mutate canonical memory.

## Revised implementation order

### Stage 1 - Persona Runtime compatibility foundation

1. **NEXT:** Define validated `PersonaState`, `DynamicTraits`, `MomentaryState`, and `BehaviorContext` structures.
2. Load the current persona file into static identity plus compatibility speech/style fields; preserve current Murr output as closely as possible.
3. Add deterministic state-to-context rendering behind the existing `ContextManager`.
4. Add bounded state snapshots and read-only `persona inspect` diagnostics.
5. Keep current prompt output stable while migrating callers incrementally.

### Stage 2 - Shared application boundary

1. Define application/service primitives for chat turns, retrieval, introspection, proposals, context diagnostics, and model selection.
2. Make CLI, OpenWebUI API, future Textual TUI, and dashboard call those primitives rather than duplicating orchestration.
3. Add provider health, capability, latency, model, fallback, and lifecycle diagnostics.
4. Preserve the local-first `ChatProvider` boundary and fake-provider tests.

### Stage 3 - Interests, attention, and verified learning

1. Add namespaced interest and skill state with bounded confidence, evidence, recency, and decay.
2. Define attention rules: relevant interests may influence examples, analogies, follow-up questions, and optional topics without hijacking the user's request.
3. Add explicit learning records separate from canonical memories: source, hypothesis, attempt, result, test evidence, and confidence update.
4. Add RSS/reference intake as an event source; reading an article may raise curiosity, but does not automatically establish expertise.
5. Add a local learning sandbox for bounded exercises, compilation/tests, timeout, filesystem/network permissions, and user-visible reports.
6. Never allow background learning to modify production projects or claim skill without verification.

### Stage 4 - Derived emotion, relationships, and behavior

1. Add a derived emotional-inference layer from interaction, current situation, relationships, and relevant memory associations.
2. Store bounded explainable state snapshots or observations—not arbitrary emotion weights on every memory.
3. Add relationship state such as familiarity and trust as derived, inspectable traits; canonical facts remain separate.
4. Map state to behavior controls: tone, warmth, humor, initiative, patience, verbosity, interruption, and clarification thresholds.
5. Add decay, hysteresis, and conservative transitions to prevent emotional oscillation or persona drift.

### Stage 5 - Multiple personas and discussion sandbox

1. Allow multiple declarative persona packages to share core memory, providers, tools, and permissions.
2. Namespace persona-specific dynamic traits, interests, skills, relationships, and apartment state.
3. Add confidence-based knowledge visibility: a persona may know a shared memory only when its access/confidence policy allows it.
4. Build a deterministic discussion sandbox with temporary shared memory, seeded events, multiple personas, replay, metrics, and bounded turns.

### Stage 6 - Tools, perception, and resident environment

1. Add structured tool registry and permission engine with allow-once, always-allow, deny, and confirmation-required policies.
2. Add one-shot `VisionProvider` screen/window/region/image/PDF inspection.
3. Add image, speech, and media provider interfaces and explicit capability routing.
4. Build the low-resource apartment as a state visualization: workbench for active projects, bookshelf for installed models, newspaper for feeds, calendar for schedule, window for permissioned desktop state, and frames for artwork.
5. Keep generated/procedural placeholder assets replaceable by commissioned art through stable asset IDs.

### Stage 7 - Resident intelligence and Crown of Claws writing mode

1. Add scheduler/watchers with explicit permissions and bounded resource targets.
2. Add workshop packaging for personas, interests, skills, apartments, voices, animation, and tools.
3. Add mandatory manuscript POV/perspective metadata for the three main characters, Murr, Quiet Accord, and third-party viewpoints.
4. Add character knowledge-state, revelation, timeline, contradiction, and continuity analysis.
5. Add writing-partner mode after assistant-mode and shared-service validation.

## Capability provider interfaces

```python
class ChatProvider(Protocol):
    def complete(self, messages, *, model=None, options=None, stream=False): ...

class VisionProvider(Protocol):
    def inspect(self, image, *, prompt=None, model=None, options=None): ...

class ImageProvider(Protocol):
    def generate(self, prompt, *, model=None, options=None): ...

class SpeechProvider(Protocol):
    def transcribe(self, audio, *, model=None, options=None): ...
```

Ollama is the current chat/embedding implementation. LM Studio, hosted APIs, llama.cpp, ComfyUI, Stable Diffusion, TTS, and STT should be adapters rather than special cases in the core.

## Evaluation, observability, and research instrumentation

This stage begins after the provider registry and routing layer are functional and stable. Instrumentation exists to answer engineering and research questions, not to collect data for its own sake.

### Useful measurements

- routing classification accuracy, route confidence, selected capability/provider/model, fallback reason, and route stability;
- prompt and completion token estimates, time to first token, provider latency, queue/load/unload time, and total turn latency;
- CPU, RAM, VRAM, temperature, and energy estimates when available;
- success, timeout, interruption, transport error, empty-output, and retry rates;
- retrieval precision/recall, irrelevant-result rate, grounding correctness, introspection correctness, and context size;
- proposal precision, approval/rejection rate, duplicate rate, reinforcement behavior, and user-correction frequency;
- learning-task completion, compile/test success, skill-confidence changes, and sandbox resource usage;
- answer-quality and persona-consistency evaluations from deterministic benchmark cases and human review.

### Experiment ledger

Add an append-only local experiment ledger with versioned structured events and aggregate reports. Every run should identify an experiment/run ID, benchmark case, configuration and policy hashes, provider/model versions, hardware profile, random seed, timestamps, outcome, and failure category. Store raw prompts/responses only when explicitly enabled and privacy-approved; aggregate metrics must remain useful without retaining unrestricted conversation content.

Required tools include deterministic benchmark suites, router decision traces, reproducible run manifests, comparison reports, and exportable research summaries. Metrics must be bounded, privacy-aware, and tied to a decision or hypothesis. This instrumentation should be reusable by routing, retrieval, Persona Runtime, autonomous learning, and the discussion sandbox.
## Future research

- Temporal and multi-hop associations after one-hop retrieval is benchmarked.
- State decay and emotional inference with explicit explanations.
- Retrieval compression only after long-duration prompt metrics justify it.
- Autonomous learning and replayable companion regression benchmarks.
- Proactive assistance and scheduling with permission.
- Native media generation and perception.
- Licensing, workshop distribution, and companion packaging.

## End state

StarFur is an operating environment for persistent AI companions. Users do not open a chatbot; they sit down at a computer where an intelligent resident already lives, remembers responsibly, develops verified interests and skills, responds through a coherent evolving personality, and remains transparent and user-controlled.