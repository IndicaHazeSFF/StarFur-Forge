# StarFur Forge ÃƒÆ’Ã†â€™Ãƒâ€ Ã¢â‚¬â„¢ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã‚Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â Command Reference

Temporary operator reference while StarFur Forge is under development.

Run commands from:

    ~/StarFur-Forge

---

## Start the Forge

Enter the project:

    cd ~/StarFur-Forge

Activate the Python environment:

    source .venv/bin/activate

Confirm the virtual environment:

    which python

Expected:

    /home/roger/StarFur-Forge/.venv/bin/python

Start Docker services:

    docker compose up -d

Check Docker services:

    docker compose ps

Check Ollama:

    systemctl status ollama --no-pager

---

## StarFur CLI

Show structured-memory status:

    python starfur.py status

Analyze a canon document and create lore proposals:

    python starfur.py analyze canon/manuscript/chapter-prologue.md

Inspect an entity:

    python starfur.py entity "Elias Voss"

Aliases also work:

    python starfur.py entity Elias

---

## Assistant Persona Configuration

The assistant persona is loaded from the path configured in `config/assistant.json`:

    {
      "persona_path": "persona/default.md"
    }

Persona files control presentation and style only. Memory retrieval, policy, safety,
commands, proposals, and provenance remain engine responsibilities. If the file is
missing, unreadable, empty, or invalid, StarFur uses a neutral built-in persona.

## Retrieval Evaluation

Run the checked-in temporary-SQLite retrieval benchmark:

    python starfur.py retrieval-eval

The report separates `lexical`, `semantic`, and `no_match` fixture tiers. The
production retriever intentionally uses lexical matching only; semantic-tier failures
are a measured future capability gap, not a reason to silently enable semantic chat
retrieval.

To run isolated semantic or hybrid comparisons with the fixed local `nomic-embed-text`
fixture embedder and a temporary Chroma collection:

    python starfur.py retrieval-eval --strategy semantic --explain
    python starfur.py retrieval-eval --strategy hybrid --explain

To measure cutoff tradeoffs without changing any runtime policy:

    python starfur.py retrieval-eval --strategy semantic --semantic-sweep
    python starfur.py retrieval-eval --strategy hybrid --semantic-sweep

To inspect one explicit fixture-only cutoff:

    python starfur.py retrieval-eval --strategy semantic --semantic-min-similarity 0.47 --explain

To measure whether a clear-first-result margin improves precision at a chosen cutoff:

    python starfur.py retrieval-eval --strategy semantic --semantic-min-similarity 0.47 --semantic-margin-sweep

To inspect one explicit cutoff-and-margin policy, including acceptance or ambiguity-rejection reasons:

    python starfur.py retrieval-eval --strategy semantic --semantic-min-similarity 0.47 --semantic-min-margin 0.02 --explain

These commands never read or modify the production assistant database or Chroma
collection. They require the local embedding model and Chroma dependency to be available.
## Ollama Generation Options

Optional, validated provider settings live in `config/assistant.json` and apply to
normal assistant responses plus proposal extraction and repair calls:

    "ollama_options": {
      "temperature": 0.4,
      "top_k": 40,
      "top_p": 0.9,
      "seed": 420
    }

All settings are optional; `{}` preserves Ollama provider defaults. `seed: 420` is
useful for repeatable debugging, while omitting `seed` uses normal provider behavior.
Only `temperature`, `top_k`, `top_p`, and `seed` are accepted to prevent silent typos.

## Assistant Memory Associations

Assistant-memory associations are currently an engine/API foundation rather than an interactive command. They link two active assistant memories within one domain using explicit provenance, type, and bounded strength. Retrieval may include one-hop related context only when one endpoint directly matches the user request; `context stats` shows the association contribution in its retrieval reasons. Associations are never inferred or mutated during normal chat.

## External Web UI API

Run the local OpenAI-compatible Assistant API:

    python starfur.py serve

Endpoints:

    GET  /health
    GET  /v1/models
    POST /v1/chat/completions
    POST /v1/starfur/documents/prepare
    POST /v1/starfur/documents/annotate
    GET  /v1/starfur/documents/review?review_id=DR-...
    POST /v1/starfur/documents/review
    POST /v1/starfur/documents/context

