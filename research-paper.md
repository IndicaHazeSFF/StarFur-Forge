# StarFur Forge: A Local-First Resident Intelligence Architecture

**Technical research-paper draft**  
**Repository snapshot reviewed:** 2026-08-08  
**Status:** Architecture and research agenda; not a peer-reviewed evaluation report

## Abstract

Contemporary conversational systems commonly treat the language model, its context window, and an application-specific chat history as the assistant. This produces fragile continuity: identity is coupled to prompts, memory is difficult to inspect or correct, model replacement can alter apparent knowledge, and external retrieval can contaminate instructions or factual claims. StarFur Forge explores a different architecture. It treats the model as a replaceable provider inside a local-first resident-intelligence platform whose durable state, provenance, persona presentation, policy, retrieval, and user control live outside the model.

The implemented prototype includes domain-scoped structured assistant memory, durable human-reviewed memory proposals, evidence and approval provenance, deterministic explainable retrieval, bounded conversation context, persona/policy separation, structured capability self-knowledge, conversational memory introspection, a provider-neutral chat interface, CLI and OpenAI-compatible presentation surfaces, an initial reviewed external-document intake path, and early benchmark metadata/retrieval fixtures. Semantic and hybrid assistant retrievers currently exist only as injected evaluation adapters; production assistant chat remains deterministically grounded in active structured memories. The earlier manuscript/lore subsystem remains conservatively separated.

This paper describes the architecture, its invariants, the current implementation boundary, and an evaluation plan aimed at measuring whether external cognition components allow smaller local models to deliver reliable resident-assistant behavior. No production-scale or model-equivalence claim is made. Static inspection identifies two immediate requirements before broader experimentation: isolation of ephemeral state between API conversations and completion of the trusted external-document review/retrieval boundary.

## 1. Problem and motivation

### 1.1 From chatbot sessions to resident intelligence

A chatbot is usually organized around a request:

```text
system prompt + recent messages + optional retrieved text -> model -> response
```

That structure is effective for short exchanges but weak as the basis for a long-lived companion. The context window is finite, generated summaries can drift, different models interpret the same prompt differently, and users cannot easily determine why the assistant believes something. If retrieval is added without source boundaries, text from documents, tools, or a web UI can be mistaken for instructions or user-authored facts.

StarFur Forge instead defines the product as continuity around a replaceable model. The model supplies language and reasoning for a turn; the platform owns identity configuration, canonical memory, provenance, retrieval, capability truth, policy, validation, diagnostics, and approval. The long-term goal described in `ROADMAP.md` is a resident intelligence: an assistant that remains locally controlled, explainable, and persistent across model/provider changes while gradually gaining perception and permissioned action.

### 1.2 Local-first constraints

Local inference is attractive for privacy, offline operation, customization, and predictable data ownership. It also imposes constraints:

- model capacity and instruction adherence vary substantially;
- GPU memory and load time make “one large model for every task” inefficient;
- structured extraction may need different generation settings from persona-rich chat;
- performance must be visible rather than assumed;
- local services and UI adapters need clear authentication and session boundaries;
- memory must survive process restarts without becoming an opaque store of model guesses.

These constraints motivate a modular cognition stack in which deterministic application components do work that need not be repeated inside every prompt or learned by every model.

### 1.3 Research questions

The current architecture supports, but has not yet answered, the following questions:

1. How much resident-assistant reliability can external structured memory, retrieval, provenance, policy, and context assembly provide independently of model size?
2. What is the minimum local model capacity required for reliable instruction following, grounded memory use, persona adherence, and acceptable prose when the surrounding architecture is held constant?
3. When does semantic or hybrid retrieval improve paraphrase recall without increasing irrelevant context or false confidence?
4. Can proposal review and evidence identity reduce persistent-memory false positives and duplicates over long sessions?
5. Which cognition components contribute measurable gains over a raw-model baseline?

These are proposed empirical questions. The repository currently contains early measurement infrastructure, not conclusive results.

## 2. Design goals and invariants

### 2.1 Goals

StarFur Forge is designed to provide:

- persistent, inspectable memory independent of any one model;
- local-first operation with explicit external-provider boundaries;
- human control over canonical long-term user memory;
- persona portability without coupling identity to factual storage;
- explainable retrieval and provenance;
- shared backend behavior across CLI, OpenWebUI, future TUI, dashboard, and apartment;
- conservative evolution through additive migrations and regression tests;
- measurable model/provider/retrieval behavior;
- eventual support for multiple personas, tools, perception, and controlled autonomy.

