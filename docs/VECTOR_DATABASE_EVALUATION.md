# WorkMate AI local vector database evaluation

## Implementation

WorkMate uses a persistent local FAISS `IndexIDMap2(IndexFlatIP)` with normalized 384-dimensional vectors from FastEmbed's `sentence-transformers/all-MiniLM-L6-v2` model. FastEmbed runs the model locally through ONNX Runtime. Model files download on first use and are reused from the local cache.

SQLite remains authoritative for source records, permissions, vector IDs, content hashes, and person-specific suppressions. Only team/organization-visible records are embedded. Before returning a semantic hit, WorkMate resolves it to the current SQLite payload and checks the caller's pre-filtered allowed IDs, current visibility policy, organization, content hash, time cutoff, and forget suppression. Private and restricted records are not embedded. A missing, stale, or corrupt FAISS index is rebuilt from SQLite.

The default index location is `data/vector_store/`. Configure `VECTOR_INDEX_DIR` to isolate an index and `FASTEMBED_CACHE_PATH` to select the model cache. Use `VECTOR_ENABLED=false` to disable vector indexing and retrieval. Run `python tools/rebuild_vector_index.py` to rebuild explicitly.

## Verification

- Full project tests: **18 passed**.
- Official runner and scorer: `tools/run_days.py --days 1-5` and `tools/score.py --days 1-5`.
- FAISS-enabled score: **85.0/85.0**, matching the preserved pre-vector baseline.
- Harness: 45 calls (5 ingestion, 7 brief, 33 ask), 0 failures, 0 invalid JSON outputs.
- Scored privacy: 40 checks, no leaks.
- Persisted shared records: 1,227; index validation succeeded after the run.
- Hosted model calls: 0. Embedding inference was local.

The fresh evaluation database and index are under `runs/workmate_faiss_eval/`; the earlier baseline and original database were not overwritten. Run artifacts are excluded from the distributable archive.

## Limits

The public pack contains only Days 1–5, so hidden-day performance and the scorer's six-day “getting better” area are unavailable. Private/restricted content is deliberately excluded from FAISS and continues through permission-filtered SQLite retrieval. Natural-language correction parsing remains narrow, and seven-day multi-session chat memory is not implemented. Hosted LLM adapters were not live-tested; this benchmark used zero hosted calls.