`/v1/starfur/documents/prepare` is the first explicit external-document intake boundary. Send a JSON object with `filename`, UTF-8 text `content`, and optional `domain` (`personal` or `project:<slug>`). It accepts `.md`, `.markdown`, and `.txt` names up to 2 MiB of UTF-8 content, validates/chunks them through StarFur, and returns source/chunk metadata only. It does not call a model, create proposals, write SQLite/Chroma, or inject the document into a chat turn.

`/v1/starfur/documents/annotate` accepts the same validated request body, sends each prepared chunk to the currently active configured provider through the shared application facade, and returns reviewable candidate proposals with source/chunk provenance. Annotation itself does not create pending proposals, write SQLite/Chroma, approve anything, or inject document text into chat. The response includes a short-lived `review.id`, display candidate IDs such as `C-001`, and a content-derived candidate identity; invalid model output returns HTTP 422.

To deliberately add one reviewed candidate to the existing pending-proposal workflow, call `/v1/starfur/documents/review` with only its returned `review_id`, `candidate_id`, and exact confirmation:

    {"review_id":"DR-...","candidate_id":"C-001","confirm":"create pending proposal"}

To hand off several already-reviewed candidates at once, send only their returned IDs and the plural exact confirmation. The server validates the entire batch before it writes any candidate, then reports each normal idempotent pending-proposal result in request order:

    {"review_id":"DR-...","candidate_ids":["C-001","C-002"],"confirm":"create pending proposals"}

To inspect an active review without re-annotation, call:

    GET /v1/starfur/documents/review?review_id=DR-...

It returns bounded candidate fields and ephemeral candidate status (`pending`,
`handed_off`, or `rejected`), never raw source chunks. A rejection is only a
short-lived review decision; it creates no proposal or memory:

    {"review_id":"DR-...","candidate_ids":["C-001"],"confirm":"reject document candidates"}

The server uses its in-memory validated candidate—not client-supplied proposal fields—then calls the normal idempotent pending-proposal writer with original chunk evidence. The result is still pending and must be approved/rejected through the existing proposal controls. Review sessions expire after 15 minutes and disappear on server restart.

`/v1/starfur/documents/context` is a separate, read-only source-selection endpoint for an active review. It accepts a `review_id`, an explicit `query`, and optional `limit` (1-8, default 3), then returns only lexical-matching chunks from the server-held source with stable scores and reasons. It does not create proposals, call a model, modify the review, or attach text to assistant chat on its own. This is the connector-facing context packet that later OpenWebUI custom retrieval will consume; raw source text remains absent from normal review metadata.

    {"review_id":"DR-...","query":"What graphics card is in the desktop?","limit":1}

To attach a reviewed document only to one chat turn, add the API extension below to the ordinary `/v1/chat/completions` request. StarFur uses the actual latest user message as the lookup query; the extension intentionally does **not** accept raw text or a client-selected query. The selected chunks are rendered as untrusted reference data, are reported in `context stats`, and do not become conversation history or a memory proposal source.

    {
      "model":"starfur-assistant",
      "messages":[{"role":"user","content":"What graphics card is in the desktop?"}],
      "starfur_document_context":{"review_id":"DR-...","limit":1}
    }

The review must be active and in the same assistant-memory domain. `context stats`, proposal commands, and memory introspection remain Core-owned command paths; an attached document never overrides them.

In OpenWebUI running in Docker, add an OpenAI connection with base URL `http://host.docker.internal:8001/v1` and model `starfur-assistant`; use the port selected when starting `serve`. The adapter preserves StarFur persona, retrieval, policy, proposals, and session state; it does not expose SQLite or Chroma. Use `--api-key <token>` for a bearer token. If OpenWebUI runs in Docker or another network namespace, bind explicitly with `--host 0.0.0.0` and use the host gateway address; do not expose an unauthenticated server beyond the local machine. Streaming uses OpenAI-compatible SSE chunks.

### Optional OpenWebUI attachment bridge

For one-file, provenance-safe source context in OpenWebUI, install
`integrations/openwebui/starfur_document_filter.py` as an OpenWebUI **Filter
Function** and attach it only to `starfur-assistant`. Configure its Valves:

    STARFUR_BASE_URL=http://host.docker.internal:8001
    STARFUR_API_KEY=starfur-local
    DOMAIN=personal
    DOCUMENT_CONTEXT_LIMIT=3
    OPENWEBUI_BASE_URL=http://localhost:8080

