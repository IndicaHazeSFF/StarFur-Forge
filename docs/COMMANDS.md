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

The multi-persona foundation uses declarative packages that contain only a persona's
presentation prompt and immutable initial state. Providers, shared Core memory,
tools, permissions, and active-session selection remain Core responsibilities.
Configured persona packages can be inspected and switched for the current session:

    persona list
    persona current
    persona use <persona-id>
    persona inspect

    persona assets

Switching clears only the current session's recent conversation context so one
persona does not inherit another's in-progress chat. It does not modify shared
assistant memories, providers, tools, permissions, or the configuration file.
The stock configuration includes `murr` (the startup persona), `neutral`, and
`nova`. `persona inspect` is read-only: it displays bounded runtime metadata
and persona-local development counts, never the full prompt or raw learning
evidence.

Each package may declare `minimum_shared_memory_confidence` in
`config/assistant.json`. After deterministic retrieval, the active persona sees
only same-domain active memories meeting that threshold. The stock packages use
`0.0`, preserving existing recall. `context stats` reports bounded visible/hidden
memory IDs plus the threshold and reason; this setting never rewrites memory or
changes another persona's state.

Packages may also declare `allowed_memory_scopes` as `null` (unrestricted) or a
subset of `personal`, `preference`, `project`, `relationship`, `routine`, and
`roleplay`. Existing rows use the conservative type-derived scopes; a newly
available explicit `visibility_scope` may override that fallback only when a
trusted/user-controlled workflow assigns it. Nothing infers `roleplay` (or any
other sensitive category) from memory prose. After ranking, both scope and
confidence must permit a record before it enters the active persona's context
or memory introspection. Stock packages remain unrestricted.

To explicitly control scope metadata without asking the model to classify
content, use either of these exact commands:

    memory scope <M-### or numeric id> <personal|preference|project|relationship|routine|roleplay|type-derived>
    proposal scope <P-### or numeric id> <personal|preference|project|relationship|routine|roleplay|type-derived>

`proposal scope` works only while the proposal is pending. `type-derived` (also
accepted as `clear`) removes explicit metadata and restores the legacy
memory-type fallback. These commands are domain-scoped and do not call a model.

Persona Runtime attention is a bounded internal presentation cue, not a user-memory
or skill system. When explicitly configured persona-local interests directly match a
request, StarFur may use up to two as optional examples or follow-up ideas. It never
claims expertise, redirects the request, or stores an interest from ordinary chat.

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
    GET  /v1/starfur/persona-runtime
    POST /v1/chat/completions
    POST /v1/starfur/documents/prepare
    POST /v1/starfur/documents/annotate
    GET  /v1/starfur/documents/review?review_id=DR-...
    GET  /v1/starfur/documents/reviews
    POST /v1/starfur/documents/review
    POST /v1/starfur/documents/context

`/v1/starfur/documents/prepare` is the first explicit external-document intake boundary. Send a JSON object with `filename`, UTF-8 text `content`, optional `domain` (`personal` or `project:<slug>`), and optional structural `profile`. It accepts `.md`, `.markdown`, and `.txt` names up to 2 MiB of UTF-8 content, validates/chunks them through StarFur, and returns source/chunk metadata only. It does not call a model, create proposals, write SQLite/Chroma, or inject the document into a chat turn.

Profiles are `assistant_note` (legacy behavior), `technical_document`, `adventure_state`, and `manuscript`. `adventure_state` preserves Markdown headings and explicit labels such as `CURRENT SCENE`, `RELATIONSHIPS`, `UNRESOLVED THREADS`, and `STORY IS HERE` before bounded paragraph/sentence chunking. The OpenWebUI Filter defaults to `auto`, which selects `adventure_state` when it sees `STORY IS HERE` or at least two other explicit story-state labels; ordinary uploads retain `assistant_note` behavior. Structural prechunking reduces provider calls for large, sectioned documents, but annotation remains synchronous and review-only in this release.

`/v1/starfur/documents/annotate` accepts the same validated request body, sends each prepared chunk to the currently active configured provider through the shared application facade, and returns reviewable candidate proposals with source/chunk provenance. Annotation itself does not create pending proposals, write SQLite/Chroma, approve anything, or inject document text into chat. The response includes a short-lived `review.id`, display candidate IDs such as `C-001`, and a content-derived candidate identity; invalid model output returns HTTP 422.

