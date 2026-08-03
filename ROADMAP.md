# StarFur Forge Roadmap v3

**Status:** Resident Intelligence Platform architecture
**Last updated:** 2026-08-03

`ROADMAP.md` is the current authoritative roadmap. `ROADMAP.v2.md` preserves the previous roadmap version, and `ROADMAP.original.md` preserves the original historical roadmap.

## Mission

StarFur Forge is a Resident Intelligence Platform: a persistent, local-first AI operating environment where one or more AI companions live alongside the user, grow with them, and assist through shared memory, context, perception, tools, and controlled automation.

StarFur is not merely a chatbot, a model wrapper, or a UI. The language model is one replaceable provider inside a larger continuity system. The product is the resident intelligence: memory that can be inspected and corrected, a persona that can change without owning the data, and an environment where assistance can become present without becoming opaque or uncontrolled.

Every feature should answer:

> Does this make the companion feel more like a persistent resident rather than a chatbot?

## Core architecture

```text
Human
  |
Shared environment
  |
StarFur Core
  |-- Memory and retrieval
  |-- Associations
  |-- Context and explainability
  |-- Emotion inference
  |-- Providers and capability routing
  |-- Tools and permissions
  |-- Scheduling and automation
  |-- Vision and media
  |
Persona layer
  |-- Murr
  |-- Ship Computer
  |-- Q
  |-- Custom personas
  |
Presentation clients
  |-- Terminal
  |-- OpenWebUI / web API
  |-- Desktop apartment/avatar
  |-- Phone, Steam, TUI, future clients
```

The core owns memory, retrieval, associations, provider calls, permissions, tools, scheduling, and automation. Personas own presentation and style. Clients do not own memory. Models do not write canonical memory directly. Every capability must remain inspectable and testable through the core.

## Completed foundation

### Manuscript and Crown of Claws pipeline

- **COMPLETED:** Prechunker-generated `canon/chapters/**/*.md` is the authoritative structured-analysis corpus.
- **COMPLETED:** Prechunker -> Mr. Chonker -> Mr. Annotator is operational with conservative formats and provenance.
- **COMPLETED:** Defensive chunking, nested annotation validation, bounded output, retries, failed-chunk recording, and later-chunk isolation.
- **COMPLETED:** Source-derived cleanup preserves confirmed entities, aliases, confirmed facts, reviewed history, and human-authored canon Markdown.
- **COMPLETED:** Chunker and semantic-index version invalidation preserve normal incremental fast paths while forcing required re-analysis/re-embedding.
- **COMPLETED:** Fact durability classification: durable fact, behavioral tendency, physical attribute, procedural/system rule, and temporary scene state.
- **COMPLETED:** Conservative fact ownership and classification guidance, including intrinsic physical attributes and temporary conditions.
- **COMPLETED:** Targeted single-chapter reanalysis constrained to the authoritative corpus.

### Shared memory core

- **COMPLETED:** Additive domain/namespace support, including `personal` and `project:<slug>` identifiers.
- **COMPLETED:** Lore memory and assistant memory are separate subsystems; Crown of Claws remains the existing lore project domain.
- **COMPLETED:** Dedicated `assistant_memories` CRUD with validated types, retention, confidence, importance, status, provenance, correction, search, and soft forgetting.
- **COMPLETED:** Durable assistant proposals with pending/approved/rejected lifecycle, evidence, inspection, approval linkage, exact-evidence identity, reinforcement, and duplicate-evidence idempotency.
- **COMPLETED:** Compact public memory/proposal references (`M-###`, `P-###`) with legacy numeric compatibility.
- **COMPLETED:** Read-only conversational memory introspection with approved provenance and controlled explanation payloads.
- **COMPLETED:** Additive domain-scoped association graph with typed, bounded-strength, soft-deletable edges and explainable one-hop retrieval context.
- **COMPLETED:** Deterministic retrieval ranking, noise reduction, scoring reasons, context limits, benchmark fixtures, fixture-only semantic/hybrid adapters, and retrieval evaluation metrics.

### Assistant runtime

