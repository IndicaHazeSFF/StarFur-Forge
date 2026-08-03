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
ASSISTANT_MEMORY_TYPE_GUIDANCE = {
    "preference": "An enduring like, dislike, choice, taste, or personal setting.",
    "personal_fact": "A stable fact about the user, including owned hardware/setup or a cautiously stated health-related fact; do not diagnose.",
    "experience": "A completed or clearly bounded event the user personally experienced.",
    "project_context": "A fact about a project, system, workstream, or its technical setup; use goal instead for an intended outcome.",
    "relationship_context": "A fact about the user's relationship, family, friend, pet, team, or other social connection.",
    "ongoing_situation": "A current, unresolved, or time-sensitive circumstance that is not a routine.",
    "goal": "An intended outcome, plan, or objective the user wants to pursue.",
    "routine": "A repeated habit, schedule, or usual practice rather than a one-time event.",
}
ASSISTANT_RETENTIONS = ("session", "short_term", "long_term")
ASSISTANT_MEMORY_STATUSES = ("active", "superseded", "forgotten")
ASSISTANT_ASSOCIATION_TYPES = (
    "related", "supports", "conflicts", "topic", "temporal",
)
ASSISTANT_ASSOCIATION_STATUSES = ("active", "inactive")
ASSOCIATION_RETRIEVAL_WEIGHT = 0.15

# Common question scaffolding should not make unrelated memories look relevant.
# This is deliberately a small deterministic list, not synonym expansion.
RETRIEVAL_STOP_WORDS = frozenset({
    "a", "about", "an", "and", "are", "as", "at", "be", "can", "could",
    "did", "do", "does", "for", "from", "give", "had", "has", "have", "how",
    "i", "if", "in", "is", "it", "me", "my", "of", "on", "or", "please",
    "say", "said", "show", "tell", "that", "the", "their", "them", "there",
    "these", "they", "this", "those", "to", "us", "user", "was", "we", "what",
    "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
})

def _validated(value, allowed, label):
    if value not in allowed:
        raise ValueError(f"Invalid {label}: {value!r}")
    return value

def normalize_memory_type(value): return _validated(value, ASSISTANT_MEMORY_TYPES, "memory_type")
def normalize_retention(value): return _validated(value, ASSISTANT_RETENTIONS, "retention")
def normalize_memory_status(value): return _validated(value, ASSISTANT_MEMORY_STATUSES, "status")
def normalize_association_type(value): return _validated(value, ASSISTANT_ASSOCIATION_TYPES, "association_type")
def normalize_association_status(value): return _validated(value, ASSISTANT_ASSOCIATION_STATUSES, "association_status")

def assistant_memory_type_prompt():
    """Return the canonical extraction taxonomy in stable stored-type order."""
    return "\n".join(
        f"- {memory_type}: {ASSISTANT_MEMORY_TYPE_GUIDANCE[memory_type]}"
        for memory_type in ASSISTANT_MEMORY_TYPES
    )



def normalize_proposal_text(value):
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    text = text.replace("â€™", "'").replace("â€œ", "").replace("â€", "")
    text = re.sub(r"\s+", " ", text)
    return re.sub(r"[.!?;:,]+$", "", text).strip()

def _retrieval_query_text(value):
    """Normalize a query and remove a single leading/trailing vocative address."""
    text = normalize_proposal_text(value)
    parts = [part.strip() for part in text.split(",")]
    if len(parts) > 1:
        if len(re.findall(r"[\w']+", parts[0])) == 1 and any(parts[1:]):
            text = ",".join(parts[1:]).strip()
        elif len(re.findall(r"[\w']+", parts[-1])) == 1 and any(parts[:-1]):
            text = ",".join(parts[:-1]).strip()
    return text


