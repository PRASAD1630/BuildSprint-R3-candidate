
import json
import sqlite3
from functools import lru_cache

from .config import DB_PATH, DATA


SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    day INTEGER NOT NULL,
    org TEXT,
    type TEXT,
    at TEXT,
    author TEXT,
    client TEXT,
    visibility TEXT,
    readers TEXT,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_day ON records(day);
CREATE INDEX IF NOT EXISTS idx_records_client ON records(client);
CREATE INDEX IF NOT EXISTS idx_records_at ON records(at);
CREATE INDEX IF NOT EXISTS idx_records_org ON records(org);
CREATE INDEX IF NOT EXISTS idx_records_author ON records(author);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_day INTEGER,
    person TEXT,
    type TEXT,
    words TEXT,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS preferences (
    person TEXT PRIMARY KEY,
    max_changes INTEGER,
    skip_newsletters INTEGER DEFAULT 0,
    raw TEXT
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person TEXT,
    meeting TEXT,
    words TEXT,
    created_day INTEGER
);

CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person TEXT,
    meeting TEXT,
    topic TEXT,
    verdict TEXT,
    words TEXT
);

CREATE TABLE IF NOT EXISTS forgotten (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person TEXT,
    words TEXT,
    created_day INTEGER
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT DEFAULT CURRENT_TIMESTAMP,
    person TEXT,
    action TEXT,
    detail TEXT
);

-- SQLite owns the mapping and retrieval metadata. FAISS stores only vectors.
CREATE TABLE IF NOT EXISTS vector_entries (
    vector_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL UNIQUE REFERENCES records(id) ON DELETE CASCADE,
    author TEXT,
    org TEXT NOT NULL,
    client TEXT,
    record_type TEXT,
    at TEXT,
    visibility TEXT NOT NULL,
    readers TEXT,
    content_hash TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    index_version INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vector_entries_org ON vector_entries(org);
CREATE INDEX IF NOT EXISTS idx_vector_entries_client ON vector_entries(client);

-- Suppression is person-scoped: forgetting by one person must not hide a
-- shared workplace record from everyone else in the organization.
CREATE TABLE IF NOT EXISTS vector_suppressions (
    person TEXT NOT NULL,
    record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(person, record_id)
);
"""


def connect():
    """Create a database connection and ensure the schema exists."""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")

    db.executescript(SCHEMA)

    return db


def rows(db, sql, args=()):
    """Return SQL query results as dictionaries."""

    return [
        dict(row)
        for row in db.execute(sql, args).fetchall()
    ]


@lru_cache(maxsize=1)
def _load_people():
    """Load the organization-to-person mapping."""

    path = DATA / "people.json"

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    mapping = {}

    for org_id, org_data in data.items():
        for person in org_data.get("people", []):
            person_id = person.get("id")

            if person_id:
                mapping[person_id] = org_id

    return mapping


def person_org(person):
    """Return the organization belonging to a person."""

    if not person:
        return None

    return _load_people().get(person)


def _normalize_readers(value):
    """Normalize reader information safely."""

    if value is None:
        return []

    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if item is not None and str(item).strip()
        ]

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        try:
            decoded = json.loads(value)

            if isinstance(decoded, list):
                return [
                    str(item).strip()
                    for item in decoded
                    if item is not None and str(item).strip()
                ]

        except (json.JSONDecodeError, TypeError):
            pass

    # Unknown reader formats must not grant access.
    return []


def can_read(record, person):
    """
    Check organization and record-level permissions.

    Rules:
    - A person must belong to the record's organization.
    - Private records are visible only to their author.
    - Restricted records are visible only to listed readers.
    - Team records are visible within the organization.
    - Unknown visibility values are denied.
    """

    if not isinstance(record, dict) or not person:
        return False

    org = person_org(person)

    if not org:
        return False

    record_org = record.get("org")

    if not record_org or str(record_org) != str(org):
        return False

    visibility = str(
        record.get("visibility") or "team"
    ).strip().lower()

    if visibility == "private":
        return record.get("author") == person

    if visibility == "restricted":
        readers = _normalize_readers(
            record.get("readers")
        )

        return person in readers

    if visibility in ("team", "organization", "org"):
        return True

    # Fail closed for unknown visibility labels.
    return False


def record_rows(db, person=None, at=None):
    """
    Retrieve records visible to a person.

    The person permission check happens before records
    are returned to the engine.

    The optional 'at' argument excludes records created
    after the requested timestamp.
    """

    query = """
        SELECT payload, day
        FROM records
        WHERE 1 = 1
    """

    args = []

    if at:
        query += " AND at <= ?"
        args.append(str(at))

    query += " ORDER BY at ASC, id ASC"

    result = []

    for row in db.execute(query, args):

        try:
            record = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(record, dict):
            continue

        record["_ingest_day"] = row["day"]

        if person is not None:
            if not can_read(record, person):
                continue

        result.append(record)

    return result


def log(db, person, action, detail=""):
    """Write an audit event."""

    db.execute(
        """
        INSERT INTO audit(person, action, detail)
        VALUES (?, ?, ?)
        """,
        (
            person,
            str(action)[:100],
            str(detail)[:1000],
        ),
    )

    db.commit()


def clear_people_cache():
    """
    Clear the cached people mapping.

    Call this if people.json changes while the application
    is running.
    """

    _load_people.cache_clear()