For a long annotation launched from a terminal, add `?stream=terminal` and use `curl -N`. This opt-in text transport prints a completed-chunk progress bar followed by the final JSON result; the normal endpoint remains the standard one-response JSON API for OpenWebUI and other clients:

    FILE="$HOME/StarFur-Forge/story.md"
    jq -n \
      --arg filename "$(basename "$FILE")" \
      --arg content "$(cat "$FILE")" \
      --arg domain "personal" \
      '{filename:$filename, content:$content, domain:$domain}' |
    curl -sN -X POST \
      -H "Authorization: Bearer starfur-local" \
      -H "Content-Type: application/json" \
      'http://127.0.0.1:8001/v1/starfur/documents/annotate?stream=terminal' \
      --data-binary @-

Terminal progress exposes only `completed/total` chunk counts. It does not stream source text, candidate content, provider output, or diagnostics; cancellation/disconnection never changes the review-only persistence rules.

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

The server uses its in-memory validated candidate—not client-supplied proposal fields—then calls the normal idempotent pending-proposal writer with original chunk evidence. The result is still pending and must be approved/rejected through the existing proposal controls. Review sessions default to 24 hours, disappear on server restart, and remain bounded by the server's active-review limit. Set the top-level assistant configuration field `document_review_ttl_seconds` to an integer from 60 through 604800 when a different local TTL is needed.

`GET /v1/starfur/documents/reviews` lists only active review IDs and bounded source/review metadata; it never calls a model or exposes raw document text.

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

Attachment failures are safe and non-persistent. The Filter may report a bounded stage/category such as attachment download, StarFur annotation request, timeout, or transport error; it intentionally does not show raw exception text, URLs, tokens, source text, or stack traces.

Annotation candidates are not persisted by the Filter. Its status message
includes the short-lived `DR-...` review ID and candidate count. In the same
OpenWebUI model chat, use these exact controls (with the reported ID):

    document review DR-...
    document review list
    document approve DR-... C-001 [C-002 ...]
    document reject DR-... C-001 [C-002 ...]

`document review list` shows active review IDs without calling the model, and
`document review <id>` displays bounded candidate metadata without calling the
model. `document approve` creates only normal pending proposals; use the
existing `proposal approve <id>` command for final assistant-memory approval.
`document reject` dismisses only the ephemeral reviewed candidate and writes no
proposal/memory. The Filter's process-local review cache defaults to 24 hours;
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

Inspect the configured task/profile route preview without calling or probing a provider:

    routing status

This shows the resolved provider/model for each configured typed task and any configured pre-request fallback. It is descriptive only; it cannot switch models, execute a task, or alter configuration.

Run one explicit, non-generating availability check for the already configured provider:

    routing probe

This calls only the provider's supported model-list health method and retains a bounded session-local status, timestamp, optional model count, and bounded error message. It never generates text, changes the selected model, reads or writes memory, or exposes a model-list payload. Run `routing status` afterward to see the updated route availability.
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

### Session roleplay mode

The first roleplay control is deliberately session-local and does not create an
adventure database, replay history, or persistent story world:

    roleplay begin [optional title]
    roleplay status
    roleplay end

You may also use the clear casual phrases `let's roleplay` or `let's go on an
adventure`. Entering or leaving mode clears recent conversation context. While
active, Core marks eligible new memory proposals and explicit `remember this:`
requests with the explicit `roleplay` visibility scope. This is not automatic
classification: only an explicit active roleplay session can add that scope.

Relationship-meter scores are internal roleplay data. Normal in-character
replies describe them qualitatively; explicitly ask for meter or score
diagnostics to see raw values.

### Future adventure workspace registry

