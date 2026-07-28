from pathlib import Path
import sqlite3

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