def _retrieval_tokens(value):
    return {
        token for token in re.findall(r"[\w']+", normalize_proposal_text(value))
        if len(token) > 1 and token not in RETRIEVAL_STOP_WORDS
    }

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
    connection.execute("""
        CREATE TABLE IF NOT EXISTS assistant_memory_associations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            source_memory_id INTEGER NOT NULL,
            target_memory_id INTEGER NOT NULL,
            association_type TEXT NOT NULL,
            strength REAL NOT NULL DEFAULT 0.5,
            source TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (source_memory_id < target_memory_id),
            CHECK (strength >= 0 AND strength <= 1),
            UNIQUE(domain, source_memory_id, target_memory_id, association_type),
            FOREIGN KEY(source_memory_id) REFERENCES assistant_memories(id),
            FOREIGN KEY(target_memory_id) REFERENCES assistant_memories(id)
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_assistant_associations_source ON assistant_memory_associations(domain, source_memory_id, status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_assistant_associations_target ON assistant_memory_associations(domain, target_memory_id, status)")

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

            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            stats[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] if exists else 0

        # Keep assistant-memory counts separate from lore-memory counts.
        stats["assistant_memories"] = connection.execute("SELECT COUNT(*) FROM assistant_memories").fetchone()[0]
        stats["assistant_active_memories"] = connection.execute("SELECT COUNT(*) FROM assistant_memories WHERE status = 'active'").fetchone()[0]
        stats["assistant_pending_proposals"] = connection.execute("SELECT COUNT(*) FROM assistant_memory_proposals WHERE status = 'pending'").fetchone()[0]

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


def _assistant_association_pair(source_memory_id, target_memory_id):
    if isinstance(source_memory_id, bool) or isinstance(target_memory_id, bool):
        raise ValueError("memory IDs must be integers")
    try:
        source_memory_id = int(source_memory_id)
        target_memory_id = int(target_memory_id)
    except (TypeError, ValueError) as error:
        raise ValueError("memory IDs must be integers") from error
    if source_memory_id == target_memory_id:
        raise ValueError("An association requires two distinct memories")
    return tuple(sorted((source_memory_id, target_memory_id)))


def create_assistant_memory_association(
    source_memory_id, target_memory_id, association_type, *, strength=0.5,
    source="manual", domain="personal",
):
    """Create a domain-scoped, undirected association between two memories."""
    domain = normalize_domain(domain)
    source_memory_id, target_memory_id = _assistant_association_pair(source_memory_id, target_memory_id)
    association_type = normalize_association_type(association_type)
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not 0 <= strength <= 1:
        raise ValueError("association strength must be between 0 and 1")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("association source must be a non-empty string")
    with connect() as connection:
        memory_count = connection.execute(
            "SELECT COUNT(*) FROM assistant_memories WHERE domain = ? AND id IN (?, ?)",
            (domain, source_memory_id, target_memory_id),
        ).fetchone()[0]
        if memory_count != 2:
            raise ValueError("Both memories must exist in the active domain")
        cursor = connection.execute(
            """INSERT INTO assistant_memory_associations
            (domain, source_memory_id, target_memory_id, association_type, strength, source)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (domain, source_memory_id, target_memory_id, association_type, float(strength), source.strip()),
        )
        connection.commit()
    return cursor.lastrowid


def get_assistant_memory_association(association_id, domain="personal"):
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM assistant_memory_associations WHERE id = ? AND domain = ?",
            (association_id, normalize_domain(domain)),
        ).fetchone()
    return dict(row) if row else None


def list_assistant_memory_associations(domain="personal", memory_id=None, status="active", limit=100):
    domain = normalize_domain(domain)
    if limit <= 0:
        raise ValueError("limit must be positive")
    clauses = ["domain = ?"]
    params = [domain]
    if status is not None:
        clauses.append("status = ?")
        params.append(normalize_association_status(status))
    if memory_id is not None:
        if isinstance(memory_id, bool):
            raise ValueError("memory ID must be an integer")
        try:
            memory_id = int(memory_id)
        except (TypeError, ValueError) as error:
            raise ValueError("memory ID must be an integer") from error
        clauses.append("(source_memory_id = ? OR target_memory_id = ?)")
        params.extend((memory_id, memory_id))
    params.append(limit)
    with connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM assistant_memory_associations WHERE {' AND '.join(clauses)} ORDER BY created_at, id LIMIT ?",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def update_assistant_memory_association(association_id, *, domain="personal", strength=None, source=None, status=None):
    changes = {}
    if strength is not None:
        if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not 0 <= strength <= 1:
            raise ValueError("association strength must be between 0 and 1")
        changes["strength"] = float(strength)
    if source is not None:
        if not isinstance(source, str) or not source.strip():
            raise ValueError("association source must be a non-empty string")
        changes["source"] = source.strip()
    if status is not None:
        changes["status"] = normalize_association_status(status)
    if not changes:
        raise ValueError("No association changes supplied")
    assignments = ", ".join(f"{column} = ?" for column in changes)
    with connect() as connection:
        cursor = connection.execute(
            f"UPDATE assistant_memory_associations SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND domain = ?",
            [*changes.values(), association_id, normalize_domain(domain)],
        )
        connection.commit()
    if not cursor.rowcount:
        raise ValueError("Association not found")
    return get_assistant_memory_association(association_id, domain=domain)


def deactivate_assistant_memory_association(association_id, domain="personal"):
    return update_assistant_memory_association(association_id, domain=domain, status="inactive")