Prepare or inspect isolated CYOA workspace metadata with exact Core commands:

    adventure list
    adventure create <title>
    adventure inspect <title>
    adventure load <title>
    adventure resume <title>
    adventure begin <title>
    adventure restart fresh <new title>
    adventure restart established <checkpoint-id|label>: <new title>
    adventure session
    adventure status
    adventure events
    adventure event provenance <AE-######>
    adventure imports
    adventure import inspect <AI-######>
    adventure import bundles
    adventure import bundle create <title>: <AI-######> <AI-######> [...]
    adventure import bundle inspect <AB-######>
    adventure import bundle status <AB-######>
    adventure import map <AI-######> <C-###> <premise|state|relationship|knowledge|resource|exclude>
    adventure import mappings <AI-######>
    adventure import status <AI-######>
    adventure import commit premise <AI-######> <C-###>
    adventure import commit state <AI-######> <C-###> <key>: <value>
    adventure import commit relationship <AI-######> <C-###> <character> <dimension>: <value>
    adventure import commit knowledge <AI-######> <C-###> <character> <knows|believes|uncertain>: <fact>
    adventure import commit resource <AI-######> <C-###> <resource-id> <operation>[: <value>]
    adventure transcript
    adventure transcript record <user|narrator>: <text>
    adventure checkpoint <label>
    adventure checkpoints
    adventure checkpoint inspect <checkpoint-id|label>
    adventure corrections
    adventure retract <AE-######>: <reason>
    adventure state
    adventure state set <key>: <value>
    adventure correct state <AE-######> <key>: <value>
    adventure relationships
    adventure relationship set <character> <dimension>: <value>
    adventure correct relationship <AE-######> <character> <dimension>: <value>
    adventure knowledge
    adventure knowledge set <character> <knows|believes|uncertain>: <fact>
    adventure correct knowledge <AE-######> <character> <knows|believes|uncertain>: <fact>
    adventure resources
    adventure resource <resource-id> <operation>[: <value>]
    adventure correct resource <AE-######> <resource-id> <operation>[: <value>]
    adventure turn begin
    adventure turn status
    adventure turn generate <completed user-turn text>
    adventure turn generate transcript
    adventure turn generation status
    adventure turn candidates
    adventure turn mutations generate <completed user-turn text>
    adventure turn mutations generate transcript
    adventure turn mutation generation status
    adventure turn mutations
    adventure turn inspect
    adventure turn remove <staged-event-number>
    adventure turn stage candidate <TC-###>
    adventure turn stage mutation candidate <TM-###>
    adventure turn stage <event-type>: <summary>
    adventure turn stage state <key>: <value>
    adventure turn stage relationship <character> <dimension>: <value>
    adventure turn stage knowledge <character> <knows|believes|uncertain>: <fact>
    adventure turn stage resource <resource-id> <operation>[: <value>]
    adventure turn commit
    adventure turn abort
    adventure record <event-type>: <summary>
    adventure pause
    adventure end
    adventure unload

    python starfur.py adventure-eval

