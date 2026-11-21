# WorkMate AI — The Work Assistant That Remembers

A privacy-first workplace assistant built for the WorkElate Round 3 challenge. It implements the required process-per-command CLI, SQLite persistence, feedback ingestion, personal forget requests, meeting briefs, cited Q&A, and a Streamlit showcase dashboard.

## Challenge contract

The supplied pack is the source of truth. The app supports:

```bash
python main.py ingest --day 1
python main.py brief --person p02 --date 2026-11-03
python main.py ask --person p02 --at 2026-11-02T18:00:00Z --ask "Who handles billing for NB?"
python main.py forget --person p02 --what "Forget the old travel detail"
```

The harness invokes a fresh process for every command. State is therefore stored in `workmate.sqlite3`. On ingest day N, only day N records are added and feedback from day N-1 is applied. Day 1 resets the local database.

## Install on Windows (VS Code)

1. Extract the ZIP into a folder.
2. Open that folder in VS Code.
3. Open Terminal → New Terminal.
4. Create and activate a virtual environment. If a previous setup left a broken `.venv`, remove that generated folder first. Use the regular 64-bit Python 3.13 interpreter (the free-threaded `3.13t` build can cause packages such as pandas to fall back to source builds):

```powershell
if (Test-Path .venv) { Remove-Item .venv -Recurse -Force }
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

5. Run the CLI and test the official harness:

```powershell
python main.py ingest --day 1
python tools/run_days.py --cmd "python main.py" --days 1-5 --out runs/workmate
python tools/score.py --run runs/workmate --days 1-5
```

6. Start the dashboard:

```powershell
streamlit run dashboard/app.py
```

## Optional LLM setup

The deterministic path runs without a model key. Optional JSON calls support OpenAI, Gemini, or a local Ollama endpoint. Copy `.env.example` to `.env`, set `MODEL_PROVIDER`, then add credentials for that provider. The adapter loads provider SDKs only when called and falls back to deterministic answers if a provider is unavailable:

```dotenv
MODEL_PROVIDER=openai
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4.1-mini
```

Hosted API calls require credits and are billed separately. The assistant uses the model only for selected natural-language summaries; it sends permission-filtered, time-bounded evidence and accepts citations only from retrieved source IDs. Configure `MODEL_INPUT_USD_PER_1M` and `MODEL_OUTPUT_USD_PER_1M` from the provider's current rates to estimate hosted model cost. Ollama usage is reported from its local token counters and has zero hosted API cost.

## Architecture

- `main.py`: exact challenge CLI interface; stdout is JSON.
- `workmate/engine.py`: ingestion, feedback, retrieval, briefs, Q&A, forgetting.
- `workmate/storage.py`: SQLite persistence and visibility enforcement.
- `workmate/vector_store.py`: local FAISS index and semantic retrieval; SQLite keeps source IDs and access metadata.
- `workmate/llm.py`: optional model adapter; backend remains responsible for permissions and citations.
- `dashboard/app.py`: Streamlit showcase interface.
- `tools/`: official runner, scorer, feed utility, and baseline supplied in the challenge pack.
- `data/` and `answers/`: original challenge fixtures and visible answer keys; do not modify them.

## Safety and privacy design

- Records are filtered by organization and visibility before use.
- `private` records are visible only to their author; `restricted` records only to listed readers.
- Q&A citations are checked against the caller's visible, ingested records.
- Feedback is delayed exactly one ingestion day as specified by the pack.
- Forget requests are person-scoped and excluded from future retrieval/briefs.
- Email, chat, document, and note bodies are treated as untrusted data, never executable instructions.
- No future-day records are read by ingestion.

## Local semantic search

SQLite remains authoritative for workplace records and permissions. FAISS stores normalized vectors in `data/vector_store/`; its vector-ID mapping, source IDs, content hashes, visibility metadata, and person-specific suppressions live in SQLite. The default embedding backend is FastEmbed with `sentence-transformers/all-MiniLM-L6-v2` in ONNX Runtime, avoiding a PyTorch download. The model is fetched on first vector indexing and cached locally. If FAISS or the embedding model cannot load, CLI answers fall back to deterministic SQLite retrieval.

Only organization-shared records are indexed. Private and restricted records stay in SQLite. Every FAISS hit is resolved back to its current SQLite record, checked against the already permission-filtered/forgotten/expired allowlist, then rechecked with the authoritative organization and visibility policy. Forget suppressions are scoped to one person so shared records remain available to other authorized teammates. A changed or missing index is rebuilt from SQLite. To rebuild manually, run `python tools/rebuild_vector_index.py`.

Set `VECTOR_ENABLED=false` to disable FAISS retrieval. Set `VECTOR_INDEX_DIR` for an isolated index (for example, a clean evaluation run); otherwise the index is stored under `data/vector_store/`.

## Important current limitations

The engine uses deterministic retrieval and templates as its safe default, with an optional provider-backed fallback for selected Q&A summaries. General natural-language correction extraction, complete English/Hinglish promise extraction, model-assisted brief writing, multi-session seven-day chat memory, and full natural-language understanding remain incomplete. Only the public Days 1–5 are available in this pack; hidden-day behavior still needs organizer evaluation.

## Design note

The system is a hybrid architecture: deterministic Python owns access control, time boundaries, storage, citations, and output validation; an LLM is reserved for language interpretation and extraction. Retrieval must be permission-filtered before model context is constructed. Every model-generated claim must be mapped back to an ingested source record and rejected if it cannot be verified. SQLite provides persistent local memory across short-lived CLI processes. Feedback is stored as user-scoped preference, correction, verdict, or forget state. The official evaluation harness is the acceptance test; visible answers are used for diagnostics, never hardcoded.