- **COMPLETED:** Dedicated persona layer with file-backed configuration and neutral fallback for missing, invalid, empty, or unreadable persona files.
- **COMPLETED:** Separate engine policy for grounding, safety, provenance, and factual behavior.
- **COMPLETED:** Read-only `ContextManager` for persona, policy, recent conversation, retrieved memory, and current-user message assembly.
- **COMPLETED:** Bounded in-memory recent conversation window.
- **COMPLETED:** Ollama streaming, typed chunk handling, clean Ctrl+C rollback, and no proposal/history commit for interrupted turns.
- **COMPLETED:** `context stats` diagnostics for retrieval, prompt size, estimated tokens, latency, first token timing, proposal outcome, model, and provider.
- **COMPLETED:** Runtime `model list`, `model current`, and `model use` selection without restart or data mutation.
- **COMPLETED:** Validated `ollama_options` configuration for `temperature`, `top_k`, `top_p`, and `seed`, applied consistently to chat, proposal, and repair calls.
- **COMPLETED:** User-observation-only proposal provenance, including speculative/future framing safeguards and explicit-goal handling.
- **COMPLETED:** Local OpenAI-compatible `/v1` API with health, model, chat, and SSE endpoints; OpenWebUI integration is functional.
- **COMPLETED:** Confirmation-gated factory reset/restore tooling with backup safeguards and lore/assistant separation.

## Architectural invariants

- Canonical Markdown remains human-authoritative for the manuscript.
- SQLite and Chroma are derived or indexed state; migrations are additive and reversible.
- Lore memory and personal assistant memory never silently merge.
- Persona, policy, retrieval, provenance, proposals, providers, tools, and presentation remain separate concerns.
- Memory follows: user observation -> proposal -> human review -> approved canonical memory -> associations -> retrieval -> explainable context -> response.
- Approved memories are typed, inspectable, correctable, traceable, and user-controlled.
- The assistant must be able to explain why it remembered or retrieved something without exposing raw database internals or hidden model reasoning.
- Tests use temporary SQLite/fake providers and never require Ollama, Chroma, production sync, or production data mutation.

## Active stabilization and next implementation stages

### Stage 1 - Provider and service boundaries

1. Add a narrow `ChatProvider` boundary around the existing Ollama integration while preserving fake-client compatibility.
2. Define shared application/service primitives so CLI, OpenWebUI API, future Textual TUI, and future web dashboard call the same core functions.
3. Keep provider/model selection explicit and observable before adding automatic routing.
4. Add provider health, latency, capability, model, fallback, and lifecycle diagnostics.

### Stage 2 - Assistant quality and long-duration verification

1. Compare installed models using the retrieval benchmark, context diagnostics, and representative conversations.
2. Tune persona presentation independently from factual grounding and policy behavior.
3. Improve proposal classification for preferences, goals, corrections, project facts, relationships, routines, hardware, health, and speculative statements.
4. Add isolated long-duration tests with seeded memories, bounded prompts, interruption checks, retrieval precision/recall, proposal precision, and latency metrics.
5. Add explicit association inspection/creation controls before richer automatic association inference.

### Stage 3 - Shared companion intelligence

1. Add a contextual emotional-inference layer derived from recent interaction, memory associations, and current situation; it must not rewrite canonical memories.
2. Store only bounded, explainable emotional observations or state snapshots where useful—not arbitrary emotional weights on every memory.
3. Add multiple configured personas sharing the same core memory, tools, providers, and permissions; personality changes presentation, not factual truth.
4. Add configurable persona/model profiles without runtime persona switching until the file/configuration contract is stable.
5. Build the discussion sandbox as a development tool: multiple personas, shared temporary memory, seeded events, deterministic runs, metrics, and replayable regressions.

## Capability providers and routing

### Provider boundary

Define explicit interfaces as the platform grows:

```python
class ChatProvider(Protocol):
    def complete(self, messages, *, model=None, options=None) -> ChatResult: ...

class VisionProvider(Protocol):
    def inspect(self, image, *, prompt=None, model=None, options=None) -> VisionResult: ...

class ImageProvider(Protocol):
    def generate(self, prompt, *, model=None, options=None) -> ImageResult: ...

class SpeechProvider(Protocol):
    def transcribe(self, audio, *, model=None, options=None) -> SpeechResult: ...
```