`adventure create` writes only a local registry entry and manifest under
`adventures/<stable-id>/`. `adventure load` attaches that workspace to the
current conversation, clears its recent chat context, and reads at most eight
validated authoritative event summaries when its event log already exists. The
selection preserves the opening event plus high-value continuity facts and
recent state in chronological order; it is not necessarily the last eight.
`adventure restart fresh <new title>` creates and mounts a fully isolated new
workspace. It preserves the previously loaded adventure unchanged and carries no
events, state, checkpoints, recent conversation, or roleplay session into the new one.
`adventure restart established <checkpoint-id|label>: <new title>` creates and mounts
an isolated child workspace from one verified checkpoint of the currently loaded
adventure. It copies only that authoritative event prefix and immutable resource
catalog, records its parent/checkpoint origin, and excludes later parent history,
parent checkpoints, recent conversation, and roleplay context. It is not a restore,
rewind, or mutation of the source workspace.
`adventure events` displays those bounded stored summaries without a model call.
`adventure event provenance <AE-######>` is a read-only audit of a generated
ordinary event's bounded generation ID, candidate ID, task/provider/model labels,
origin event count, and explicit transcript record references when used. It never
returns raw prompts, provider output, hidden context, or chain-of-thought.
`adventure imports` lists reviewed document selections staged for the loaded
workspace, and `adventure import inspect` displays one selected candidate set.
They are read-only source-review controls: staged imports do not establish
events, state, replay facts, or memories.
`adventure import bundles` lists optional user-authored groups of two or more
already staged document sources. Use `adventure import bundle create` to group,
for example, a `details.md` and exported conversation for the same adventure;
`adventure import bundle inspect` lists its source records. Bundles are
non-canonical organizational metadata, not an automatic import or prompt mount.
`adventure import bundle status` combines the read-only candidate mapping and
canonical-history audit for every source in one bundle; it cannot alter any
mapping, event, state, memory, or prompt context.
`adventure import map` records an explicit user-authored destination plan for
one staged candidate. `adventure import mappings` inspects the latest plan.
Mappings are not commits: they create no event, state, replay fact, or memory.
`adventure import status` is a read-only per-candidate audit: it shows the
current mapping and any canonical events committed from its prior mappings.
Mapping a candidate to `exclude` changes only that future plan; it never
retracts already recorded adventure events.
`adventure import commit premise` is the initial narrow canonical bridge: it
requires that exact candidate's current mapping to be `premise`, then records
one auditable `premise` event using the reviewed candidate summary/details.
It is idempotent for the same mapping. State, relationship, knowledge, and
resource mappings remain plans only until their separate typed commit paths exist.
`adventure import commit state` is the next typed bridge. It requires a current
`state` mapping but also requires the user to supply the validated state key and
value explicitly; the reviewed document is provenance, not authority to infer a
state mutation. It is idempotent for that mapping and exact typed value.
`adventure import commit relationship` likewise requires a current `relationship`
mapping and an explicit qualitative character/dimension/value. It never derives
numeric meters or a relationship from document prose.
`adventure import commit knowledge` requires a current `knowledge` mapping and
an explicit character-specific `knows`, `believes`, or `uncertain` claim. A
document does not make a belief objective world truth.
`adventure import commit resource` requires a current `resource` mapping and a
resource operation valid for the loaded adventure's immutable resource catalog.
The document cannot invent resources, bypass bounds, or expose hidden values.
`adventure transcript` displays optional presentation history kept separately from
authoritative events. `adventure transcript record` explicitly stores one bounded
user or narrator line; it never creates story state, replay facts, memories, or a
model request. After explicitly recording one adjacent `user` line followed by one
`narrator` line, `adventure turn generate transcript` may use that pair as bounded,
untrusted candidate-extraction input. It does not make the transcript authoritative,
stage a candidate, or write an event. Any incomplete or non-adjacent pair fails
closed. `adventure turn generate <completed user-turn text>` remains the direct
manual source path; `adventure turn generation status` reports bounded task outcome
and transcript record references when that explicit source path was used.
`adventure checkpoint <label>` creates a named immutable reference to the current
authoritative event-log prefix; `adventure checkpoints` lists those references; and
`adventure checkpoint inspect <checkpoint-id|label>` recomputes the verified prefix's
derived facts without changing the mounted session. A checkpoint is not yet a snapshot,
rewind, restore, or branch and cannot change story state.
`adventure corrections` is a read-only audit of active, superseded, and retracted event IDs.
It never calls a model. `adventure retract <AE-######>: <reason>` appends one explicit
Core-owned audit event that makes a currently active event stop affecting authoritative
projections; it never deletes history and cannot retract a retraction.
The four explicit `adventure correct` forms append one schema-v2 typed replacement for a
currently active state, relationship, character-knowledge, or resource event. They never edit
or delete history, infer corrections from narration, correct ordinary prose events, or resolve
contradictions. A correction must target the current active tip; use
`adventure corrections` to inspect its ID first.
`adventure state` displays the complete current authoritative state projected from
explicit state-change records. Prompt context uses a separate deterministic bounded
selection, so context limits never discard state. `adventure state set <key>: <value>` writes one
validated `state_change` event and refreshes that projection. Keys must use
lowercase letters, numbers, and underscores (for example `current_location`).
Core never extracts state from ordinary narration or model output.
`adventure relationships` displays complete qualitative character relationship
facts; prompt context uses a separate deterministic bounded selection. `adventure relationship set <character> <dimension>: <value>` records
one explicit `relationship_change` event, such as `adventure relationship set
Vespera trust: cautious`. Latest values are event-backed and rebuildable; Core
never assigns relationships from ordinary narration or a provider response.
`adventure knowledge` displays complete character-specific knowledge, beliefs,
and uncertainty; prompt context uses a separate deterministic bounded selection. `adventure knowledge set <character> <knows|believes|uncertain>:
<fact>` writes one explicit `character_knowledge` event, for example
`adventure knowledge set Vespera believes: the hatch is trapped`. A belief or
uncertainty is not automatically objective world truth; Core never derives it
from narration or a provider response.
`adventure turn` provides an explicit staged-event transaction for future
generated adventure turns. `adventure turn stage` keeps one ordinary validated
event draft in session memory only; the `state`, `relationship`, `knowledge`, and `resource`
variants stage one Core-validated structured fact. None alter prompt context or
the event log until `adventure turn commit` atomically appends the full batch;
the opaque Core request ID makes a matching completed-commit retry idempotent.
`adventure turn inspect` is the read-only pre-commit review of that staged batch;
hidden resource changes remain redacted. It never creates an event or changes a
projection.
`adventure turn candidates` displays only the current noncanonical, provider-untrusted
candidate batch for the loaded workspace. Candidates become stale after any authoritative
story write. `adventure turn stage candidate <TC-###>` requires an active transaction and
explicitly stages just that validated ordinary candidate; repeating the same candidate is a
no-op. Neither command creates candidates, calls a model, or writes an event.
`adventure turn mutations generate` runs a separate, explicit model task that may
propose only typed `state_set`, `relationship_set`, `knowledge_set`, or
`resource_change` mutations. Its `TM-###` inbox is distinct from ordinary `TC-###`
events; `adventure turn mutations` is read-only and `adventure turn stage mutation
candidate <TM-###>` still requires an active staged turn. A selected resource proposal
must additionally validate against the loaded adventure's immutable resource catalog
and current/staged resource state. No generated candidate is automatically staged or
persisted.
`adventure turn remove <staged-event-number>` discards exactly one inspected
draft while retaining the rest of the session-local batch. It is not a canonical
event deletion; no stored history exists until the remaining batch is committed.
`adventure turn abort` discards staging, and a mount change also discards it.
The direct state, relationship, knowledge, and resource commands remain documented
immediate-write alternatives.
`adventure` is a reserved Core command namespace. Exact documented forms run as
shown; malformed or unknown `adventure ...` input returns deterministic Core
guidance and never falls through to model generation, memory proposals, chat
history changes, or adventure writes.
`python starfur.py adventure-eval` runs only checked-in, deterministic adventure
integrity fixtures. It opens no provider, production memory, or live adventure
workspace; the current suite measures event-backed projections, generic resource
boundaries, bounded replay, and repeatability.
Generic adventure resource declarations remain scenario/package data. With a
declared catalog, `adventure resource <resource-id> <operation>[: <value>]`
explicitly validates and appends one generic resource operation; its `adventure
turn stage resource ...` counterpart remains session-local until commit. Plain
text values are accepted for text-like resources; use JSON for booleans, numbers,
or structured inventory values such as `["brass_key", 1]`. `adventure resources`
displays only public values. Hidden values and their event summaries never enter
normal model context or read-only inspection.
While a workspace is mounted, numeric relationship-meter wording in retrieved
`relationship_context` memories is redacted before normal narration unless the
user explicitly asks for a meter, score, or internal diagnostic. This changes
only prompt presentation; stored records and `context stats` remain intact.
`adventure record` is the initial explicit Core-owned write path; it requires a
loaded workspace and one of: `choice`, `discovery`, `promise`, `lie`,
`relationship_change`, `emotional_transition`, `state_change`,
`unresolved_hook`, `character_knowledge`, `inventory_change`, or
`location_change`.
`adventure resume <title>` is an exact load alias that does not begin roleplay
automatically. `adventure pause` ends the mounted adventure/active roleplay
session while preserving its stored event log. `adventure end` does the same
immediately; `end story now` is its exact Core-owned alias. Neither deletes,
archives, resets, or changes an adventure workspace.
`adventure begin <title>` is the explicit story-session entry point: it loads
one existing workspace and starts roleplay with that workspace title as its
session label. It creates no workspace or event and cannot infer a story from
ordinary chat.
`adventure session` is a read-only lifecycle view showing the active persona,
loaded workspace, session-local roleplay label, branch origin when present, and
whether a turn is staged. It does not reveal prompts, narrative event text, or
private persona runtime data.
This slice never captures narration, automatically creates events, starts
roleplay, writes shared assistant memory, runs a replay engine, or creates an
adventure database/index. A duplicate normalized title is rejected; future
resume controls will be explicit rather than silently creating another world.