### 2.2 Invariants

The current repository encodes several important invariants:

1. **Canonical memory is application-owned.** Model output is a proposal or response, not automatically a fact.
2. **User-facing proposals use user evidence by default.** Assistant-generated factual prose is not independently stored as canonical user memory.
3. **Approval remains explicit.** Conservative automatic proposal generation creates reviewable pending records; it does not silently activate them.
4. **Forgetting preserves history.** Memories transition status rather than being silently erased from the audit trail.
5. **Domains isolate memory.** `personal` and validated `project:<slug>` namespaces prevent unrelated corpora from sharing retrieval context (`pipeline/domains.py:4-12`).
6. **Persona does not own knowledge.** Style/presentation, factual policy, capability truth, and memory are separate layers.
7. **Normal assistant retrieval is deterministic.** Semantic/hybrid assistant recall remains an explicit evaluation mode until measured and authorized.
8. **External documents are untrusted input.** Their contents cannot directly select storage fields or bypass human review.
9. **Authoritative manuscript Markdown is preserved.** Lore-derived records can be rebuilt; human-authored sources and confirmed entities are not treated as disposable model output.
10. **Incremental changes preserve working formats.** Schema evolution is additive and production stores are not rebuilt merely to simplify code.

These contracts are summarized in `AGENTS.md` and represented in the database, assistant, document, and sync implementations.

## 3. Architecture

### 3.1 Layered view

The implemented and planned platform can be represented as:

```text
Presentation
  CLI | OpenAI-compatible HTTP/OpenWebUI | future TUI/dashboard/apartment
                         |
Application boundary
  AssistantApplication | capability manifest | diagnostics
                         |
Turn orchestration
  AssistantSession | commands | lifecycle | proposal workflow
                         |
Context and cognition
  ContextManager | deterministic retrieval | associations | introspection
                         |
Identity and control
  persona | policy | capability truth | future permissions
                         |
Durable state
  assistant memories | proposals | evidence | lore | future semantic sources
                         |
Replaceable providers
  Ollama chat | future LM Studio/vision/image/speech/embedding providers
```

The key design choice is that the provider is at the bottom of this control flow, not at the center of data ownership.

### 3.2 Presentation-neutral application boundary

`pipeline/application.py` describes itself as a thin application facade and owns one stateful `AssistantSession` plus shared capability and document operations (`pipeline/application.py:1-38`). Both the terminal loop and HTTP adapter can use this boundary. Access is protected by a re-entrant lock, and request-specific stream writers are restored after use (`pipeline/application.py:60-64`).

This is the correct convergence point for future frontends, but the present implementation has a limitation: the HTTP server creates a single application/session (`pipeline/api.py:347-350`). The chat endpoint extracts only the latest user message from the client payload and relies on server-held history (`pipeline/api.py:183-200`). Consequently, multiple client conversations do not yet have isolated ephemeral state. A session registry is required before the architecture can be described as multi-client.

### 3.3 Stateful turn orchestration

`AssistantSession` coordinates commands, retrieval, context construction, provider generation, streaming, interruption semantics, conversation history, proposal extraction, introspection targets, model selection, lifecycle state, and diagnostics (`pipeline/assistant.py`). The session appends an assistant message only after generation completes; interrupted output is not committed to history or passed into proposal generation. This protects durable behavior from partial streams.

The concentration of responsibilities makes the current vertical slice easy to exercise, but the class is also the primary coupling point. The repository has already begun extracting stable primitives—providers, personas, context plans, capabilities, command help, retrieval strategies, and the application facade. Further decomposition should be driven by actual alternate consumers rather than a speculative rewrite.

### 3.4 Provider abstraction and lifecycle

`pipeline/providers.py` defines `ChatProvider` with completion and model-listing behavior, an Ollama implementation, and a callable adapter used by deterministic tests (`pipeline/providers.py:17-68`). `pipeline/provider_state.py` defines an explicit lifecycle vocabulary for disconnected, connecting, loading, ready, idle, generating, streaming, cooling, unloading, and error states.

This state vocabulary can support UI animation and observability without parsing model prose. Present transitions mostly describe application-observed activity; actual model load/warm/unload detection will require provider-specific probes. Vision, image, embedding, and speech interfaces remain future work.

