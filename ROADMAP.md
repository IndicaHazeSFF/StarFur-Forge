# StarFur Forge Roadmap v2

**Last updated:** 2026-08-01

This is the authoritative roadmap. `ROADMAP.original.md` preserves the previous roadmap text for historical reference.

## Project direction

StarFur Forge is a local-first memory and assistant engine with two closely related uses:

1. **Assistant Mode** â€” a configurable persona using personal/project memory safely and transparently.
2. **Crown of Claws Mode** â€” manuscript analysis and narrative memory for the multi-POV novel.

The engine should remain shared. Persona, domain, retrieval, provider, and policy boundaries should make the modes configurable without duplicating the core.

## Completed foundation

### Manuscript and lore pipeline

- Prechunker-generated `canon/chapters/*.md` is the authoritative manuscript analysis corpus.
- Prechunker â†’ Mr. Chonker â†’ Mr. Annotator pipeline is operational.
- Chunking and annotation have defensive validation, retries, failure recording, and regression tests.
- Structured lore memory preserves source provenance and performs normal source cleanup.
- Semantic indexing supports invalidation/version changes without destroying the normal incremental fast path.
- Targeted chapter reanalysis is available and constrained to the authoritative corpus.
- Fact durability/type classification is stored without discarding temporary scene-state facts.
- Classification guidance covers physical attributes, behavioral tendencies, temporary scene state, and subject attribution.
- Assistant/lore corpus contracts are documented separately; production data formats remain conservative.

### Shared memory and assistant memory

- Additive domain/namespace support exists, including personal and project-style domains.
- Lore memory and assistant memory are separate subsystems.
- Dedicated `assistant_memories` storage supports validated memory types, retention, confidence, importance, status, provenance, CRUD, search, correction, and soft forgetting.
- Durable assistant proposals support pending/approved/rejected lifecycle, review commands, evidence records, deterministic identity, exact-evidence idempotency, reinforcement, duplicate-evidence no-op behavior, and approval linkage.
- Proposal inspection exposes identity, provenance, evidence, and review state without mutation.
- Assistant responses are not proposal evidence by default; proposals derive from user observations and explicit remember requests.

### Assistant runtime

- ~~Local OpenAI-compatible `/v1` API adapter for external chat UIs, with health/model/chat endpoints and SSE streaming.~~ **COMPLETED 2026-08-02**
- Interactive local Assistant Mode uses Ollama with configurable model and persona.
- Persona instructions are loaded through a dedicated persona layer with neutral fallback behavior.
- Policy, persona, retrieval, provenance/introspection, and command parsing remain separate concerns.
- Recent conversation context is bounded in memory.
- Streaming output works, including clean Ctrl+C interruption and rollback of incomplete turns.
- Deterministic retrieval supports ranking, explanations, context assembly, benchmark fixtures, and read-only diagnostics.
- Conversational memory introspection can explain selected active memories and approved provenance without exposing rejected proposals or hidden reasoning.
- A read-only `context stats` command reports bounded diagnostics for the most recent turn.
- A read-only `ContextManager` assembles persona, policy, recent conversation, retrieved memory, and user-message sections while preserving the established payload format.
- Runtime Ollama model selection (`model list`, `model current`, `model use`) is the next active implementation target.
- Factory reset/restore tooling exists with confirmation and backup safeguards.

## Current stabilization priorities

1. ~~Finish and verify runtime model selection across Ollama environments.~~ **COMPLETED 2026-08-01**
2. Compare installed models using the retrieval benchmark, context diagnostics, and representative assistant conversations.
3. Improve proposal classification and quality using observed failures, without changing lifecycle or provenance semantics.
4. Run longer isolated assistant tests and record retrieval quality, proposal precision, latency, prompt size, and interruption behavior.
5. Keep the full test suite green in WSL; treat host-only filesystem failures as environment-specific until reproduced in WSL.

## Near-term assistant roadmap

### Stage A â€” Provider and context boundaries

- ~~Complete runtime model selection.~~ **COMPLETED 2026-08-01**
- Add a narrow text-provider interface after model selection is stable; preserve Ollama compatibility and fake-client tests.
- Keep ContextManager deterministic and read-only.
- Add provider/model information to diagnostics and clear unavailable-provider errors.
- Do not add automatic routing or dynamic context budgets yet.