`what is loaded?` is a read-only conversational alias for `adventure status`.

When a factual turn produces a proposal, review it in chat:

    proposal list
    proposal inspect <id>
    proposal approve <id>
    proposal reject <id>
    proposal approve all
    proposal scope <id> <scope|type-derived>

`proposal approve all` previews all pending proposals in the active domain and shows low-confidence warnings. It only proceeds when the next input is exactly `approve all`; any other input cancels the batch. Approval preserves normal provenance and reports individual results.

Inspect approved memories:

    memory inspect <M-###>
    memory scope <M-###> <scope|type-derived>

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

Interactive assistant command that displays the bounded diagnostics snapshot for the latest completed or interrupted conversational turn: model/provider, typed task-route summaries, persona/runtime-state/policy sizes, prompt and response character counts, estimated token counts, recent-context size, selected memory IDs with deterministic scores/reasons, per-persona shared-memory visibility decisions, latency, stream first-token timing, and proposal outcome. Route summaries show only task ID, selected provider/model, configured-fallback marker, and submitted/failure category; they never expose prompts, raw provider output, memory content, or provider payloads. The command is read-only: it does not invoke a model, query/write memory stores, or retain raw prompts/conversation text.


Hidden development reset (not shown in normal help):

    python starfur.py factory-reset --all --confirm

