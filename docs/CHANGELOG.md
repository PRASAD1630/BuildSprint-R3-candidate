# Changelog

## 2026-11-21 — continuation

- Made optional model providers lazy so CLI and deterministic operation work without an installed provider SDK.
- Added a central JSON adapter for OpenAI, Gemini, and Ollama with timeouts, provider usage counters, optional rate-based cost estimates, and deterministic fallback.
- Removed the Day 5 ingestion ceiling to support later day files when provided.
- Made feedback application idempotent across repeated ingestion of the same day.
- Changed CLI exception handling to emit a JSON error, send diagnostics to stderr, and exit nonzero.
- Added tests for provider-free operation, JSON parsing, later-day ingestion, and feedback idempotency.
- Improved task-versus-summary routing, first-name resolution, dash normalization, and English/Hinglish promise extraction with author-local relative dates.
- Replaced `.env.example` with a credential-free template and documented provider setup.
- Updated `check_subprocess.py` to validate the optional no-provider path rather than require Gemini at import time.
- Preserved pre-existing database and evaluation artifacts.
- Final public Days 1–5 scorer result: 85.0/85.0; full test suite: 8 passed.

## Earlier project state

The project already contained the CLI, SQLite persistence, organization/person visibility filters, deterministic task and brief logic, forget filtering, expiry helpers, an optional model fallback, public Days 1–5 fixtures, and prior evaluation outputs. These were retained rather than replaced.

## 2026-11-21 — FAISS local vector retrieval

- Added persistent local FAISS retrieval using FastEmbed and `sentence-transformers/all-MiniLM-L6-v2`; embeddings run locally through ONNX Runtime.
- Kept SQLite authoritative for source records, permissions, vector ID mappings, content hashes, and person-scoped forget suppressions.
- Added index validation/recovery, content-hash synchronization, access/time/forget rechecks on every hit, vector statistics, a rebuild utility, and vector recovery/security tests.
- Integrated semantic search into eligible Q&A fallback and brief context while retaining deterministic task/brief logic.
- FAISS-enabled official Days 1–5 result: 85.0/85.0; 45/45 harness calls successful; zero invalid outputs; zero hosted model calls; 1,227 records indexed.
- Full test suite: 18 passed. See `VECTOR_DATABASE_EVALUATION.md`.