The Filter declares module-level `file_handler = True`, so OpenWebUI skips its
built-in RAG for that model. It also clears attachment reference fields as a
defense against builds that do not fully honor that switch. It accepts exactly one UTF-8 `.md`, `.markdown`,
or `.txt` attachment per turn, downloads it from the authenticated OpenWebUI
file API, invokes StarFur `/documents/annotate`, then forwards only the
short-lived `review_id` and bounded context limit in `starfur_document_context`.
StarFur derives source retrieval from the user's actual latest message. Raw
document text is never appended to the user message or conversation history.

Annotation candidates are not persisted by the Filter. Its status message
includes the short-lived `DR-...` review ID and candidate count. In the same
OpenWebUI model chat, use these exact controls (with the reported ID):

    document review DR-...
    document approve DR-... C-001 [C-002 ...]
    document reject DR-... C-001 [C-002 ...]

`document review` displays bounded candidate metadata without calling the
model. `document approve` creates only normal pending proposals; use the
existing `proposal approve <id>` command for final assistant-memory approval.
`document reject` dismisses only the ephemeral reviewed candidate and writes no
proposal/memory. The Filter's process-local review cache lasts at most 14 minutes;
restart/expiry safely requires re-annotation. Unsupported, multiple, or failed
attachments produce a status notice and no source context—there is no hidden
fallback to OpenWebUI RAG. See `integrations/openwebui/README.md` for full
setup and the smoke test.

### API conversation isolation

StarFur keeps **ephemeral** chat state separate only when a client supplies a
stable conversation identifier. This isolates recent conversation context,
active model selection, last-selected memory references, and pending command
confirmations. Requests for the same identifier are serialized; different
identifiers may run concurrently. An in-flight conversation is never evicted
mid-request. Canonical SQLite/Chroma memory remains shared and domain-scoped.

For `POST /v1/chat/completions`, StarFur selects the identifier in this order:

1. `X-StarFur-Conversation` request header;
2. JSON `conversation_id` (StarFur extension);
3. JSON `metadata.starfur_conversation_id` (StarFur extension);
4. OpenAI-compatible JSON `user` field;
5. the legacy shared `default` session when none is supplied.

For example:

    curl -H "Authorization: Bearer starfur-local" \
      -H "X-StarFur-Conversation: openwebui-chat-42" \
      -H "Content-Type: application/json" \
      http://127.0.0.1:8001/v1/chat/completions \
      -d '{"model":"starfur-assistant","messages":[{"role":"user","content":"Hello"}]}'

Identifiers are opaque local map keys, not user authentication or a security
boundary. They are limited to 128 safe identifier characters. Sessions are
in-memory and bounded with least-recently-used eviction; a restart clears only
ephemeral chat state. A frontend that does not send a stable per-chat key still
uses the legacy default session, so it does **not** gain separate-chat isolation
automatically.

## Runtime Ollama Model Selection

`config/assistant.json` `chat_model` is the startup default. Inside Assistant Mode, select from models installed locally in Ollama without restarting:

    model list
    model current
    model use <model-name>

`model list` calls Ollama's Python client API and marks the active model. `model use` verifies the exact installed model (tags such as `qwen3:8b` are supported) and changes only the current assistant session; it does not rewrite configuration, conversation history, proposals, SQLite, or Chroma. The selected model is used for subsequent chat and proposal-extraction calls. `context stats` continues to show the model used for its recorded turn.
## Assistant Proposal Provenance

Automatic assistant-memory proposals are derived from user observations only.
Questions, information requests, and assistant-generated answers are not canonical
memory evidence. Explicit `remember this:` commands and user corrections remain
valid memory sources. Future assistant-self memory, if added, must use a separate
explicit provenance type and opt-in behavior.
Speculative or playful future statements are not proposed unless the user clearly
expresses their own intent, plan, or goal (for example, “I want to…” or “I plan to…”).

## Assistant Memory Classification

Assistant proposals use the existing stored types; no schema migration is required:

