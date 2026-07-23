from pathlib import Path
import sqlite3


DB_PATH = Path("data/starfur.db")


def connect():
    """
    Open a connection to the StarFur database.
    """
    connection = sqlite3.connect(DB_PATH)

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

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
