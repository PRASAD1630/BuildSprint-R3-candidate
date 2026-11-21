"""Persistent FAISS retrieval backed by SQLite metadata and source records.

SQLite is authoritative. FAISS contains normalized dense vectors and vector IDs;
every returned vector is resolved back to its current SQLite source record and
checked against the caller's pre-filtered allowlist and access policy.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from . import storage
from .config import ROOT


INDEX_VERSION = 1
MODEL_NAME = os.getenv(
    "VECTOR_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
EMBEDDING_DIMENSION = 384
TEAM_VISIBILITIES = {"team", "organization", "org"}
INDEX_NAME = "workmate.faiss"
METADATA_NAME = "workmate.index.json"

_STATS = {
    "embedding_ms": 0,
    "search_ms": 0,
    "rebuild_ms": 0,
    "searches": 0,
    "results": 0,
    "last_error": None,
}


def _enabled():
    return os.getenv("VECTOR_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off", "disabled"
    }


def _index_dir() -> Path:
    return Path(os.getenv("VECTOR_INDEX_DIR", ROOT / "data" / "vector_store"))


def _load_packages():
    import faiss
    import numpy as np

    return faiss, np


@lru_cache(maxsize=1)
def _embedding_model():
    from fastembed import TextEmbedding

    cache_dir = os.getenv("FASTEMBED_CACHE_PATH")
    return TextEmbedding(model_name=MODEL_NAME, cache_dir=cache_dir)


def generate_embeddings(texts):
    """Generate normalized float32 MiniLM vectors; model loading is lazy."""
    values = [str(text or "").strip() for text in texts]
    if not values:
        return None
    started = time.perf_counter()
    faiss, np = _load_packages()
    vectors = list(_embedding_model().embed(values))
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != len(values):
        raise ValueError("Embedding model returned an invalid matrix")
    if matrix.shape[1] != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSION}-dimensional embeddings; "
            f"received {matrix.shape[1]}"
        )
    if not np.isfinite(matrix).all():
        raise ValueError("Embedding model returned non-finite values")
    faiss.normalize_L2(matrix)
    _STATS["embedding_ms"] += int((time.perf_counter() - started) * 1000)
    return matrix


def generate_embedding(text):
    """Generate one normalized vector for a query or a source record."""
    matrix = generate_embeddings([text])
    return matrix[0] if matrix is not None else None


def _record_text(record):
    parts = [
        record.get("type"),
        record.get("title"),
        record.get("subject"),
        record.get("name"),
        record.get("body"),
    ]
    if record.get("task_id"):
        parts.extend([
            record.get("task_id"), record.get("owner"), record.get("due"),
            record.get("status"),
        ])
    if isinstance(record.get("cells"), dict):
        parts.extend(f"{key}: {value}" for key, value in record["cells"].items())
    return " ".join(str(part).strip() for part in parts if part not in (None, ""))[:12000]


def _eligible(record):
    if not isinstance(record, dict) or not record.get("id") or not record.get("org"):
        return False
    visibility = str(record.get("visibility") or "team").strip().lower()
    if visibility not in TEAM_VISIBILITIES:
        return False
    if record.get("type") == "notification":
        return False
    return bool(_record_text(record))


def _content_hash(record):
    material = f"{MODEL_NAME}\0{INDEX_VERSION}\0{_record_text(record)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _index_paths():
    directory = _index_dir()
    return directory, directory / INDEX_NAME, directory / METADATA_NAME


def _db_identity():
    return str(Path(storage.DB_PATH).resolve()).casefold()


def _team_records(db):
    result = []
    for row in db.execute("SELECT id,payload FROM records ORDER BY id"):
        try:
            record = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            continue
        if _eligible(record):
            result.append(record)
    return result


def _entry_rows(db):
    return storage.rows(
        db,
        "SELECT vector_id,record_id,content_hash,embedding_model,index_version "
        "FROM vector_entries ORDER BY vector_id",
    )


def _index_ids(faiss, index):
    if not index.ntotal:
        return []
    try:
        return [int(value) for value in faiss.vector_to_array(index.id_map)]
    except Exception as exc:
        raise ValueError("FAISS index does not contain an ID map") from exc


def _read_valid_index(db):
    faiss, _ = _load_packages()
    directory, index_path, metadata_path = _index_paths()
    if not index_path.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        index = faiss.read_index(str(index_path))
        entries = _entry_rows(db)
        mapped_ids = [int(row["vector_id"]) for row in entries]
        index_ids = _index_ids(faiss, index)
        valid = (
            metadata.get("index_version") == INDEX_VERSION
            and metadata.get("model") == MODEL_NAME
            and metadata.get("db_identity") == _db_identity()
            and metadata.get("vector_ids") == mapped_ids
            and index_ids == mapped_ids
            and index.ntotal == len(entries)
            and (not index.ntotal or index.d == EMBEDDING_DIMENSION)
        )
        return index if valid else None
    except Exception:
        return None


def _atomic_write(index, vector_ids):
    faiss, _ = _load_packages()
    directory, index_path, metadata_path = _index_paths()
    directory.mkdir(parents=True, exist_ok=True)
    temp_index = None
    temp_metadata = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="workmate-", suffix=".faiss.tmp", dir=directory, delete=False
        ) as file:
            temp_index = file.name
        faiss.write_index(index, temp_index)
        os.replace(temp_index, index_path)
        temp_index = None

        metadata = {
            "index_version": INDEX_VERSION,
            "model": MODEL_NAME,
            "dimension": EMBEDDING_DIMENSION,
            "db_identity": _db_identity(),
            "vector_ids": [int(value) for value in vector_ids],
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="workmate-", suffix=".json.tmp",
            dir=directory, delete=False,
        ) as file:
            temp_metadata = file.name
            json.dump(metadata, file, separators=(",", ":"))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_metadata, metadata_path)
        temp_metadata = None
    finally:
        for path in (temp_index, temp_metadata):
            if path and os.path.exists(path):
                os.unlink(path)


def _apply_correction_suppressions(db):
    """Suppress obviously superseded owner facts for the correcting person."""
    corrections = storage.rows(
        db,
        "SELECT person,words FROM corrections WHERE words IS NOT NULL",
    )
    import re

    pattern = re.compile(
        r"\b(?P<new>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+"
        r"(?:owns|handles|is responsible for)\s+"
        r"(?P<subject>[A-Za-z0-9 -]+?)\s+now,?\s+not\s+"
        r"(?P<old>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
        re.I,
    )
    for correction in corrections:
        match = pattern.search(correction["words"] or "")
        person = correction["person"]
        if not match or not person:
            continue
        old = match.group("old").casefold()
        subject_words = {
            word for word in match.group("subject").casefold().split()
            if len(word) > 2
        }
        for row in db.execute("SELECT id,payload FROM records"):
            try:
                record = json.loads(row["payload"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not storage.can_read(record, person):
                continue
            searchable = " ".join(str(record.get(key) or "") for key in (
                "body", "title", "subject"
            )).casefold()
            if old not in searchable:
                continue
            if not subject_words.issubset(set(searchable.split())):
                continue
            if match.group("new").casefold() in searchable and re.search(
                r"takes over|now owns|now handles", searchable
            ):
                continue
            db.execute(
                "INSERT OR IGNORE INTO vector_suppressions(person,record_id,reason) "
                "VALUES(?,?,?)",
                (person, row["id"], "superseded by stored correction"),
            )


def rebuild_vector_index(db=None):
    """Rebuild FAISS and its SQLite ID map from current eligible records."""
    own_db = db is None
    db = db or storage.connect()
    started = time.perf_counter()
    try:
        faiss, np = _load_packages()
        records = _team_records(db)
        texts = [_record_text(record) for record in records]
        matrix = generate_embeddings(texts) if texts else np.empty(
            (0, EMBEDDING_DIMENSION), dtype=np.float32
        )
        old = {row["record_id"]: row for row in _entry_rows(db)}

        db.execute("BEGIN IMMEDIATE")
        current_ids = {record["id"] for record in records}
        for record_id in list(old):
            if record_id not in current_ids:
                db.execute("DELETE FROM vector_entries WHERE record_id=?", (record_id,))

        for record in records:
            digest = _content_hash(record)
            prior = old.get(record["id"])
            if prior and prior["content_hash"] == digest:
                continue
            db.execute(
                """INSERT INTO vector_entries
                   (record_id,author,org,client,record_type,at,visibility,readers,
                    content_hash,embedding_model,index_version)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(record_id) DO UPDATE SET
                    author=excluded.author,org=excluded.org,client=excluded.client,
                    record_type=excluded.record_type,at=excluded.at,
                    visibility=excluded.visibility,readers=excluded.readers,
                    content_hash=excluded.content_hash,
                    embedding_model=excluded.embedding_model,
                    index_version=excluded.index_version""",
                (
                    record["id"], record.get("author"), record["org"],
                    record.get("client"), record.get("type"), record.get("at"),
                    str(record.get("visibility") or "team"),
                    json.dumps(record.get("readers", [])), digest, MODEL_NAME,
                    INDEX_VERSION,
                ),
            )
        db.commit()

        entries = _entry_rows(db)
        vector_ids = [int(row["vector_id"]) for row in entries]
        dimension = int(matrix.shape[1]) if matrix is not None and matrix.size else EMBEDDING_DIMENSION
        index = faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))
        if vector_ids:
            index.add_with_ids(matrix, np.asarray(vector_ids, dtype=np.int64))
        _atomic_write(index, vector_ids)
        _apply_correction_suppressions(db)
        db.commit()
        _STATS["rebuild_ms"] += int((time.perf_counter() - started) * 1000)
        _STATS["last_error"] = None
        return {"ok": True, "indexed": len(vector_ids), "model": MODEL_NAME}
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        _STATS["last_error"] = type(exc).__name__
        return {"ok": False, "indexed": 0, "error": type(exc).__name__}
    finally:
        if own_db:
            db.close()


def sync_vector_index():
    """Index changed SQLite records; unchanged indexes are left on disk."""
    if not _enabled():
        return {"ok": False, "indexed": 0, "disabled": True}
    db = storage.connect()
    try:
        records = _team_records(db)
        entries = _entry_rows(db)
        expected = {
            record["id"]: _content_hash(record)
            for record in records
        }
        actual = {row["record_id"]: row["content_hash"] for row in entries}
        index = _read_valid_index(db)
        if index is not None and expected == actual:
            _apply_correction_suppressions(db)
            db.commit()
            return {"ok": True, "indexed": len(entries), "unchanged": True}
        return rebuild_vector_index(db)
    finally:
        db.close()


def initialize_vector_store():
    """Load a valid persisted index, recovering it from SQLite if necessary."""
    if not _enabled():
        return {"ok": False, "indexed": 0, "disabled": True}
    db = storage.connect()
    try:
        index = _read_valid_index(db)
        if index is not None:
            return {"ok": True, "indexed": int(index.ntotal), "loaded": True}
        return rebuild_vector_index(db)
    finally:
        db.close()


def add_record(db, record):
    """Refresh the index from SQLite after the source record is committed."""
    if not _eligible(record):
        delete_record_embedding(db, record.get("id"))
        return {"ok": True, "indexed": False}
    # Full validation/rebuild also detects edits to an existing record.
    return rebuild_vector_index(db)


def update_record_embedding(db, record):
    return add_record(db, record)


def delete_record_embedding(db, record_id):
    """Remove a mapping for a source record; SQLite FK cascades suppressions."""
    if not record_id:
        return
    db.execute("DELETE FROM vector_entries WHERE record_id=?", (record_id,))
    db.execute("DELETE FROM vector_suppressions WHERE record_id=?", (record_id,))
    db.commit()
    # The next loader detects the changed ID map and rebuilds atomically.


def suppress_records(db, person, record_ids, reason=""):
    """Apply a person-specific forget/correction suppression in SQLite."""
    for record_id in set(record_ids or []):
        db.execute(
            "INSERT OR IGNORE INTO vector_suppressions(person,record_id,reason) "
            "VALUES(?,?,?)",
            (person, record_id, str(reason)[:300]),
        )
    db.commit()


def search_similar_records(
    db, query, person, allowed_record_ids, at=None, limit=8
):
    """Search FAISS, then revalidate every hit against live SQLite state."""
    allowed = set(allowed_record_ids or [])
    if not _enabled() or not allowed or not query or not person:
        return []
    started = time.perf_counter()
    try:
        faiss, np = _load_packages()
        index = _read_valid_index(db)
        if index is None:
            status = rebuild_vector_index(db)
            if not status.get("ok"):
                return []
            index = _read_valid_index(db)
        if index is None or not index.ntotal:
            return []

        query_vector = generate_embedding(query).reshape(1, -1)
        candidate_count = min(int(index.ntotal), max(64, int(limit) * 16))
        scores, ids = index.search(query_vector, candidate_count)
        mapped = {
            int(row["vector_id"]): row
            for row in db.execute(
                "SELECT vector_id,record_id,org,content_hash FROM vector_entries"
            )
        }
        suppressed = {
            row[0] for row in db.execute(
                "SELECT record_id FROM vector_suppressions WHERE person=?", (person,)
            )
        }
        results = []
        for score, vector_id in zip(scores[0], ids[0]):
            if int(vector_id) < 0:
                continue
            entry = mapped.get(int(vector_id))
            if not entry or entry["record_id"] not in allowed:
                continue
            if entry["record_id"] in suppressed:
                continue
            row = db.execute(
                "SELECT payload FROM records WHERE id=?", (entry["record_id"],)
            ).fetchone()
            if not row:
                continue
            try:
                record = json.loads(row["payload"])
            except (json.JSONDecodeError, TypeError):
                continue
            # SQLite's live payload and policy—not vector metadata—decide access.
            if not storage.can_read(record, person):
                continue
            if record.get("org") != entry["org"] or not _eligible(record):
                continue
            if _content_hash(record) != entry["content_hash"]:
                continue
            if at and _timestamp(record.get("at")) > _timestamp(at):
                continue
            results.append({"record": record, "score": float(score)})
            if len(results) >= limit:
                break
        _STATS["searches"] += 1
        _STATS["results"] += len(results)
        _STATS["search_ms"] += int((time.perf_counter() - started) * 1000)
        return results
    except Exception as exc:
        # Retrieval errors are safe: the engine continues with SQLite matching.
        _STATS["last_error"] = type(exc).__name__
        return []


def _timestamp(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def validate_vector_index():
    db = storage.connect()
    try:
        return _read_valid_index(db) is not None
    finally:
        db.close()


def get_vector_store_stats():
    db = storage.connect()
    try:
        row = db.execute("SELECT COUNT(*) FROM vector_entries").fetchone()
        count = int(row[0]) if row else 0
    finally:
        db.close()
    return {
        "index_dir": str(_index_dir()),
        "indexed_records": count,
        "model": MODEL_NAME,
        "index_version": INDEX_VERSION,
        **_STATS,
    }