- `preference` ? enduring likes, dislikes, choices, or settings.
- `personal_fact` ? stable personal facts, including owned hardware/setup or cautiously stated health facts; never diagnoses.
- `experience` ? completed or bounded personal events.
- `project_context` ? facts about projects, systems, workstreams, or technical setup.
- `relationship_context` ? relationships with people, pets, teams, or other social connections.
- `ongoing_situation` ? current unresolved or time-sensitive circumstances.
- `goal` ? intended outcomes or plans.
- `routine` ? repeated habits, schedules, or usual practices.

An explicit correction is classified as the corrected fact's underlying type and should identify the correction in its details. Ambiguous observations should produce no proposal.

## Interrupting Generation

Press Ctrl+C during a streamed response to stop that generation and return to the
assistant prompt. The partial response is not saved to conversation history and does
not produce a memory proposal. Press Ctrl+C while waiting at the input prompt to exit
cleanly.

## Assistant Memory Review

Start interactive Assistant Mode:

    python starfur.py assistant

When a factual turn produces a proposal, review it in chat:

    proposal list
    proposal inspect <id>
    proposal approve <id>
    proposal reject <id>
    proposal approve all

`proposal approve all` previews all pending proposals in the active domain and shows low-confidence warnings. It only proceeds when the next input is exactly `approve all`; any other input cancels the batch. Approval preserves normal provenance and reports individual results.

Inspect approved memories:

    memory inspect <M-###>

List or search active memories in the current domain:

    memory list
    memory search <query>

Soft-forget an active memory by title/summary or compact reference:

    forget this: <memory title>
    forget this: M-###

User-facing references are compact (`M-001` for memories and `P-001` for proposals). Legacy numeric IDs remain accepted for compatibility.

Approval is not automatic by default. Rejected proposals remain in history, and approving a proposal twice is refused.

---

## Lore Review

Review pending lore proposals:

    python -m pipeline.review_proposals

Review controls:

    A = Approve
    E = Edit
    R = Reject
    S = Skip
    Q = Quit

---

## Annotation Testing

Inspect Qwen annotations without creating proposals:

    python -m pipeline.inspect_annotations

The source document is currently configured inside:

    pipeline/inspect_annotations.py

This is temporary. A future StarFur CLI command will accept the
document path directly.

---

## Chroma / Canon Ingestion

Run incremental canon ingestion:

    python -m pipeline.ingest

Do NOT use:

    python pipeline/ingest.py

Pipeline modules use package-qualified imports and should be run
with `python -m`.

---

## Python Checks

Compile StarFur:

    python -m compileall -q pipeline starfur.py

Compile one module:

    python -m py_compile pipeline/annotator.py

---

## Git

Check repository state:

    git status

Stage changes:

    git add .

Commit:

    git commit -m "Commit description"

Recent commits:

    git log --oneline --decorate -5

---

## SQLite

Open the StarFur database:

    sqlite3 data/starfur.db

Show tables:

    sqlite3 data/starfur.db ".tables"

Show entity schema:

    sqlite3 data/starfur.db ".schema entities"

Show confirmed entities:

    sqlite3 -header -column data/starfur.db \
    "SELECT id, canonical_name, entity_type, status FROM entities;"

Show proposals:

    sqlite3 -header -column data/starfur.db \
    "SELECT id, proposed_name, proposed_entity_type, status FROM proposals;"

Show appearances:

    sqlite3 -header -column data/starfur.db "
    SELECT
        e.canonical_name,
        a.source,
        a.scene_index,
        a.chunk_index
    FROM appearances a
    JOIN entities e ON e.id = a.entity_id
    ORDER BY e.canonical_name, a.source, a.chunk_index;
    "

---

## Current Architecture

Permanent canon:

    canon/

Structured memory:

    data/starfur.db

Semantic memory:

    ChromaDB

Local inference:

    Ollama

Startup model default:

    config/assistant.json -> chat_model (currently qwen3:8b)

The interactive `model use` command can override this for the current session only.

Main CLI:

    starfur.py

---

## Planned Commands

These do NOT exist yet.

    starfur sync

Automatically process new and changed canon.

    starfur review

Review pending lore proposals.

    starfur inspect <file>

Inspect annotations without modifying memory.

    starfur rebuild

Reconstruct generated databases from canonical Markdown.

    starfur commands

