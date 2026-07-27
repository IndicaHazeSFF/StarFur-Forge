from pathlib import Path
import sqlite3


DB_PATH = Path("data/starfur.db")

FACT_TYPE_DEFAULT = "durable_fact"
FACT_TYPES = (
    "durable_fact",
    "behavioral_tendency",
    "physical_attribute",
    "procedural_system_rule",
    "temporary_scene_state",
)


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
    connection.commit()

    return connection


def get_entities(entity_type=None):
    """
    Return confirmed entities.

    Optionally filter by entity type.
    """
    with connect() as connection:

        if entity_type:
            rows = connection.execute(
                """
                SELECT *
                FROM entities
                WHERE entity_type = ?
                AND status = 'confirmed'
                ORDER BY canonical_name
                """,
                (entity_type,),
            ).fetchall()

        else:
            rows = connection.execute(
                """
                SELECT *
                FROM entities
                WHERE status = 'confirmed'
                ORDER BY canonical_name
                """
            ).fetchall()

    return [dict(row) for row in rows]


def get_entity_names_and_aliases():
    """Return confirmed canonical names and aliases for proposal review."""
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT canonical_name AS name FROM entities WHERE status = 'confirmed'
            UNION ALL
            SELECT aliases.alias AS name
            FROM aliases JOIN entities ON entities.id = aliases.entity_id
            WHERE entities.status = 'confirmed'
            ORDER BY name
            """
        ).fetchall()
    return [row["name"] for row in rows if row["name"]]


def get_entity_by_name(name):
    """
    Find an entity by canonical name or alias.
    """
    with connect() as connection:

        row = connection.execute(
            """
            SELECT *
            FROM entities
            WHERE lower(canonical_name) = lower(?)
            LIMIT 1
            """,
            (name,),
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
            LIMIT 1
            """,
            (name,),
        ).fetchone()

    if row:
        return dict(row)

    return None


def create_entity(
    canonical_name,
    entity_type,
    description=None,
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
                description
            )
            VALUES (?, ?, ?)
            """,
            (
                canonical_name,
                entity_type,
                description,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
def get_entity_facts(entity_id):
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
            ORDER BY source, scene_index, chunk_index, id
            """,
            (entity_id,),
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