def _rank_assistant_memories(query, domain):
    normalized_query = _retrieval_query_text(query)
    tokens = _retrieval_tokens(normalized_query)
    if not tokens:
        return []
    rows = list_assistant_memories(domain=domain, status="active", limit=1000)
    rows_by_id = {row["id"]: row for row in rows}
    ranked = {}
    for row in rows:
        text = normalize_proposal_text(" ".join(str(row.get(key) or "") for key in ("subject", "summary", "details")))
        row_tokens = _retrieval_tokens(text)
        overlap = len(tokens & row_tokens)
        phrase = normalized_query in text
        if not overlap and not phrase:
            continue
        score = overlap / max(len(tokens), 1) + (0.5 if phrase else 0) + float(row.get("confidence") or 0) * 0.2 + float(row.get("importance") or 0) * 0.1
        reasons = [f"{overlap} meaningful keyword overlap"]
        if phrase:
            reasons.append("exact phrase")
        # Keep this internal overlap count until we know whether the query has
        # a stronger multi-term match. It is removed before results are
        # returned, so the public retrieval result shape remains unchanged.
        ranked[row["id"]] = {
            "memory": row,
            "score": score,
            "reasons": reasons,
            "_overlap": overlap,
            "_phrase": phrase,
        }

    # A query with several meaningful terms should not be padded with weak
    # one-term matches when at least one memory matches two or more terms.
    # Single-term recall (for example, "glasses") remains available when no
    # stronger lexical match exists.
    strongest_overlap = max((item["_overlap"] for item in ranked.values()), default=0)
    if strongest_overlap >= 2:
        ranked = {
            memory_id: item
            for memory_id, item in ranked.items()
            if item["_overlap"] >= 2 or item["_phrase"]
        }
    direct_ids = set(ranked)

    if direct_ids:
        for association in list_assistant_memory_associations(domain=domain, status="active", limit=10000):
            source_id = association["source_memory_id"]
            target_id = association["target_memory_id"]
            if source_id not in direct_ids and target_id not in direct_ids:
                continue
            strength = float(association["strength"])
            boost = strength * ASSOCIATION_RETRIEVAL_WEIGHT
            if boost <= 0:
                continue
            for matched_id, related_id in ((source_id, target_id), (target_id, source_id)):
                if matched_id not in direct_ids or related_id not in rows_by_id:
                    continue
                item = ranked.setdefault(related_id, {"memory": rows_by_id[related_id], "score": 0.0, "reasons": []})
                item["score"] += boost
                item["reasons"].append(
                    f"association with memory #{matched_id}: {association['association_type']} "
                    f"(strength {strength:.2f}; +{boost:.3f})"
                )

    output = []
    for item in ranked.values():
        output.append({
            key: value
            for key, value in {**item, "score": round(item["score"], 6)}.items()
            if not key.startswith("_")
        })
    return sorted(output, key=lambda item: (-item["score"], -int(item["memory"]["id"])))


def retrieve_assistant_memories(query, domain="personal", limit=8):
    """Return deterministic active-memory matches, including bounded association context."""
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    if limit <= 0:
        raise ValueError("limit must be positive")
    return _rank_assistant_memories(query, normalize_domain(domain))[:limit]


def explain_assistant_memory_retrieval(query, domain="personal", limit=8):
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    if limit <= 0:
        raise ValueError("limit must be positive")
    domain = normalize_domain(domain)
    ranked = _rank_assistant_memories(query, domain)
    selected = ranked[:limit]
    selected_ids = {item["memory"]["id"] for item in selected}
    ranked_by_id = {item["memory"]["id"]: item for item in ranked}
    not_selected = []
    for row in list_assistant_memories(domain=domain, status="active", limit=1000):
        if row["id"] in selected_ids:
            continue
        item = ranked_by_id.get(row["id"])
        if item is None:
            not_selected.append({"memory": row, "score": 0.0, "reason": "no lexical or association match"})
        else:
            not_selected.append({"memory": row, "score": item["score"], "reason": "below selection cutoff", "reasons": item["reasons"]})
    not_selected.sort(key=lambda item: (-item["score"], -int(item["memory"]["id"])))
    return {"selected": selected, "not_selected": not_selected}
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

def assistant_public_id(kind, record_id, domain="personal"):
    """Return a compact user-facing reference while retaining numeric DB IDs internally."""
    table = "assistant_memories" if kind == "memory" else "assistant_memory_proposals" if kind == "proposal" else None
    prefix = "M" if kind == "memory" else "P" if kind == "proposal" else None
    if table is None:
        raise ValueError("Unknown assistant record kind")
    with connect() as connection:
        row = connection.execute(
            f"SELECT id FROM {table} WHERE domain = ? ORDER BY created_at, id",
            (normalize_domain(domain),),
        ).fetchall()
    for position, row in enumerate(row, 1):
        if row["id"] == int(record_id):
            return f"{prefix}-{position:03d}"
    return f"{prefix}-{int(record_id):03d}"


def resolve_assistant_id(reference, kind, domain="personal"):
    """Resolve public M-/P- references and legacy numeric IDs to internal IDs."""
    value = str(reference).strip()
    if value.isdigit():
        return int(value)
    match = re.fullmatch(r"([MP])-(\d+)", value, re.IGNORECASE)
    expected = "M" if kind == "memory" else "P" if kind == "proposal" else None
    if not match or match.group(1).upper() != expected:
        return None
    ordinal = int(match.group(2))
    table = "assistant_memories" if kind == "memory" else "assistant_memory_proposals"
    with connect() as connection:
        rows = connection.execute(
            f"SELECT id FROM {table} WHERE domain = ? ORDER BY created_at, id",
            (normalize_domain(domain),),
        ).fetchall()
    return rows[ordinal - 1]["id"] if 1 <= ordinal <= len(rows) else None


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