### 3.5 Capability truth

Personas should be able to explain StarFur without embedding an obsolete command manual. `pipeline/capabilities.py` therefore represents implemented capabilities as immutable structured objects. Relevant capability descriptions are selected for explicit capability questions and inserted into context. `pipeline/command_help.py` separately supplies deterministic command syntax.

This distinguishes conceptual self-knowledge (“I can maintain reviewed memories”) from runtime instructions (“use `proposal approve P-001`”). Adding a capability to the core can update every persona and presentation surface without editing persona prompts.

## 4. Memory and provenance

### 4.1 Domain-scoped structured memory

The assistant uses dedicated structured-memory tables rather than repurposing fictional lore facts. `assistant_memories` represents preferences, personal facts, experiences, goals, routines, project context, relationship context, ongoing situations, and other validated types. Records include domain, subject, summary/details, importance, confidence, retention, status, source, timestamps, and optional proposal origin (`pipeline/db.py:182-236`).

Retention supports session-oriented, short-term, and long-term use. Status transitions support active, forgotten/inactive, and compatible lifecycle values. Queries are domain-aware, and public CLI/API references use compact display identifiers rather than exposing assumptions about raw SQLite sequences.

Confidence and importance are ranking/context signals, not truth probabilities produced by a calibrated statistical model. Explicit user storage may legitimately enter with maximum configured confidence; inferred proposals should be treated more conservatively. The current system does not implement asymptotic belief updates or contradiction truth maintenance.

### 4.2 Durable proposals

Long-term memory candidates are stored separately from canonical active memories. A proposal contains validated memory fields plus status, identity, review metadata, and optional approved-memory linkage. Evidence rows preserve original observation text, normalized observation identity, source, and timestamps. Approval creates an active memory with `source_proposal_id` and sets the proposal's `approved_memory_id`; evidence is linked to the approved memory in the same transaction (`pipeline/db.py:1150-1164`).

Exact-evidence idempotency uses deterministic normalization and hashes. If the same factual observation is processed again, it does not add support or confidence repeatedly. A distinct observation can reinforce an existing pending proposal when identity rules align. The original proposal wording is preserved rather than overwritten by a later model paraphrase. Broad semantic equivalence is deliberately deferred because “similar name” or “similar sentence” is not sufficient evidence of identical belief.

### 4.3 Provenance and introspection

Memory provenance answers two different questions:

- **What does the active memory say?**
- **Why is it present and what evidence supported approval?**

Inspection APIs expose both through a controlled structure. Conversational questions such as “why do you remember that?” can refer to the memories selected for the last completed response. Only active canonical memories and approved provenance are exposed; rejected proposals, unrestricted raw history, database internals, and hidden model reasoning are excluded.

This is a practical alternative to asking a generative model for an unverifiable post-hoc explanation. Retrieval scores and stored provenance are application facts. The persona may express those facts naturally, but it does not invent the underlying explanation.

### 4.4 Lore separation

The earlier Crown of Claws subsystem maintains entities, aliases, appearances, facts, proposals, and canon export separately from personal assistant memory. The authoritative manuscript analysis corpus is generated under `canon/chapters/`, and derived records retain their source paths. This separation prevents fictional facts from becoming personal memories and permits future project namespaces without destructive conversion.

## 5. Retrieval and context assembly

### 5.1 Deterministic production retrieval

Normal assistant chat queries active memories within the selected domain and scores them using transparent lexical/phrase evidence plus bounded confidence, importance, and association contributions (`pipeline/db.py:905-1002`). Multi-term queries suppress weak one-token coincidences, and stable ordering makes repeated retrieval explainable.

A conceptual score can be written as:

```text
S(m, q) = L(m, q) + P(m, q) + C(m) + I(m) + A(m, q)
```

where `L` is meaningful lexical overlap, `P` is phrase evidence, `C` and `I` are bounded confidence/importance contributions, and `A` is one-hop association support. This expression describes the architecture, not a claim that the weights are optimally calibrated.

The result packet includes public memory identity, content, score, and reasons. Diagnostics can therefore distinguish retrieval failure from model-use failure. The observed case “the correct memory was selected but the model answered generically” is different from “no relevant memory was retrieved,” and the architecture records that distinction.

### 5.2 Semantic and hybrid adapters

