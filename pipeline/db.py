from pathlib import Path
import hashlib
import re
import sqlite3
import unicodedata

from pipeline.domains import DEFAULT_PROJECT_DOMAIN, normalize_domain


DB_PATH = Path("data/starfur.db")

FACT_TYPE_DEFAULT = "durable_fact"
FACT_TYPES = (
    "durable_fact",
    "behavioral_tendency",
    "physical_attribute",
    "procedural_system_rule",
    "temporary_scene_state",
)


ASSISTANT_MEMORY_TYPES = (
    "preference", "personal_fact", "experience", "project_context",
    "relationship_context", "ongoing_situation", "goal", "routine",
)
ASSISTANT_RETENTIONS = ("session", "short_term", "long_term")
ASSISTANT_MEMORY_STATUSES = ("active", "superseded", "forgotten")

def _validated(value, allowed, label):
    if value not in allowed:
        raise ValueError(f"Invalid {label}: {value!r}")
    return value

def normalize_memory_type(value): return _validated(value, ASSISTANT_MEMORY_TYPES, "memory_type")
def normalize_retention(value): return _validated(value, ASSISTANT_RETENTIONS, "retention")
def normalize_memory_status(value): return _validated(value, ASSISTANT_MEMORY_STATUSES, "status")



def normalize_proposal_text(value):
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    text = text.replace("’", "'").replace("“", "").replace("”", "")
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"[.!?;:,]+$", "", text).strip()

def assistant_proposal_key(domain, subject, memory_type, summary):
    identity = "|".join((normalize_domain(domain), normalize_proposal_text(subject), memory_type, normalize_proposal_text(summary)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()

def assistant_observation_key(domain, subject, memory_type, observation_text):
    identity = "observation|" + "|".join((normalize_domain(domain), normalize_proposal_text(subject), memory_type, normalize_proposal_text(observation_text)))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()

def normalize_fact_type(fact_type):
    if fact_type in FACT_TYPES:
        return fact_type

    return FACT_TYPE_DEFAULT


def ensure_entity_facts_schema(connection):
    """Add fact classification without rewriting existing fact rows."""
    table = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'entity_facts'
        """
    ).fetchone()

    if not table:
        connection.execute(
            """
            CREATE TABLE entity_facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL,
                fact TEXT NOT NULL,
                evidence TEXT,
                source TEXT NOT NULL,
                scene_index INTEGER,
                chunk_index INTEGER,
                fact_type TEXT NOT NULL DEFAULT 'durable_fact',
                status TEXT NOT NULL DEFAULT 'extracted',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        return

    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(entity_facts)"
        ).fetchall()
    }

    if "fact_type" not in columns:
        connection.execute(
            """
            ALTER TABLE entity_facts
            ADD COLUMN fact_type TEXT NOT NULL DEFAULT 'durable_fact'
            """
        )




def ensure_memory_domains_schema(connection):
    tables = ("entities", "appearances", "entity_facts", "proposals")
    for table in tables:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if not exists:
            continue
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if "domain" not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN domain TEXT NOT NULL DEFAULT '{DEFAULT_PROJECT_DOMAIN}'"
            )