Display this command reference.

Eventually the CLI should be installed so commands become:

    starfur status
    starfur sync
    starfur review
    starfur entity "Ceph"

rather than requiring `python starfur.py`.

---

## Design Rule

Canonical Markdown is intended to become the durable source of truth.

SQLite and Chroma should ultimately be rebuildable from:

    canon/

plus StarFur source/configuration.

## Sync

Synchronize StarFur's canon, semantic memory, and structured memory:

    python starfur.py sync

Sync automatically skips unchanged manuscript files and embeddings.


## RAG Testing

Start the interactive StarFur canon RAG:

    python -m pipeline.rag


## Performance Testing

Time an annotation test:

    time python -m pipeline.inspect_annotations

Planned: automatic performance logging and:

    python starfur.py perf


Assistant proposal inspection:

    proposal inspect <id>

Displays a domain-scoped proposal, identity, lifecycle, and oldest-first evidence without changing state.


    memory inspect <M-###>

Displays a domain-scoped canonical memory and evidence linked during proposal approval. Legacy memories may show no recorded evidence provenance.


    python starfur.py assistant-context "query" [--domain personal] [--limit 8] [--explain]

Displays deterministic ranked active canonical assistant memories and scoring reasons without invoking the chat model.


    python starfur.py retrieval-eval

Runs the checked-in retrieval benchmark against a temporary SQLite corpus and reports top-1/top-3 hit rate, irrelevant results, repeatability, and failures.


    python starfur.py retrieval-eval --strategy deterministic|semantic|hybrid

Semantic and hybrid strategies require explicit temporary Chroma dependencies; deterministic remains the default chat/evaluation path.


Semantic retrieval evaluation uses only a temporary fixture Chroma collection with injected embeddings; production collections are never opened by the benchmark.


Conversational introspection recognizes questions such as ?what do you remember about ...??, ?why do you remember that??, and ?where did that memory come from??. Responses use active canonical memory and approved provenance only.


Interactive `assistant` responses stream incrementally in the terminal while the complete response remains buffered for history and proposal processing.


### Assistant Context Assembly