`pipeline/retrieval.py` defines deterministic, semantic, and hybrid `MemoryRetriever` implementations. Semantic retrieval accepts an injected embedder and collection; hybrid scoring retains deterministic and semantic components. `pipeline/retrieval_eval.py` can build a temporary Chroma collection from stable fixture keys and compare strategies without writing production collections (`pipeline/retrieval_eval.py:24-96`).

Production assistant chat does not currently inject the semantic retriever. This is an intentional boundary: fixture improvements must be measured against false positives, no-match behavior, domain isolation, and answer grounding before semantic results are silently added to prompts.

### 5.3 Associations

Assistant memories may have domain-scoped, explainable associations. Current retrieval uses bounded one-hop support. This provides a third connective layer between explicit structured items without treating every relationship as a new canonical fact. It is an initial association graph, not a full cognitive or emotional network.

Future work may add temporal relations, learned relation proposals, and persona-local associations. Those additions should retain inspectability, bounded traversal, domain isolation, and human control over canonical user knowledge.

### 5.4 ContextManager

`pipeline/context.py` builds an immutable context plan containing persona, policy, recent conversation, retrieved memories, capability context, behavior context, introspection payloads, the current user message, and final model messages (`pipeline/context.py:60-170`). It also records selected memory IDs, section sizes, and estimated tokens. Prompt ordering and formatting are centralized rather than reconstructed by each frontend.

The context manager is deterministic and read-only. It does not select models, write memories, call providers, or mutate retrieval timestamps. Token estimation is currently approximate, which is sufficient for diagnostics but not a substitute for provider-reported tokenization in controlled benchmarks.

## 6. Document intake and reviewed knowledge

### 6.1 Implemented flow

StarFur's initial external-document workflow uses explicit APIs rather than trusting arbitrary UI-injected RAG:

1. validate filename, supported text type, size, and domain;
2. compute a content-addressed source identifier;
3. split text through shared chunking logic;
4. annotate each chunk with bounded model output and retries;
5. validate candidate types/fields and attach engine-owned provenance;
6. retain candidates in a short-lived server-side review;
7. require an exact handoff confirmation for a selected candidate;
8. create a normal pending assistant-memory proposal;
9. require ordinary proposal approval before activation.

The preparation layer is implemented in `pipeline/document_intake.py`; model extraction and JSON recovery are in `pipeline/document_annotation.py`; bounded review state is in `pipeline/document_review.py`; and routes are in `pipeline/api.py:78-180`.

The annotation prompt labels source text as untrusted data and reserves domain/source authority for the engine. A document that says “ignore previous instructions” is therefore content to analyze, not a system command. Per-chunk failures are bounded and can be reported without discarding successful candidates from other chunks.

### 6.2 Current boundary

The flow extracts reviewable structured memories. It does not yet provide full document RAG. Source files/chunks are not durable assistant source records, and production assistant semantic retrieval does not search them. A fact omitted by annotation will not be available later merely because it appeared in the document.

Reviews are process-local and expire. Candidate display identity includes an ordinal, making convenient batch review possible but requiring a stronger content-derived fingerprint for repeat annotations whose model output order changes. The active chat provider currently performs annotation; task-specific model profiles are not yet available.

### 6.3 UI contamination risk

An external UI may independently retrieve attachment fragments and prepend them to a chat message. Once flattened into user text, StarFur cannot reliably know which words are the user's assertion, which are a command, and which came from a document. This can weaken persona adherence, command routing, and proposal provenance.

The architectural remedy is not a custom UI immediately. It is a source-aware message contract: user observations, commands, retrieved external context, tool output, and approved canonical memory should be distinct structured inputs to the application/context layer. OpenWebUI or another adapter can then map uploads to StarFur's intake/retrieval services.

## 7. Provider and presentation architecture

### 7.1 Multiple frontends, one backend contract

The CLI and OpenAI-compatible HTTP interface already share `AssistantApplication`. Future Textual TUI, web dashboard, and apartment should use the same application primitives rather than invoking database or model code directly. Presentation layers may render streaming, diagnostics, proposals, and capability help differently, but they should not reinterpret memory policy.

### 7.2 Current API semantics

The HTTP API supports a model listing, chat completion streaming, health/diagnostics, and document operations. Authentication is an optional bearer key. This is adequate for controlled local use, but not a production security model. Binding a no-key server beyond loopback would expose memory operations to the local network.