Requires typing `StarFur Factory Reset`; creates a SQLite backup and scopes deletion to assistant memory plus the configured semantic collection. Production reset additionally requires `--allow-production-reset`.


Hidden development restore:

    python starfur.py factory-restore

Lists timestamped backups, asks for a backup selection, and requires typing `StarFur Factory Restore`. Current data is safety-backed up before replacement.


### Shared runtime diagnostics

The local API exposes the bounded, read-only diagnostics snapshot at `GET /v1/starfur/diagnostics` (with the same bearer token as the other endpoints). It reports provider configuration and whether health was probed, active/startup model, capability manifest fingerprint and IDs, fallback state, lifecycle readiness, and the latest recorded turn timings plus its bounded task-route trace. Its `routing` section is a passive preview of whether configured task profiles would be routable through the current provider status; it does not switch, probe, or call a provider. Normal diagnostics never call Ollama or read/write memory stores. To explicitly run one non-generating provider availability probe, use `GET /v1/starfur/diagnostics?probe=provider`; it reports only health status, timestamp, model count when available, and a bounded error message.

`GET /v1/starfur/persona-runtime` returns the active conversation's bounded persona-runtime snapshot for future dashboard, TUI, and apartment presentation. It includes public identity/trait/state metadata and local record counts only. It does not call a model, seed a persona state, reveal prompts or raw evidence, modify memory stores, or edit configuration. `GET /v1/starfur/resident-snapshot` additionally includes the last completed turn's bounded task-route summary in its adventure-turn read model; it is informational and cannot drive provider selection or state mutation.
## Capability-aware assistant explanations

StarFur Core owns a structured capability manifest rather than placing feature knowledge in persona files. During ordinary conversation no capability block is added. Explicit questions such as `What can you do?` receive the current public capability manifest; narrowly named features such as memory proposals or model switching receive only matching capability entries. Persona controls presentation, while Core remains authoritative for what is currently supported. This does not expose private databases, hidden reasoning, or unregistered future features.
Proposal review commands require an identifier: proposal inspect <id>, proposal approve <id>, or proposal reject <id>. proposal approve all remains the explicit batch flow.

Direct proposal-help questions such as How do I approve new memories? receive Core-owned syntax so persona responses cannot invent or omit proposal IDs.

## Direct Command Help

Questions such as How do I search memories?, How do I show context diagnostics?, or How do I select a model? return Core-owned, exact command syntax rather than model-generated instructions. list models is an accepted alias for model list.

Persona Runtime diagnostics:

    persona inspect

This is read-only and shows bounded state metadata plus derived behavior controls without displaying the full persona prompt or changing runtime state. Normal chat receives the same Core-provided presentation-only behavior guidance; it cannot override engine policy, factual grounding, provenance, commands, or permissions.

`persona assets` shows only declared visual-state names from the active persona package's manifest. It never exposes package-relative paths, opens files, or loads assets.

