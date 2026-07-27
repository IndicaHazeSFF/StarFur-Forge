from pathlib import Path
import sqlite3


DB_PATH = Path("data/starfur.db")


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,

    description TEXT,

    status TEXT NOT NULL DEFAULT 'confirmed',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(canonical_name, entity_type)
);


CREATE TABLE IF NOT EXISTS aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    entity_id INTEGER NOT NULL,
    alias TEXT NOT NULL,

    FOREIGN KEY(entity_id)
        REFERENCES entities(id)
        ON DELETE CASCADE,

    UNIQUE(entity_id, alias)
);


CREATE TABLE IF NOT EXISTS appearances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    entity_id INTEGER NOT NULL,

    source TEXT NOT NULL,
    scene_index INTEGER,
    chunk_index INTEGER,

    context TEXT,

    FOREIGN KEY(entity_id)
        REFERENCES entities(id)
        ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS entity_facts (
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
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(entity_id)
        REFERENCES entities(id)
        ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    subject_entity_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    object_entity_id INTEGER NOT NULL,

    description TEXT,
    source TEXT,

    status TEXT NOT NULL DEFAULT 'confirmed',

    FOREIGN KEY(subject_entity_id)
        REFERENCES entities(id)
        ON DELETE CASCADE,

    FOREIGN KEY(object_entity_id)
        REFERENCES entities(id)
        ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL,
    description TEXT,

    source TEXT,
    scene_index INTEGER,
    chunk_index INTEGER,

    status TEXT NOT NULL DEFAULT 'confirmed'
);


CREATE TABLE IF NOT EXISTS event_participants (
    event_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,

    role TEXT,

    PRIMARY KEY(event_id, entity_id),

    FOREIGN KEY(event_id)
        REFERENCES events(id)
        ON DELETE CASCADE,

    FOREIGN KEY(entity_id)
        REFERENCES entities(id)
        ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    proposal_type TEXT NOT NULL,

    proposed_name TEXT,
    proposed_entity_type TEXT,

    description TEXT,
    evidence TEXT,

    source TEXT,
    scene_index INTEGER,
    chunk_index INTEGER,

    status TEXT NOT NULL DEFAULT 'pending',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX IF NOT EXISTS idx_entities_name
ON entities(canonical_name);

CREATE INDEX IF NOT EXISTS idx_entities_type
ON entities(entity_type);

CREATE INDEX IF NOT EXISTS idx_aliases_alias
ON aliases(alias);

CREATE INDEX IF NOT EXISTS idx_appearances_entity
ON appearances(entity_id);

CREATE INDEX IF NOT EXISTS idx_appearances_source
ON appearances(source);

CREATE INDEX IF NOT EXISTS idx_relationships_subject
ON relationships(subject_entity_id);

CREATE INDEX IF NOT EXISTS idx_relationships_object
ON relationships(object_entity_id);

CREATE INDEX IF NOT EXISTS idx_proposals_status
ON proposals(status);
"""


def main():
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(DB_PATH)

    try:
        connection.executescript(SCHEMA)
        connection.commit()

    finally:
        connection.close()

    print("=== STARFUR DATABASE ===")
    print(f"Database: {DB_PATH}")
    print("Schema initialized successfully.")


if __name__ == "__main__":
    main()