More importantly, one shared session currently serves all requests. Serialization ensures consistency under concurrent access, but not isolation. A future session registry should key bounded ephemeral state by explicit conversation identity while sharing canonical memory by user/domain policy. Client-provided history should either be validated and used consistently or remain explicitly server-owned; mixing “latest client message” with an implicit global history is ambiguous.

### 7.3 Routing as measured infrastructure

The long-term router is envisioned as a small attention/classification step that selects capabilities and task profiles: lightweight chat, heavier reasoning, coding, structured extraction, vision, image generation, embeddings, or speech. Routing should not be introduced as invisible prompt heuristics. Each decision should record:

- requested capability and task class;
- chosen provider/model/profile;
- route confidence and reasons;
- fallback path;
- model load/warm state where measurable;
- TTFT, provider latency, and total turn time;
- errors, retries, and empty-output behavior.

The existing provider interface, lifecycle state, diagnostics, and benchmark manifest are useful prerequisites. A permission engine must mediate tools and environmental actions independently of persona or router choice.

## 8. Evaluation methodology

### 8.1 Why unit tests are insufficient

Unit and integration tests answer whether specified code behavior remains intact. They do not establish retrieval quality, answer grounding, persona adherence, model portability, long-session stability, or the contribution of an architectural component. StarFur therefore needs a versioned behavioral benchmark layer above its test suite.

Every benchmark run should record at least:

- benchmark schema/version and case identity;
- git commit and dirty-worktree state;
- architecture/configuration fingerprint;
- provider, model, quantization, generation options, and context size;
- hardware and available software versions;
- expected and actual result;
- pass/fail plus structured failure category;
- retrieved identities, ranks, scores, and reasons;
- prompt/completion estimates or provider token counts;
- TTFT, provider latency, phase timings, and total latency;
- optional CPU, RAM, VRAM, temperature, and energy observations;
- retry, interruption, empty-output, and fallback events.

Raw private prompts or memories should not be written to public benchmark artifacts by default. Fixtures should use synthetic identities and stable keys.

### 8.2 Benchmark families

The roadmap correctly identifies the following initial families:

1. **Memory retrieval:** Recall@K, Precision@K, Top-1/Top-K hits, distractors, false positives, and clean no-match cases.
2. **Retrieval versus use:** record separately whether the correct memory entered context and whether the model used it accurately.
3. **Long-document behavior:** question answering and proposal extraction across increasing source/chunk counts, including middle-of-document facts.
4. **Annotation quality:** field validity, false positives, missed durable facts, subject attribution, type classification, duplicates, and retry behavior.
5. **Boundary isolation:** user observation versus document content, commands inside RAG, persona/policy adherence under long context, and source/domain isolation.
6. **Persona/instruction adherence:** factual directness, style retention, command-help accuracy, and avoidance of invented capabilities.
7. **Provider portability:** identical fixtures across Ollama and later compatible providers/models.
8. **Latency/resources:** cold and warm TTFT, throughput, phase timings, context size, VRAM/RAM, and fallback cost.
9. **Persistence/recovery:** restarts, interrupted streams, expired review state, database migration, and long-session continuity.

Real failures should become permanent synthetic regression cases when privacy permits. Examples include correct retrieval followed by an ungrounded answer, model JSON wrapped in prose, empty streamed content, path-separator assumptions, RAG text overriding command intent, and duplicated proposal evidence.

### 8.3 Small-model scaling study

The principal scaling experiment should hold StarFur's surrounding architecture constant while varying only provider/model capacity and documented generation parameters. Outcomes should be separated into:

- structured memory retrieval, largely application-provided;
- correct use/grounding of retrieved memory;
- reasoning and multi-step instruction following;
- structured extraction validity;
- persona adherence;
- prose quality;
- latency, TTFT, throughput, and resource cost.

The research question is not whether a small model is universally “as smart” as a large model. It is whether external memory and control components reduce the minimum model capacity for specific resident-assistant tasks. A positive result would require confidence intervals or repeated seeded/unseeded runs, held-constant fixtures, documented quantization/context, and transparent failures.

### 8.4 Ablations and baselines

After the initial harness is stable, configurations can be compared against:

- raw model with only the user prompt;
- model plus persona/policy but no memory;
- deterministic memory without associations;
- deterministic memory with associations;
- semantic-only retrieval;
- hybrid retrieval;
- full StarFur context and provenance;
- individual components disabled one at a time.