Resident apartment activity:

    resident status
    resident action <idle|resting|reading|working|waiting|chatting|adventuring>
    resident action clear

This is an exact Core-owned, persona-local, restart-ephemeral presentation state. It does not start work, call a provider, change memory, or imply autonomous activity. `resident action clear` restores the Core default `idle` state. The apartment dashboard may show the action even when no matching authored animation is installed yet.

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

Adventure-turn benchmark results use the same opt-in ledger and keep the pipeline outcomes separate: generation completion, candidate validation, Core-use/staging, and canonical commit are recorded as bounded counts and rates. Turn text, provider payloads, and narrative prose are never retained by this result schema. This distinction lets a failed model response be measured separately from a successful Core commit or final narration-quality review.

`python starfur.py adventure-turn-eval` runs the deterministic C3 orchestration fixture suite in temporary adventure workspaces. It tests valid candidate review/stage/commit, explicit no-change output, invalid envelopes, and stale-origin rejection without invoking a model or touching an installed adventure. Add `--record-ledger <path>` to retain the bounded outcome record.

### Task/provider profiles

`config/assistant.json` may declare validated `task_profiles` for workloads such as `assistant_chat`, `assistant_proposal`, `adventure_turn_generation`, `document_annotation`, `coding`, `vision`, and `image_generation`. A profile may declare a provider label, model, bounded generation settings, context size, output ceiling, and a fallback task name. Profiles do not construct or probe providers. Normal session chat, proposal extraction, and generated-adventure-turn calls now form a deterministic route from bounded provider status and submit it through one already-injected chat adapter. The route is chosen before the request; a provider failure never triggers an implicit second request or model fallback.

Document annotation has its own bounded content-validation policy: the configured `document_annotation` profile may receive two attempts for a chunk, then an explicitly configured `document_annotation_fallback` profile may receive one attempt only when the primary output remained invalid. The current stock configuration uses Qwen3 8B alone for all three bounded attempts. Phi-4 Mini remains an explicit benchmark/experimental model rather than an automatic intake fallback, because the first public quality runs produced schema-valid empty output with zero expected-fact recall. A valid empty proposal list ends the sequence normally. Annotation results expose only model labels, bounded attempt counts, and whether fallback ran; no provider output is retained. Both paths remain review-only and create no memory until the existing explicit review/approval flow.

After an explicit annotation request, record its bounded reliability outcome without retaining source text, review IDs, candidates, prompts, or provider output:

    python starfur.py annotation-eval-record \
      --primary-model qwen3:8b --primary-attempts 3 \
      --fallback-attempts 0 \
      --chunks 1 --failed-chunks 0 --candidates 3 \
      --record-ledger data/experiment_ledger.jsonl

Use the `execution` object returned by `/documents/annotate` for the exact model labels, attempt counts, fallback use, and `elapsed_ms` latency value. The reliability benchmark fingerprint identifies the bounded-validation contract; the recorded model and attempt fields, rather than a hard-coded primary/fallback label, identify the observed route. A valid empty candidate list is still a successful reliability result; fact quality remains a separate reviewed benchmark concern.

Compare all recorded annotation observations without reading source documents or model output:

    python starfur.py annotation-eval-report --ledger data/experiment_ledger.jsonl

The report shows reliability and extraction quality separately: a schema-valid
empty candidate list can pass reliability but correctly fail quality recall.

For checked-in quality fixtures, save a standard (non-progress-streaming) API
annotation response locally, then score only its structured candidates. The
ledger receives recall, precision, false-positive, missed-target, and optional
latency counts—not candidate wording or source text:

    python starfur.py annotation-quality-eval \
      --response /tmp/qwen-model-comparison.json \
      --case model-comparison-facts \
      --primary-model qwen3:8b \
      --record-ledger data/experiment_ledger.jsonl

Run the checked-in public fixture directly against one installed Ollama model.
This is an explicit provider call, but it creates no review, proposal, memory,
or semantic entry:

    python starfur.py annotation-quality-run \
      --model phi4-mini:latest \
      --record-ledger data/experiment_ledger.jsonl

An `assistant_chat` profile model establishes Assistant Mode's startup default; later `model use` selections still control chat and proposal calls for that session. Document annotation may use its own configured model. If a profile names a provider other than the already active provider, StarFur fails clearly rather than silently substituting a backend.
