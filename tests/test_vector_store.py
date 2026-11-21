import json

import numpy as np
import pytest

faiss = pytest.importorskip("faiss")

from workmate import storage, vector_store


def _record(record_id, org, body, visibility="team", author="p02", readers=None, at="2026-11-05T12:00:00Z"):
    return {
        "id": record_id,
        "org": org,
        "type": "chat",
        "at": at,
        "author": author,
        "client": "northbeam",
        "visibility": visibility,
        "readers": readers or [],
        "body": body,
    }


def _fake_embeddings(texts):
    matrix = np.zeros((len(texts), vector_store.EMBEDDING_DIMENSION), dtype=np.float32)
    for row, text in enumerate(texts):
        value = str(text).lower()
        if any(term in value for term in ("billing", "invoice", "kavya", "arjun")):
            matrix[row, 0] = 1.0
        elif any(term in value for term in ("homepage", "redesign", "wireframe")):
            matrix[row, 1] = 1.0
        else:
            matrix[row, 2] = 1.0
    return matrix


@pytest.fixture
def vector_db(tmp_path, monkeypatch):
    db_path = tmp_path / "vector-test.sqlite3"
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    monkeypatch.setattr(vector_store, "_index_dir", lambda: tmp_path / "faiss")
    monkeypatch.setattr(vector_store, "generate_embeddings", _fake_embeddings)
    monkeypatch.setenv("VECTOR_ENABLED", "true")
    monkeypatch.setattr(vector_store, "_STATS", {
        "embedding_ms": 0, "search_ms": 0, "rebuild_ms": 0,
        "searches": 0, "results": 0, "last_error": None,
    })
    db = storage.connect()
    org = storage.person_org("p02")
    yield db, org
    db.close()


def _insert(db, record):
    db.execute(
        """INSERT OR REPLACE INTO records
           (id,day,org,type,at,author,client,visibility,readers,payload)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            record["id"], 1, record["org"], record["type"], record["at"],
            record["author"], record.get("client"), record["visibility"],
            json.dumps(record.get("readers", [])), json.dumps(record),
        ),
    )
    db.commit()


def test_faiss_index_persists_mapping_and_prevents_duplicates(vector_db):
    db, org = vector_db
    _insert(db, _record("r-team", org, "Kavya owns billing and invoices"))
    _insert(db, _record("r-private", org, "Private billing record", "private"))
    _insert(db, _record("r-restricted", org, "Restricted billing record", "restricted", readers=["p03"]))

    first = vector_store.sync_vector_index()
    second = vector_store.sync_vector_index()

    assert first["ok"] and first["indexed"] == 1
    assert second["ok"] and second["unchanged"]
    assert db.execute("SELECT COUNT(*) FROM vector_entries").fetchone()[0] == 1
    assert vector_store.validate_vector_index()
    assert (vector_store._index_dir() / vector_store.INDEX_NAME).is_file()
    assert (vector_store._index_dir() / vector_store.METADATA_NAME).is_file()


def test_search_rechecks_person_and_organization_permissions(vector_db):
    db, org = vector_db
    other_org = storage.person_org("q01")
    _insert(db, _record("r-visible", org, "Billing owner and invoice details"))
    _insert(db, _record("r-other-org", other_org, "Billing owner and invoice details", author="q01"))
    vector_store.sync_vector_index()

    results = vector_store.search_similar_records(
        db, "billing owner", "p02", ["r-visible", "r-other-org"], limit=5
    )
    assert [item["record"]["id"] for item in results] == ["r-visible"]


def test_person_scoped_forget_suppression_survives_search(vector_db):
    db, org = vector_db
    _insert(db, _record("r-shared", org, "Kavya owns billing"))
    vector_store.sync_vector_index()
    vector_store.suppress_records(db, "p02", ["r-shared"], "forget billing")

    assert vector_store.search_similar_records(
        db, "billing", "p02", ["r-shared"]
    ) == []
    assert vector_store.search_similar_records(
        db, "billing", "p03", ["r-shared"]
    )


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_missing_or_corrupt_index_recovers_from_sqlite(vector_db, failure):
    db, org = vector_db
    _insert(db, _record("r1", org, "Kavya owns billing"))
    vector_store.sync_vector_index()
    index_path = vector_store._index_dir() / vector_store.INDEX_NAME
    if failure == "missing":
        index_path.unlink()
    else:
        index_path.write_bytes(b"not a faiss index")

    results = vector_store.search_similar_records(db, "billing", "p02", ["r1"])
    assert [item["record"]["id"] for item in results] == ["r1"]
    assert vector_store.validate_vector_index()


def test_stale_payload_is_discarded_until_index_is_synced(vector_db):
    db, org = vector_db
    record = _record("r1", org, "Kavya owns billing")
    _insert(db, record)
    vector_store.sync_vector_index()
    record["body"] = "The homepage redesign is in progress"
    db.execute("UPDATE records SET payload=? WHERE id='r1'", (json.dumps(record),))
    db.commit()

    assert vector_store.search_similar_records(db, "billing", "p02", ["r1"]) == []
    assert vector_store.sync_vector_index()["ok"]
    assert vector_store.search_similar_records(db, "homepage redesign", "p02", ["r1"])


def test_correction_suppresses_old_fact_for_correcting_person(vector_db):
    db, org = vector_db
    _insert(db, _record("a-old", org, "Kavya handles Northbeam billing"))
    _insert(db, _record("b-new", org, "Arjun takes over Northbeam billing from Kavya"))
    db.execute(
        "INSERT INTO corrections(person,meeting,words,created_day) VALUES(?,?,?,?)",
        ("p02", "ev-1", "No, Arjun owns billing now, not Kavya.", 3),
    )
    db.commit()
    vector_store.sync_vector_index()

    suppressed = db.execute(
        "SELECT record_id FROM vector_suppressions WHERE person='p02'"
    ).fetchall()
    assert [row[0] for row in suppressed] == ["a-old"]
    results = vector_store.search_similar_records(
        db, "billing", "p02", ["a-old", "b-new"], limit=5
    )
    assert [item["record"]["id"] for item in results] == ["b-new"]


def test_timestamp_cutoff_is_reapplied_to_vector_results(vector_db):
    db, org = vector_db
    _insert(db, _record("r-future", org, "Kavya owns billing", at="2026-11-07T12:00:00Z"))
    vector_store.sync_vector_index()
    assert vector_store.search_similar_records(
        db, "billing", "p02", ["r-future"], at="2026-11-06T12:00:00Z"
    ) == []


def test_embedding_generation_normalizes_vectors(monkeypatch):
    class FakeModel:
        def embed(self, texts):
            yield np.array([3.0] + [4.0] + [0.0] * 382, dtype=np.float32)

    monkeypatch.setattr(vector_store, "_load_packages", lambda: (faiss, np))
    monkeypatch.setattr(vector_store, "_embedding_model", lambda: FakeModel())
    vector = vector_store.generate_embedding("billing record")
    assert vector.dtype == np.float32
    assert np.isclose(np.linalg.norm(vector), 1.0)


def test_embedding_backend_failure_is_a_safe_empty_retrieval(vector_db, monkeypatch):
    db, org = vector_db
    _insert(db, _record("r1", org, "Kavya owns billing"))
    monkeypatch.setattr(vector_store, "_load_packages", lambda: (_ for _ in ()).throw(ImportError("faiss")))
    assert vector_store.search_similar_records(db, "billing", "p02", ["r1"]) == []