def ensure_assistant_memories_schema(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS assistant_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            subject TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            details TEXT,
            importance REAL NOT NULL DEFAULT 0.5,
            confidence REAL NOT NULL DEFAULT 0.5,
            retention TEXT NOT NULL DEFAULT 'long_term',
            status TEXT NOT NULL DEFAULT 'active',
            source TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_accessed_at TEXT
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_assistant_memories_domain ON assistant_memories(domain)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_assistant_memories_status ON assistant_memories(status)")
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(assistant_memories)")}
    if "source_proposal_id" not in columns: connection.execute("ALTER TABLE assistant_memories ADD COLUMN source_proposal_id INTEGER")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_memories_source_proposal ON assistant_memories(source_proposal_id) WHERE source_proposal_id IS NOT NULL")
    connection.execute("CREATE TABLE IF NOT EXISTS assistant_memory_proposals (id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT NOT NULL, subject TEXT NOT NULL, memory_type TEXT NOT NULL, summary TEXT NOT NULL, details TEXT, importance REAL NOT NULL, confidence REAL NOT NULL, retention TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT, reviewed_by TEXT, review_note TEXT, approved_memory_id INTEGER)")
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(assistant_memory_proposals)")}
    for column, definition in (('proposal_key', 'TEXT'), ('evidence_count', 'INTEGER NOT NULL DEFAULT 1'), ('first_observed_at', 'TEXT'), ('last_observed_at', 'TEXT')):
        if column not in columns: connection.execute(f"ALTER TABLE assistant_memory_proposals ADD COLUMN {column} {definition}")
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_proposals_pending_key ON assistant_memory_proposals(domain, proposal_key) WHERE status = 'pending' AND proposal_key IS NOT NULL")
    connection.execute("CREATE TABLE IF NOT EXISTS assistant_memory_proposal_evidence (id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id INTEGER NOT NULL, source TEXT NOT NULL, source_reference TEXT, evidence_hash TEXT NOT NULL, raw_excerpt TEXT, observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(proposal_id, evidence_hash))")
    evidence_columns = {row["name"] for row in connection.execute("PRAGMA table_info(assistant_memory_proposal_evidence)")}
    if "memory_id" not in evidence_columns: connection.execute("ALTER TABLE assistant_memory_proposal_evidence ADD COLUMN memory_id INTEGER")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_assistant_proposal_evidence_memory ON assistant_memory_proposal_evidence(memory_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_assistant_proposal_evidence_proposal ON assistant_memory_proposal_evidence(proposal_id)")

def connect():
    """
    Open a connection to the StarFur database.
    """
    connection = sqlite3.connect(DB_PATH)

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    ensure_entity_facts_schema(connection)
    ensure_memory_domains_schema(connection)
    ensure_assistant_memories_schema(connection)
    connection.commit()

    return connection


def get_entities(entity_type=None, domain=DEFAULT_PROJECT_DOMAIN):
    """
    Return confirmed entities.

    Optionally filter by entity type.
    """
    with connect() as connection:

        domain = normalize_domain(domain)

        if entity_type:
            rows = connection.execute(
                """
                SELECT *
                FROM entities
                WHERE entity_type = ?
                AND domain = ?
                AND status = 'confirmed'
                ORDER BY canonical_name
                """,
                (entity_type, domain),
            ).fetchall()

        else:
            rows = connection.execute(
                """
                SELECT *
                FROM entities
                WHERE domain = ?
                AND status = 'confirmed'
                ORDER BY canonical_name
                """
            , (domain,)).fetchall()

    return [dict(row) for row in rows]


def get_entity_names_and_aliases(domain=DEFAULT_PROJECT_DOMAIN):
    """Return confirmed canonical names and aliases for proposal review."""
    domain = normalize_domain(domain)
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT canonical_name AS name FROM entities WHERE status = 'confirmed' AND domain = ?
            UNION ALL
            SELECT aliases.alias AS name
            FROM aliases JOIN entities ON entities.id = aliases.entity_id
            WHERE entities.status = 'confirmed' AND entities.domain = ?
            ORDER BY name
            """, (domain, domain)
        ).fetchall()
    return [row["name"] for row in rows if row["name"]]


def get_entity_by_name(name, domain=DEFAULT_PROJECT_DOMAIN):
    """
    Find an entity by canonical name or alias.
    """
    domain = normalize_domain(domain)

    with connect() as connection:

        row = connection.execute(
            """
            SELECT *
            FROM entities
            WHERE lower(canonical_name) = lower(?)
              AND domain = ?
            LIMIT 1
            """,
            (name, domain),
        ).fetchone()

        if row:
            return dict(row)

        row = connection.execute(
            """
            SELECT entities.*
            FROM aliases
            JOIN entities
                ON aliases.entity_id = entities.id
            WHERE lower(aliases.alias) = lower(?)
              AND entities.domain = ?
            LIMIT 1
            """,
            (name, domain),
        ).fetchone()

    if row:
        return dict(row)

    return None


def create_entity(
    canonical_name,
    entity_type,
    description=None,
    domain=DEFAULT_PROJECT_DOMAIN,
):
    """
    Create a confirmed canon entity.
    """
    with connect() as connection:

        cursor = connection.execute(
            """
            INSERT INTO entities (
                canonical_name,
                entity_type,
                description,
                domain
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                canonical_name,
                entity_type,
                description,
                normalize_domain(domain),
            ),
        )

        connection.commit()

        return cursor.lastrowid


def add_alias(entity_id, alias):
    """
    Add an alias to an existing entity.
    """
    with connect() as connection:

        connection.execute(
            """
            INSERT OR IGNORE INTO aliases (
                entity_id,
                alias
            )
            VALUES (?, ?)
            """,
            (
                entity_id,
                alias,
            ),
        )

        connection.commit()


def add_appearance(
    entity_id,
    source,
    scene_index=None,
    chunk_index=None,
    context=None,
):
    """
    Record an entity appearing in a source passage.

    Duplicate appearances are ignored.
    """
    with connect() as connection:

        connection.execute(
            """
            INSERT OR IGNORE INTO appearances (
                entity_id,
                source,
                scene_index,
                chunk_index,
                context
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                source,
                scene_index,
                chunk_index,
                context,
            ),
        )

        connection.commit()


def create_proposal(
    proposal_type,
    proposed_name=None,
    proposed_entity_type=None,
    description=None,
    evidence=None,
    source=None,
    scene_index=None,
    chunk_index=None,
):
    """
    Store an AI-generated proposal for human review.

    This DOES NOT modify confirmed canon.
    """
    with connect() as connection:

        cursor = connection.execute(
            """
            INSERT INTO proposals (
                proposal_type,
                proposed_name,
                proposed_entity_type,
                description,
                evidence,
                source,
                scene_index,
                chunk_index
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_type,
                proposed_name,
                proposed_entity_type,
                description,
                evidence,
                source,
                scene_index,
                chunk_index,
            ),
        )

        connection.commit()

        return cursor.lastrowid


def get_pending_proposals():
    """
    Return proposals awaiting human review.
    """
    with connect() as connection:

        rows = connection.execute(
            """
            SELECT *
            FROM proposals
            WHERE status = 'pending'
            ORDER BY created_at
            """
        ).fetchall()

    return [dict(row) for row in rows]


def database_stats():
    """
    Return basic StarFur database statistics.
    """
    with connect() as connection:

        tables = [
            "entities",
            "aliases",
            "appearances",
            "entity_facts",
            "relationships",
            "events",
            "proposals",
        ]

        stats = {}

        for table in tables:

            count = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            stats[table] = count

    return stats
def clear_source_appearances(source):
    """
    Remove source-derived appearance records for one document.

    Confirmed entities themselves are never removed.
    """
    with connect() as connection:
        cursor = connection.execute(
            """
            DELETE FROM appearances
            WHERE source = ?
            """,
            (source,),
        )

        connection.commit()

        return cursor.rowcount


def clear_pending_source_proposals(source):
    """
    Remove unresolved proposals generated from an older
    version of a source document.

    Approved and rejected proposals are preserved as
    human-review history.
    """
    with connect() as connection:
        cursor = connection.execute(
            """
            DELETE FROM proposals
            WHERE source = ?
              AND status = 'pending'
            """,
            (source,),
        )

        connection.commit()

        return cursor.rowcount
        
def clear_source_entity_facts(source):
    """
    Delete rebuildable extracted entity facts associated
    with a source.

    Confirmed facts are preserved.
    """

    with connect() as conn:
        cursor = conn.execute(
            """
            DELETE FROM entity_facts
            WHERE source = ?
              AND status = 'extracted'
            """,
            (source,),
        )

        return cursor.rowcount


def clear_source_derived_memory(source):
    """
    Clear rebuildable structured memory associated with
    a source before that source is re-analyzed.

    Confirmed memory is preserved.
    """

    appearances = clear_source_appearances(
        source
    )

    proposals = clear_pending_source_proposals(
        source
    )

    entity_facts = clear_source_entity_facts(
        source
    )

    return {
        "appearances": appearances,
        "pending_proposals": proposals,
        "entity_facts": entity_facts,
    }
def add_entity_fact(
    entity_id,
    fact,
    evidence,
    source,
    scene_index=None,
    chunk_index=None,
    status="extracted",
    fact_type=FACT_TYPE_DEFAULT,
    domain=DEFAULT_PROJECT_DOMAIN,
):
    """
    Record a source-derived fact about an entity.

    Duplicate facts from the same source/chunk are ignored.
    """

    with connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO entity_facts (
                entity_id,
                fact,
                evidence,
                source,
                scene_index,
                chunk_index,
                fact_type,
                status,
                domain
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id,
                fact,
                evidence,
                source,
                scene_index,
                chunk_index,
                normalize_fact_type(fact_type),
                status,
                normalize_domain(domain),
            ),
        )
