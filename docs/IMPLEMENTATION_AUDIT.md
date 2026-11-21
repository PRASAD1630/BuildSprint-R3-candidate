# WorkMate Round 3 Implementation Audit

Audit date: 2026-11-21

## Scope inspected

Reviewed the project README, data format and design note; CLI (`main.py`); all modules in `workmate/`; tests; runner, scorer and feed utility; day, feedback, task and answer fixtures; prior evaluation artifacts; `.env.example`; and the SQLite schema. The actual `.env` was not inspected or packaged because it contains credentials. Existing database and evaluation artifacts were preserved.

## Existing architecture

- `main.py` exposes the four required JSON CLI commands.
- `workmate/engine.py` provides deterministic ingestion, retrieval, Q&A, meeting briefs, forgetting, expiry, alias matching, and task updates.
- `workmate/storage.py` stores source records and person-scoped preferences, feedback, corrections, verdicts, forget requests, metadata, and audit events in SQLite. `can_read` checks organization and visibility before the engine returns evidence.
- The engine uses a bounded model fallback for some latest-client questions. The original adapter was Gemini-only, despite the configuration and example environment naming OpenAI.
- `tools/run_days.py` executes each command in a fresh process. `tools/score.py` scores output against the supplied answer keys.
- The workspace contains public data and answer keys for Days 1–5 only. There are no visible Days 6–15 fixtures here.

## Findings and changes in this continuation

7. **No semantic vector database existed.** Added a persistent local FAISS index backed by FastEmbed embeddings. SQLite remains the source of truth for content and policy; every hit is checked against the current payload, allowlist, organization, visibility, time cutoff, and person-specific suppression. Missing or corrupt indexes rebuild from SQLite.
8. **Semantic search integration and verification.** Q&A fallback and brief context now use vector results after existing deterministic filters. The FAISS-enabled Days 1–5 run scored 85/85, matched the baseline, and indexed 1,227 records. All 18 tests passed.

1. **All CLI commands crashed at import time.** `workmate/llm.py` imported `google.genai` at module load. The active environment did not provide that SDK, and deterministic commands therefore failed before reaching their fallback. Provider SDK imports are now lazy; `MODEL_PROVIDER=none` runs without any model SDK.
2. **Provider configuration did not match implementation.** The config/example exposed OpenAI while the adapter always called Gemini. The adapter now supports OpenAI, Gemini, and Ollama, with request timeouts, structured JSON parsing, usage collection, and deterministic fallback. Hosted provider exceptions do not include request content or credentials in their returned diagnostic.
3. **Ingestion rejected days after Day 5.** The fixed upper bound was removed. Ingestion reads only the requested day file and the prior day's feedback file; absent files produce empty input.
4. **Repeated ingestion duplicated feedback.** A metadata marker now ensures feedback for a particular ingestion day is applied once, while source records remain safely upserted.
5. **CLI exceptions returned success exit status.** Errors now remain JSON on stdout, details go to stderr, and the process exits nonzero.
6. **A distributable environment template contained a credential.** `.env.example` was replaced with blank provider fields. `.env` is excluded from packaging. The exposed credential must be revoked by its owner.

## Existing privacy and retrieval controls

`storage.record_rows` parses payloads and applies `can_read` before returning person-scoped records. The engine then applies question-time cutoffs, forgotten-term filtering, and temporary-fact expiry before answering or building model evidence. Model-generated citations are restricted to retrieved record IDs. Imported record text is framed as untrusted evidence in the model instructions.

## Known gaps

- Feedback corrections are persisted, but there is no general structured correction parser that resolves and applies arbitrary natural-language corrections as durable fact updates.
- Promise extraction in meeting briefs is mostly rule-based and recognizes only a limited set of English patterns; comprehensive English/Hinglish extraction, completion matching, and duplicate suppression remain incomplete.
- Model use is limited to selected Q&A summaries. Model-assisted correction extraction, broad question-intent parsing, and model-generated brief selection/writing are not implemented.
- There is no seven-day multi-session conversation-memory store. The required CLI contract has no conversation/session identifier, and durable facts remain separate from any conversation history.
- The public pack contains no Days 6–15, so hidden-day behavior cannot be scored from this workspace.
- Correction-to-vector suppression uses a narrow natural-language pattern; arbitrary corrections remain a known limitation.
- Hosted LLM providers were not contacted; this benchmark used local embeddings and no hosted model calls.
- The earlier baseline remains preserved; the FAISS-enabled result is recorded separately in `runs/workmate_faiss_eval`.

## Data preservation

The existing `workmate.sqlite3`, `evaluation/` artifacts, and `runs/workmate/` output were not overwritten. The next runner invocation must use a fresh output folder and a separate temporary database.
