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

In OpenWebUI running in Docker, add an OpenAI connection with base URL `http://host.docker.internal:8001/v1` and model `starfur-assistant`; use the port selected when starting `serve`. The adapter preserves StarFur persona, retrieval, policy, proposals, and session state; it does not expose SQLite or Chroma. Use `--api-key <token>` for a bearer token. If OpenWebUI runs in Docker or another network namespace, bind explicitly with `--host 0.0.0.0` and use the host gateway address; do not expose an unauthenticated server beyond the local machine. Streaming uses OpenAI-compatible SSE chunks.

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

Assistant prompt construction is deterministic and read-only. The context layer combines the configured persona and engine policy with already-retrieved active memories (including each selected memory's non-empty details), the bounded recent conversation window, and the current user message. It does not retrieve memories, write data, call a model, summarize history, or apply token budgeting. When a selected memory directly answers a question, engine policy requires the factual answer first; persona warmth may follow. `context stats` reports the same plan's bounded size/accounting metadata. It also reports measured phase timings (prompt build, retrieval, association, provider, proposal, and total turn) and an estimated completion-token count. Timing values are diagnostics only and are not used for routing or budgeting.

Assistant chat now reaches Ollama through a narrow `ChatProvider` adapter. This does not change the installed-model commands or Ollama configuration; it establishes the provider boundary used by future LM Studio, hosted, and specialist-capability adapters. The assistant remains responsible for prompt/context assembly, streaming state, memory proposals, and diagnostics.


    context stats

Interactive assistant command that displays the bounded diagnostics snapshot for the latest completed or interrupted conversational turn: model/provider, prompt and response character counts, estimated token counts, recent-context size, selected memory IDs with deterministic scores/reasons, latency, stream first-token timing, and proposal outcome. It is read-only: it does not invoke a model, query/write memory stores, or retain raw prompts/conversation text.


Hidden development reset (not shown in normal help):

    python starfur.py factory-reset --all --confirm

Requires typing `StarFur Factory Reset`; creates a SQLite backup and scopes deletion to assistant memory plus the configured semantic collection. Production reset additionally requires `--allow-production-reset`.


Hidden development restore:

    python starfur.py factory-restore

Lists timestamped backups, asks for a backup selection, and requires typing `StarFur Factory Restore`. Current data is safety-backed up before replacement.

## Capability-aware assistant explanations

StarFur Core owns a structured capability manifest rather than placing feature knowledge in persona files. During ordinary conversation no capability block is added. Explicit questions such as `What can you do?` receive the current public capability manifest; narrowly named features such as memory proposals or model switching receive only matching capability entries. Persona controls presentation, while Core remains authoritative for what is currently supported. This does not expose private databases, hidden reasoning, or unregistered future features.
Proposal review commands require an identifier: proposal inspect <id>, proposal approve <id>, or proposal reject <id>. proposal approve all remains the explicit batch flow.