Ablation results would clarify whether an apparent improvement comes from retrieval, policy, prompt structure, model capacity, or prose preference. They should not be conducted before session and source isolation, because contamination would confound the measurements.

## 9. Current results and evidence

### 9.1 Implemented verification surfaces

Static repository inspection finds deterministic tests and fixtures for major contracts including:

- assistant CRUD, domains, proposal lifecycle, evidence, approval links, and public identifiers;
- annotation parsing, nested schema validation, retry/failure semantics, and source attribution;
- deterministic retrieval, associations, introspection, and context planning;
- fixture-only semantic/hybrid retrieval comparison;
- streaming and interruption rollback;
- capability selection and deterministic command help;
- application facade locking and fake providers;
- API authentication, chat, diagnostics, document preparation/annotation/review handoff;
- benchmark manifest and retrieval metric calculations;
- lore chunking, sync discovery, version invalidation, and targeted reanalysis.

`CHANGELOG.md` records prior focused and full-suite verification throughout development. Recent entries report focused retrieval and context tests for approved external-document memories (`CHANGELOG.md:639-641`). This paper's inspection did not execute those tests, so they are implementation-history evidence rather than independently reproduced experimental results.

### 9.2 What can currently be claimed

The code supports the following bounded claims:

- StarFur has an additive, domain-aware assistant-memory schema separate from lore memory.
- Canonical assistant memories can be created, inspected, corrected, softly forgotten, searched, and retrieved.
- Model-generated memory candidates are application-validated and normally require human approval.
- Proposal evidence and approval provenance can be inspected and linked to an approved memory.
- Exact repeated observation evidence is idempotent.
- Normal assistant retrieval is deterministic and exposes result scores/reasons.
- Semantic/hybrid retrieval can be evaluated against fixtures without touching production Chroma.
- Persona presentation, policy, capabilities, and prompt assembly are separate modules.
- CLI and HTTP presentation surfaces share an application facade.
- External text can be prepared, annotated, reviewed, and handed off into the normal proposal workflow through explicit APIs.

### 9.3 What cannot currently be claimed

The repository does not yet establish that:

- semantic personal-memory retrieval improves production conversations;
- small local models match large models in general intelligence;
- external documents are fully available through source-level RAG;
- separate OpenWebUI chats are isolated;
- the API is safe for untrusted or multi-user deployment;
- proposal extraction has measured real-world precision/recall;
- long sessions preserve consistency over hundreds or thousands of turns;
- provider routing improves cost, latency, or quality;
- emotion, autonomous learning, vision, tools, or the apartment are implemented;
- the system is production-scale or ready for unattended automation.

These negative statements are important: they preserve a clear line between engineering progress and future research results.

## 10. Limitations and threats to validity

### 10.1 Architectural limitations

The current HTTP surface shares one stateful session, creating a threat to conversation isolation. The external-document review is in-memory and short-lived. Production assistant retrieval is structured/lexical rather than semantic. Associations are one-hop. The provider abstraction covers chat but not the full planned capability stack. `AssistantSession` and `pipeline/db.py` remain broad coupling points. Some lore paths bypass newer application/provider conventions.

### 10.2 Evaluation limitations

Existing retrieval fixtures are necessarily small and synthetic. Test success does not imply user-facing answer quality. Fixed seeds improve reproducibility but can hide variance; random-seed repetitions are also required. Model names alone are insufficient—template, quantization, context, provider version, and generation options affect behavior. Hardware/resource measurements can vary with background load and model warm state.

### 10.3 Memory epistemology

Confidence fields are user/application metadata, not calibrated epistemic probabilities. Human approval confirms that a memory may be stored, not that every wording is objectively true forever. Corrections, temporal supersession, conflicts, and perspective-dependent beliefs require explicit future models. Emotional state should not be represented by attaching permanent emotion numbers to every memory; it is better derived from bounded state, relationships, events, and associations.

### 10.4 Privacy and security

Local-first operation reduces third-party data exposure but does not eliminate local risks. SQLite/Chroma backups, exported diagnostics, external UI logs, and benchmark artifacts can contain sensitive data. The present optional single bearer token is not an account/authorization system. Tools, screen access, files, automation, and health data require a centralized permission layer, audit events, least privilege, and explicit user controls before implementation.

