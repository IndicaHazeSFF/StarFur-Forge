# StarFur Forge — Command Reference

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

Primary model:

    qwen3:8b

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