def get_entity_facts(entity_id, domain=DEFAULT_PROJECT_DOMAIN):
    """
    Return all recorded facts for an entity.
    """

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                fact,
                evidence,
                source,
                scene_index,
                chunk_index,
                fact_type,
                status,
                created_at,
                updated_at
            FROM entity_facts
            WHERE entity_id = ?
              AND domain = ?
            ORDER BY source, scene_index, chunk_index, id
            """,
            (entity_id, normalize_domain(domain)),
        ).fetchall()

    return rows
def get_all_entity_facts():
    """
    Return entity facts grouped by entity ID.
    """

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                entity_id,
                fact,
                evidence,
                source,
                scene_index,
                chunk_index,
                fact_type,
                status
            FROM entity_facts
            ORDER BY
                entity_id,
                source,
                scene_index,
                chunk_index,
                id
            """
        ).fetchall()

    facts_by_entity = {}

    for row in rows:
        entity_id = row["entity_id"]

        facts_by_entity.setdefault(
            entity_id,
            [],
        ).append(row)

    return facts_by_entity

def create_assistant_memory(subject, memory_type, summary, details=None, importance=0.5, confidence=0.5, retention="long_term", source=None, domain="personal"):
    domain = normalize_domain(domain)
    memory_type = normalize_memory_type(memory_type)
    retention = normalize_retention(retention)
    if not 0 <= importance <= 1 or not 0 <= confidence <= 1:
        raise ValueError("importance and confidence must be between 0 and 1")
    with connect() as connection:
        cursor = connection.execute(
            """INSERT INTO assistant_memories
            (domain, subject, memory_type, summary, details, importance, confidence, retention, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (domain, subject, memory_type, summary, details, importance, confidence, retention, source),
        )
        connection.commit()
        return cursor.lastrowid


def get_assistant_memory(memory_id, domain="personal"):
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM assistant_memories WHERE id = ? AND domain = ?",
            (memory_id, normalize_domain(domain)),
        ).fetchone()
    return dict(row) if row else None


def list_assistant_memories(domain="personal", status="active", memory_type=None, retention=None, limit=100):
    clauses = ["domain = ?"]
    params = [normalize_domain(domain)]
    if status is not None:
        clauses.append("status = ?")
        params.append(normalize_memory_status(status))
    if memory_type is not None:
        clauses.append("memory_type = ?")
        params.append(normalize_memory_type(memory_type))
    if retention is not None:
        clauses.append("retention = ?")
        params.append(normalize_retention(retention))
    if limit <= 0:
        raise ValueError("limit must be positive")
    params.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM assistant_memories WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def search_assistant_memories(query, domain="personal", status="active", limit=20):
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    pattern = f"%{query.strip()}%"
    clauses = ["domain = ?", "(subject LIKE ? OR summary LIKE ? OR details LIKE ?)"]
    params = [normalize_domain(domain), pattern, pattern, pattern]
    if status is not None:
        clauses.append("status = ?")
        params.append(normalize_memory_status(status))
    params.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM assistant_memories WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def update_assistant_memory(memory_id, domain="personal", **changes):
    allowed = {"subject", "memory_type", "summary", "details", "importance", "confidence", "retention", "status", "source"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Unknown memory fields: {sorted(unknown)}")
    if "memory_type" in changes:
        changes["memory_type"] = normalize_memory_type(changes["memory_type"])
    if "retention" in changes:
        changes["retention"] = normalize_retention(changes["retention"])
    if "status" in changes:
        changes["status"] = normalize_memory_status(changes["status"])
    for field in ("importance", "confidence"):
        if field in changes and not 0 <= changes[field] <= 1:
            raise ValueError(f"{field} must be between 0 and 1")
    if not changes:
        return get_assistant_memory(memory_id, domain)
    assignments = ", ".join(f"{key} = ?" for key in changes)
    values = list(changes.values()) + [memory_id, normalize_domain(domain)]
    with connect() as connection:
        connection.execute(
            f"UPDATE assistant_memories SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND domain = ?",
            values,
        )
        connection.commit()
    return get_assistant_memory(memory_id, domain)


def forget_assistant_memory(memory_id, domain="personal"):
    return update_assistant_memory(memory_id, domain, status="forgotten")

def create_assistant_memory_proposal(proposal, domain="personal", observation_text=None):
    if observation_text is not None:
        return upsert_assistant_memory_proposal(proposal, domain=domain, observation_text=observation_text)
    domain = normalize_domain(domain)
    required = ("subject", "memory_type", "summary", "details", "importance", "confidence", "retention")
    if any(field not in proposal for field in required): raise ValueError("Missing proposal field")
    normalize_memory_type(proposal["memory_type"]); normalize_retention(proposal["retention"])
    for field in ("importance", "confidence"):
        if isinstance(proposal[field], bool) or not isinstance(proposal[field], (int, float)) or not 0 <= proposal[field] <= 1: raise ValueError("Invalid proposal score")
    with connect() as connection:
        cursor = connection.execute("INSERT INTO assistant_memory_proposals (domain, subject, memory_type, summary, details, importance, confidence, retention, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (domain, proposal["subject"], proposal["memory_type"], proposal["summary"], proposal.get("details"), proposal["importance"], proposal["confidence"], proposal["retention"], proposal.get("source", "assistant_turn_proposal")))
        connection.commit()
        return cursor.lastrowid

def list_assistant_memory_proposals(domain="personal", status="pending"):
    with connect() as connection:
        rows = connection.execute("SELECT * FROM assistant_memory_proposals WHERE domain = ? AND (? IS NULL OR status = ?) ORDER BY created_at, id", (normalize_domain(domain), status, status)).fetchall()
    return [dict(row) for row in rows]

def get_assistant_memory_proposal(proposal_id, domain="personal"):
    with connect() as connection:
        row = connection.execute("SELECT * FROM assistant_memory_proposals WHERE id = ? AND domain = ?", (proposal_id, normalize_domain(domain))).fetchone()
    return dict(row) if row else None

def inspect_assistant_memory_proposal(proposal_id, domain="personal"):
    """Return a proposal and oldest-first evidence without changing any state."""
    with connect() as connection:
        proposal = connection.execute("SELECT * FROM assistant_memory_proposals WHERE id = ? AND domain = ?", (proposal_id, normalize_domain(domain))).fetchone()
        if not proposal:
            return None
        evidence = connection.execute("SELECT id, proposal_id, source, source_reference, evidence_hash, raw_excerpt, observed_at FROM assistant_memory_proposal_evidence WHERE proposal_id = ? ORDER BY observed_at, id", (proposal_id,)).fetchall()
    return {"proposal": dict(proposal), "evidence": [dict(row) for row in evidence]}

def reject_assistant_memory_proposal(proposal_id, domain="personal", reviewed_by="user", review_note=None):
    with connect() as connection:
        cursor = connection.execute("UPDATE assistant_memory_proposals SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?, review_note = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND domain = ? AND status = 'pending'", (reviewed_by, review_note, proposal_id, normalize_domain(domain)))
        if cursor.rowcount != 1: raise ValueError("Proposal is missing or not pending")
        connection.commit()
    return get_assistant_memory_proposal(proposal_id, domain)

def approve_assistant_memory_proposal(proposal_id, domain="personal", reviewed_by="user", review_note=None):
    domain = normalize_domain(domain)
    with connect() as connection:
        proposal = connection.execute("SELECT * FROM assistant_memory_proposals WHERE id = ? AND domain = ?", (proposal_id, domain)).fetchone()
        if not proposal or proposal["status"] not in ("pending", "approved"):
            raise ValueError("Proposal is missing or not pending")
        if proposal["status"] == "approved" and proposal["approved_memory_id"]:
            row = connection.execute("SELECT * FROM assistant_memories WHERE id = ? AND domain = ?", (proposal["approved_memory_id"], domain)).fetchone()
            return dict(row) if row else None
        cursor = connection.execute("INSERT INTO assistant_memories (domain, subject, memory_type, summary, details, importance, confidence, retention, status, source, source_proposal_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)", (domain, proposal["subject"], proposal["memory_type"], proposal["summary"], proposal["details"], proposal["importance"], proposal["confidence"], proposal["retention"], proposal["source"], proposal_id))
        memory_id = cursor.lastrowid
        connection.execute("UPDATE assistant_memory_proposals SET status = 'approved', approved_memory_id = ?, reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?, review_note = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'", (memory_id, reviewed_by, review_note, proposal_id))
        connection.execute("UPDATE assistant_memory_proposal_evidence SET memory_id = ? WHERE proposal_id = ? AND (memory_id IS NULL OR memory_id = ?)", (memory_id, proposal_id, memory_id))
        connection.commit()
    return get_assistant_memory(memory_id, domain)

def inspect_assistant_memory(memory_id, domain="personal"):
    with connect() as connection:
        memory = connection.execute("SELECT * FROM assistant_memories WHERE id = ? AND domain = ?", (memory_id, normalize_domain(domain))).fetchone()
        if not memory: return None
        evidence = connection.execute("SELECT id, proposal_id, memory_id, source, source_reference, evidence_hash, raw_excerpt, observed_at FROM assistant_memory_proposal_evidence WHERE memory_id = ? ORDER BY observed_at, id", (memory_id,)).fetchall()
    return {"memory": dict(memory), "evidence": [dict(row) for row in evidence]}

def upsert_assistant_memory_proposal(proposal, domain="personal", source_reference=None, observation_text=None):
    domain = normalize_domain(domain)
    key = assistant_observation_key(domain, proposal["subject"], proposal["memory_type"], observation_text) if observation_text is not None else assistant_proposal_key(domain, proposal["subject"], proposal["memory_type"], proposal["summary"])
    source = proposal.get("source", "assistant_turn_proposal")
    evidence_text = observation_text if observation_text is not None else (source_reference or proposal["summary"])
    evidence_hash = hashlib.sha256((source + "|" + normalize_proposal_text(evidence_text)).encode("utf-8")).hexdigest()
    with connect() as connection:
        connection.execute("BEGIN")
        row = connection.execute("SELECT * FROM assistant_memory_proposals WHERE domain = ? AND proposal_key = ? AND status = 'pending'", (domain, key)).fetchone()
        if row:
            evidence = connection.execute("SELECT 1 FROM assistant_memory_proposal_evidence WHERE proposal_id = ? AND evidence_hash = ?", (row["id"], evidence_hash)).fetchone()
            if evidence and observation_text is not None:
                connection.commit()
                return {"proposal_id": row["id"], "action": "duplicate_evidence", "previous_evidence_count": row["evidence_count"], "evidence_count": row["evidence_count"]}
            connection.execute("UPDATE assistant_memory_proposals SET evidence_count = evidence_count + 1, last_observed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, confidence = MIN(1.0, confidence + 0.05) WHERE id = ?", (row["id"],))
            connection.execute("INSERT OR IGNORE INTO assistant_memory_proposal_evidence (proposal_id, source, source_reference, evidence_hash, raw_excerpt) VALUES (?, ?, ?, ?, ?)", (row["id"], source, source_reference, evidence_hash, observation_text or proposal.get("summary")) )
            connection.commit()
            return {"proposal_id": row["id"], "action": "reinforced", "previous_evidence_count": row["evidence_count"], "evidence_count": row["evidence_count"] + 1}
        cursor = connection.execute("INSERT INTO assistant_memory_proposals (domain, subject, memory_type, summary, details, importance, confidence, retention, source, proposal_key, evidence_count, first_observed_at, last_observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", (domain, proposal["subject"], proposal["memory_type"], proposal["summary"], proposal.get("details"), proposal["importance"], proposal["confidence"], proposal["retention"], source, key))
        proposal_id = cursor.lastrowid
        connection.execute("INSERT INTO assistant_memory_proposal_evidence (proposal_id, source, source_reference, evidence_hash, raw_excerpt) VALUES (?, ?, ?, ?, ?)", (proposal_id, source, source_reference, evidence_hash, observation_text or proposal.get("summary")) )
        connection.commit()
    return {"proposal_id": proposal_id, "action": "created", "previous_evidence_count": 0, "evidence_count": 1}