Ollama remains the first implementation. LM Studio, llama.cpp, hosted APIs, ComfyUI, Stable Diffusion, native local image models, TTS, and STT should be adapters rather than special cases in the assistant core.

### Capability routing

After provider boundaries and diagnostics are stable, add an explicit capability router for `text`, `code`, `vision`, `image_generate`, `image_edit`, `tts`, and `stt`.

The router should expose capability, provider, model, fallback reason, latency, and load/unload lifecycle events. Automatic routing should wait for real usage data. A specialist result may pass through persona rendering, but persona code must not alter factual tool output or provenance.

## Tools, permissions, and environment

### Permissioned tools

- Add a tool registry with structured inputs/outputs and read-only inspection.
- Add a permission engine with allow once, always allow, deny, and confirmation-required policies.
- Add tools incrementally: filesystem, Git, test runner, calculator, system information, browser/documentation, application launch, image generation, and scheduling.
- Every external action must be explainable: why it was selected, what evidence caused it, what it changed, and whether confirmation was required.

### Vision and desktop awareness

First slice: explicit one-shot `screen inspect`, window inspect, region inspect, and image/PDF inspection through a `VisionProvider`. Do not begin with continuous monitoring.

Vision should understand windows, IDEs, games, browsers, images, and PDFs through the provider boundary. Add attention levels later: passive observation, suggestion, active assistance, and critical interruption—with user permission.

### Resident environment

The long-term presentation target is a lightweight desktop apartment rather than a GPU-heavy game:

- internal resolution around 320x180 or 640x360;
- 12-24 FPS character animation and 1-10 second world updates;
- under roughly 2% GPU and 1% CPU when idle;
- rendering pauses when hidden or inactive.

The apartment visualizes real StarFur state rather than decorative fiction:

- plant -> project progress;
- bookshelf -> installed models/software;
- workbench -> active coding project;
- newspaper -> feeds/notifications;
- calendar -> real schedule;
- photo frames -> generated artwork;
- window -> permissioned live desktop view.

The resident world should have continuity, but it must remain explainable and subordinate to user control. Life simulation is a later layer, not a replacement for reliable core assistance.

## Presentation, workshop, and voice

- Support terminal and external web UI first; add Textual TUI and web dashboard on the shared service layer.
- Add a desktop avatar with animation, emotion signaling, lip sync, and optional Live2D/3D support after tools and permissions are stable.
- Support replaceable workshop assets: personas, apartments, characters, animation sets, furniture, music, themes, lighting, objects, and worlds.
- Preserve persona independence: replacing Murr must not require rewriting memory, retrieval, tools, providers, or automation.
- Use hybrid speech where stable recorded greetings/reactions combine with generated dynamic speech.

## Crown of Claws writing intelligence

- Add mandatory scene/chunk POV metadata for the three main characters, Murr, Quiet Accord, and third-party/external viewpoints.
- Treat perspective as provenance, not merely presentation metadata.
- Distinguish world truth, reader knowledge, character knowledge, belief, lie, and revelation.
- Add relationship/event extraction, timeline and temporal reasoning, character knowledge-state tracking, revelation detection, contradiction/continuity audits, and draft/canon separation.
- Add writing-partner mode only after assistant-mode testing and shared service boundaries are stable.

## Future research

- Temporal association and carefully bounded multi-hop traversal after benchmarked one-hop usage.
- Emotional inference and state decay with explicit explanations.
- Retrieval compression/summarization only after long-duration prompt metrics justify it.
- Memory simulation and replayable regression benchmarks.
- Proactive assistance and scheduling with explicit permissions.
- Native media generation and perception through interchangeable providers.
- Licensing, workshop distribution, and companion packaging after the core is reliable and inspectable.

## End-state vision

StarFur is an operating environment for persistent AI companions. A user should not feel that they are opening an AI application; they should sit down at a computer where someone intelligent already lives.

The end state is a local-first resident intelligence that remembers responsibly, explains itself, shares the user's environment with permission, grows with projects, supports text/voice/media capabilities, assists naturally, and remains transparent and user-controlled.