### Stage B â€” Assistant quality

- ~~Ensure direct-answer grounding includes selected memory details and keeps persona flavor after, not instead of, the factual answer.~~ **COMPLETED 2026-08-01**
- Improve retrieval scoring and evaluation fixtures.
- ~~Add a first additive association layer for domain-scoped assistant-memory edges and explainable one-hop deterministic retrieval context.~~ **COMPLETED 2026-08-02**
- Add conservative proposal classification improvements and correction handling.
- Add optional proposal-review usability improvements.
- Test persona quality separately from factual grounding.
- Add bounded long-duration regression/simulation tests before changing retrieval algorithms.

### Stage C â€” Multiple personas and integrations

- Support multiple configured personas without runtime switching until the configuration contract is proven.
- Add LM Studio as a provider adapter if it improves accessibility for testers.
- Preserve shared memory domains and explicit provenance across personas.
- Keep persona presentation separate from factual/system policy.

## Crown of Claws roadmap

### Narrative provenance and perspective

- Add scene/chunk perspective metadata for the three main characters, Murr, Quiet Accord, and other third-party/external viewpoints.
- Treat perspective as provenance, not merely presentation metadata.
- Distinguish world truth, reader knowledge, character knowledge, belief, lie, and revelation.
- Prefer explicit manuscript metadata over inference; store uncertainty when POV is ambiguous.

### Narrative intelligence

- Relationship and event extraction with evidence.
- Timeline and temporal reasoning, including narrative versus chronological order.
- Character knowledge-state tracking and revelation detection.
- Contradiction and continuity audits.
- Writing assistance with draft/canon separation and human review.

## Platform and control center

- Shared application/service layer for CLI, future Textual TUI, and future web API/dashboard.
- Web configuration, proposal review, memory inspection, corpus status, and performance dashboards.
- Project abstraction so Crown of Claws is one project domain rather than a hard-coded engine assumption.
- Permissioned tools for files, applications, system information, and automation.
- Voice input/output and interruption-aware conversation.
- Desktop fursona with animation, emotion signaling, lip sync, and Live2D/3D support.

## Future architecture: capability routing and native media

After manual model selection, provider boundaries, and diagnostics are stable, add an explicit capability router. It should classify a request into capabilities such as `text`, `code`, `image_generate`, `image_edit`, `vision`, `tts`, or `stt`, then select a configured provider.

Use adapters, not backend-specific logic in the assistant core:

```python
class ImageProvider(Protocol):
    def generate(self, prompt, *, model=None, options=None) -> ImageResult:
        ...
```

Stable Diffusion, ComfyUI, a native local image model, and hosted APIs should be interchangeable providers. A provider may be loaded, warmed, used, and unloaded according to a configurable VRAM/lifecycle policy. Return structured artifact metadata (path/handle, provider, model, timing, and errors); do not put binary media in memory tables or prompts.

The first slice should use explicit configuration and fake-provider tests. Automatic routing should wait for real usage data and must expose capability, provider, model, fallback reason, latency, and lifecycle events. A specialist result may pass through a persona-rendering step, but persona code must not alter factual tool output or provenance.

## Future research

- Extend the completed association foundation only after benchmarked usage: temporal relationships, carefully bounded multi-hop traversal, and richer relationship provenance.
- Emotional state as a separate contextual layer, not arbitrary permanent fields on every memory.
- Discussion sandbox with seeded memories, multiple personas, scheduled events, deterministic seeds, and retrieval/proposal metrics.
- Hybrid deterministic/semantic retrieval experiments against the checked-in benchmark corpus.
- POV-aware retrieval and writing-partner mode.

## Development invariants

- Preserve authoritative manuscript Markdown and existing data formats unless a migration is explicitly planned.
- Prefer additive, reversible migrations and soft status transitions.
- Do not mutate production SQLite or Chroma during tests.
- Keep lore memory separate from assistant memory.
- Keep persona, policy, retrieval, provenance, proposal, and provider concerns separate.
- Every behavior change gets focused regression tests and a changelog entry.

## End-state vision

A persistent, local-first StarFur companion that understands fictional worlds and personal context, remembers selectively and transparently, knows why it retrieved information, supports text/voice/media capabilities through interchangeable providers, helps write and maintain narratives, and can inhabit the desktop without sacrificing inspectability or user control.