Assistant prompt construction is deterministic and read-only. The context layer combines the configured persona, its bounded presentation-only runtime state, and engine policy with already-retrieved active memories (including each selected memory's non-empty details), the bounded recent conversation window, and the current user message. It does not retrieve memories, write data, call a model, summarize history, or apply token budgeting. When a selected memory directly answers a question, engine policy requires the factual answer first; persona warmth may follow. `context stats` reports the same plan's bounded size/accounting metadata. It also reports measured phase timings (prompt build, retrieval, association, provider, proposal, and total turn) and an estimated completion-token count. Timing values are diagnostics only and are not used for routing or budgeting.

Assistant chat now reaches Ollama through a narrow `ChatProvider` adapter. This does not change the installed-model commands or Ollama configuration; it establishes the provider boundary used by future LM Studio, hosted, and specialist-capability adapters. The assistant remains responsible for prompt/context assembly, streaming state, memory proposals, and diagnostics.


    context stats

Interactive assistant command that displays the bounded diagnostics snapshot for the latest completed or interrupted conversational turn: model/provider, persona/runtime-state/policy sizes, prompt and response character counts, estimated token counts, recent-context size, selected memory IDs with deterministic scores/reasons, latency, stream first-token timing, and proposal outcome. It is read-only: it does not invoke a model, query/write memory stores, or retain raw prompts/conversation text.


Hidden development reset (not shown in normal help):

    python starfur.py factory-reset --all --confirm

Requires typing `StarFur Factory Reset`; creates a SQLite backup and scopes deletion to assistant memory plus the configured semantic collection. Production reset additionally requires `--allow-production-reset`.


Hidden development restore:

    python starfur.py factory-restore

Lists timestamped backups, asks for a backup selection, and requires typing `StarFur Factory Restore`. Current data is safety-backed up before replacement.


### Shared runtime diagnostics

The local API exposes the bounded, read-only diagnostics snapshot at `GET /v1/starfur/diagnostics` (with the same bearer token as the other endpoints). It reports provider configuration and whether health was probed, active/startup model, capability manifest fingerprint and IDs, fallback state, lifecycle readiness, and the latest recorded turn timings. It never probes Ollama or reads/writes memory stores. Terminal `context stats` remains the detailed per-turn diagnostic view.
## Capability-aware assistant explanations

StarFur Core owns a structured capability manifest rather than placing feature knowledge in persona files. During ordinary conversation no capability block is added. Explicit questions such as `What can you do?` receive the current public capability manifest; narrowly named features such as memory proposals or model switching receive only matching capability entries. Persona controls presentation, while Core remains authoritative for what is currently supported. This does not expose private databases, hidden reasoning, or unregistered future features.
Proposal review commands require an identifier: proposal inspect <id>, proposal approve <id>, or proposal reject <id>. proposal approve all remains the explicit batch flow.

Direct proposal-help questions such as How do I approve new memories? receive Core-owned syntax so persona responses cannot invent or omit proposal IDs.

## Direct Command Help

Questions such as How do I search memories?, How do I show context diagnostics?, or How do I select a model? return Core-owned, exact command syntax rather than model-generated instructions. list models is an accepted alias for model list.

Persona Runtime diagnostics:

    persona inspect

This is read-only and shows bounded state metadata without displaying the full persona prompt or changing runtime state. Normal chat receives the same bounded presentation-only trait and momentary-state snapshot; it cannot override engine policy, factual grounding, provenance, commands, or permissions.

### External document annotation resilience

`POST /v1/starfur/documents/annotate` processes chunks independently. Invalid or empty annotation output is retried up to three times; later attempts tell the provider to return only a JSON object or `{"proposals": []}`. A partially successful response remains reviewable and includes a bounded `failures` list with chunk ID, ordering metadata, attempt count, and `invalid_annotation_output`; failed chunks do not create proposals or persist source text. Re-annotate a source later to retry failed chunks.

### External document candidate identity

Each reviewed document candidate has stable provenance derived from its source chunk plus candidate ordinal. Multiple valid facts extracted from one chunk therefore become separate pending proposals when explicitly handed off; repeating the same `C-###` handoff remains idempotent and returns `duplicate_evidence` rather than creating another proposal.

### Approved document retrieval

A reviewed document candidate affects assistant chat only after normal proposal approval. The resulting active assistant memory participates in the same deterministic, domain-scoped retrieval as other approved memories. Context and context stats may label it as an `approved external document`; they do not expose raw uploaded text, source IDs, or chunk identifiers. Pending, rejected, and forgotten document-derived records are not retrievable.

### Retrieval benchmark

`python starfur.py retrieval-eval` runs the deterministic fixture benchmark against a temporary SQLite database. Results now include `benchmark_version`, strategy, per-case expected/returned IDs, Recall@K, Precision@K, irrelevant-result count, and repeatability. It does not read or mutate production memory/Chroma.

### Benchmark manifests

`pipeline/benchmark.py` provides the first metadata-only benchmark layer. `BenchmarkRunManifest` records workload, architecture fingerprint, provider/model/quantization, context size, seed, hardware, and run identity. `build_scaling_plan()` creates same-workload/different-model plans without invoking providers or touching production data.

### Explicit benchmark result recording

`retrieval-eval` remains read-only by default. To append its temporary-fixture result to a local, privacy-bounded JSONL ledger, opt in with a path:

    python starfur.py retrieval-eval --record-ledger data/experiment_ledger.jsonl --run-id retrieval-baseline-001 --git-commit <commit> --hardware-profile "RTX 4070"

The ledger stores versioned manifest metadata, expected/returned fixture memory IDs, retrieval scores/reasons, aggregate metrics, and pass/fail results. It deliberately rejects raw prompts and responses, and does not read production assistant memory or Chroma.

### Task/provider profiles

`config/assistant.json` may declare validated `task_profiles` for workloads such as `assistant_chat`, `assistant_proposal`, `document_annotation`, `coding`, `vision`, and `image_generation`. A profile may declare a provider label, model, bounded generation settings, context size, output ceiling, and a future fallback task name. Profiles do not route requests or construct providers yet.

An `assistant_chat` profile model establishes Assistant Mode's startup default; later `model use` selections still control chat and proposal calls for that session. Document annotation may use its own configured model. If a profile names a provider other than the already active provider, StarFur fails clearly rather than silently substituting a backend.
