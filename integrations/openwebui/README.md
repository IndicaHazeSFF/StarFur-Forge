# StarFur OpenWebUI reviewed-document bridge

`starfur_document_filter.py` is an optional OpenWebUI **Filter** function for
the `starfur-assistant` connection. It makes one supported attachment per turn
go through StarFur's external-document pipeline instead of OpenWebUI's built-in
RAG.

It is deliberately an integration artifact, not a StarFur runtime dependency.
Terminal Assistant Mode, direct API callers, and OpenWebUI chats without the
Filter retain their current behavior.

## What it does

```text
OpenWebUI upload + question
  -> authenticated raw-file download from the current OpenWebUI instance
  -> StarFur POST /v1/starfur/documents/annotate
  -> short-lived StarFur review ID + non-persistent candidates
  -> starfur_document_context { review_id, limit }
  -> normal StarFur /v1/chat/completions request
  -> StarFur derives lexical source context from the actual user question
```

The Filter declares module-level `file_handler = True`. That tells OpenWebUI to
skip its built-in attachment RAG after the Filter returns. This avoids two
unrelated RAG paths injecting text into the same prompt.

The Filter also clears the attachment reference fields before returning. This
defense-in-depth step prevents a second RAG path on OpenWebUI builds that do not
fully honor `file_handler`.

The bridge never appends raw attachment text to `messages` and never
auto-approves anything. It can only create a pending proposal after the user
types an explicit reviewed-document command described below.

## Install

1. Start StarFur locally with the normal OpenAI-compatible server. The default
   copy/paste configuration is retained in `docs/COMMANDS.md`.
2. In OpenWebUI, create a new **Filter Function** and paste the full contents
   of `starfur_document_filter.py`.
3. Configure its Valves:

   ```text
   STARFUR_BASE_URL=http://host.docker.internal:8001
   STARFUR_API_KEY=starfur-local
   DOMAIN=personal
   DOCUMENT_CONTEXT_LIMIT=3
   ```

   `OPENWEBUI_BASE_URL` defaults to `http://localhost:8080`, the normal
   OpenWebUI backend address from inside its container. For a native install,
   reverse proxy, or custom Docker port, change it to the address reachable
   from the OpenWebUI backend process (not necessarily the browser URL).

4. Attach the Filter **only** to the `starfur-assistant` model. Do not attach
   it globally: `file_handler = True` means any model using this Filter opts out
   of OpenWebUI's built-in file retrieval.

5. Upload exactly one UTF-8 `.md`, `.markdown`, or `.txt` file and ask a
   specific question about it. The status indicator reports the short-lived
   `DR-...` review ID and candidate count; retain that ID for candidate review.
   `context stats` should show the external
   document section and selected safe chunk reference.

## Review candidates in OpenWebUI

After an upload reports its `DR-...` ID, use exact commands in the same
`starfur-assistant` chat:

```text
document review DR-...
document approve DR-... C-001 [C-002 ...]
document reject DR-... C-001 [C-002 ...]
```

`document review` is read-only and returns bounded candidate metadata with
ephemeral status. `document approve` explicitly hands the selected original
server-side candidates to StarFur's normal pending-proposal workflow; it does
not create an active memory. Use `proposal list` and `proposal approve <id>`
for the existing final approval step. `document reject` dismisses candidates
only within the short-lived review and creates no proposal or memory. These
commands are parsed by the Filter and handled by StarFur Core, so no language
model decides what is persisted.

## Boundaries and limitations

- The source/review cache is process-local, bounded to 32 entries, and expires
  in at most 14 minutes (shorter than StarFur's 15-minute review lifetime).
  Restarting OpenWebUI or StarFur causes safe re-annotation.
- One supported text attachment per turn only. PDFs, Office files, images,
  collections, and multi-file synthesis are intentionally not handled yet.
- Annotation can be slow because it runs the configured StarFur annotation
  profile before chat. This is a correctness-first prototype; provider routing
  and a source/session cache are later optimization work.
- If processing fails, the Filter reports a safe status and sends no source
  context. Because it owns file handling, it does not silently fall back to
  OpenWebUI RAG.
- Candidates are **not** automatically written to SQLite, Chroma, or the
  pending-proposal table. The explicit `document approve` command is the only
  Filter handoff path; it creates pending proposals only. Review status and
  dismissal are short-lived and disappear safely on expiry/restart.

## Smoke test

Use a short text attachment such as:

```markdown
# Test document

My desktop has an RTX 4070 graphics card.
```

Ask: `What graphics card is in the desktop?`

Expected: a fact-grounded StarFur reply and `context stats` containing:

```text
External document context: 1 chunk(s), ...
Selected document chunks: test-document.md#0
```

No proposal should be created merely because the document was supplied to that
chat turn.