### 10.5 Static-inspection limitation

This draft was based on read-only static repository inspection. No current test run, database migration, provider request, HTTP session test, performance benchmark, or production-data operation was performed. File/line references are snapshot navigation aids.

## 11. Future work

### 11.1 Near-term engineering sequence

The evidence supports the following order:

1. isolate API conversation/session state;
2. complete reviewed external-document usability and source boundaries;
3. inject the retrieval strategy with deterministic default;
4. connect benchmark manifests to a result ledger;
5. introduce explicit task/provider profiles and measured routing;
6. add permissioned tools and controlled source-level RAG;
7. add vision/image/speech providers;
8. build apartment/avatar presentation on reliable lifecycle/capability events.

This order keeps the user-visible prototype moving while ensuring each new capability enters a measurable, permissioned platform.

### 11.2 Persona runtimes

Personas are currently style packages plus bounded state structures. The longer-term architecture proposes executable persona runtimes with their own interests and structured/semantic/associative memory, while StarFur Core retains shared user/project memory and policy. Persona-local learning should use explicit source and weight rules and must not silently rewrite shared canonical memory. A persona may learn Rust through sandboxed exercises, for example, but experiments and derived notes should remain distinguishable from user-approved personal facts.

### 11.3 Emotion and temporal context

Emotion should be a derived behavior layer, not a universal permanent scalar on every memory. Momentary state can combine recent events, relationship context, association activation, decay, and bounded traits to produce a `BehaviorContext`. The policy layer must continue to govern usefulness, factuality, and safety. Temporal memory and supersession will be needed to represent “used to prefer,” “currently upset about,” and “resolved situation” without deleting history.

### 11.4 Tools, perception, and apartment

A tool framework and permission engine should precede operational computer control. Vision can begin as explicit one-shot screen/window/region inspection rather than continuous monitoring. Image generation, TTS/STT, and system monitoring should be separate providers/capabilities with observable lifecycle and resource use.

The apartment is best treated as a presentation of core state: model loading may send a persona to a desk; generation may show thinking; tool execution may animate a workstation; mood may affect posture; system metrics may appear on displays. It should consume structured runtime events rather than infer state from response text. Placeholder/procedurally generated art can validate the interaction model before commissioned assets replace it.

### 11.5 Writing-partner integration

The existing lore subsystem supplies source-aware entities, facts, aliases, appearances, and semantic canon retrieval. Future writing-partner mode should call shared application/retrieval services while retaining its own project domain and canonical Markdown contracts. POV/perspective tracking is important for multi-POV manuscripts but need not become a universal assistant-memory primitive prematurely.

### 11.6 Research program

Once the initial benchmark runner exists, StarFur can accumulate longitudinal evidence across commits. The most valuable program is not a single headline score but a sequence of reproducible comparisons:

- deterministic versus semantic versus hybrid retrieval;
- retrieval success versus grounded answer success;
- model-size/quantization/context scaling;
- task-specific profile versus one-model operation;
- association and provenance ablations;
- long-session and restart recovery;
- contamination and adversarial-document cases;
- cold/warm resource and latency behavior;
- raw model versus full architecture.

These results could support technical validation, grant applications, and a public engineering portfolio if fixtures, exclusions, failures, and hardware/configuration are disclosed.

## 12. Conclusion

StarFur Forge demonstrates a coherent architectural shift from “chatbot with a database” toward a local-first resident-intelligence platform. The strongest aspect is not any single model or memory table, but separation of concerns: models propose and generate; the application validates; canonical memory and provenance remain durable; retrieval is inspectable; persona controls presentation; policy and capabilities remain core-owned; and multiple interfaces can converge on one backend boundary.

The system is already a meaningful single-user research prototype, particularly in structured memory and review. It is not yet a complete semantic document assistant, multi-client service, autonomous agent, or resident apartment. The next work should strengthen isolation, source boundaries, retrieval injection, and measurement before adding routing, tools, vision, or autonomy.

The central research hypothesis remains plausible but unproven: externalizing memory, retrieval, provenance, policy, and context management may allow smaller local models to provide more reliable resident-assistant behavior than their raw conversational performance suggests. StarFur now has enough architectural structure to test that hypothesis rigorously. The value of the next phase will come from preserving failures, controlling variables, and measuring the complete system rather than attributing every outcome to the language model alone.
