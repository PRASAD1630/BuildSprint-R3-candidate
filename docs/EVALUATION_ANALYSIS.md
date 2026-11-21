# Evaluation Analysis

## Official public result

- **Score:** 85.0 / 85.0
- **Days:** 1–5, all public days present in this pack
- **Run:** `runs/workmate_round3_release2`
- **Harness/scorer:** supplied `tools/run_days.py` and `tools/score.py`
- **Commands:** all runner commands exited 0; all 40 brief/ask output files parsed as JSON; no invalid outputs
- **Model:** deterministic mode (`MODEL_PROVIDER=none`); **model calls: 0**
- **Privacy:** 0 leaks across 40 checks

| Area | Result | Checks |
|---|---:|---:|
| Briefs | 20 / 20 | 7 |
| Answers | 15 / 15 | 33 |
| Honesty | 15 / 15 | 40 |
| Memory | 15 / 15 | 2 |
| Privacy | 10 / 10 | 40 |
| Cost | 10 / 10 | 40 |
| Better over time | Not scored | 5 days are below the scorer's 6-day minimum |

The score is the scorer's actual result from the final fresh run. It is separate from the older `evaluation/score-day-1-to-5.json` artifact, which was retained unchanged.

## FAISS-enabled repeat

- **Score:** 85.0 / 85.0 (`runs/workmate_faiss_eval/score.json`)
- **Harness calls:** 45 total (5 ingest, 7 briefs, 33 asks); 0 failed calls and 0 invalid JSON outputs
- **Index:** 1,227 eligible shared records; FAISS validation succeeded after the run
- **Embedding:** local FastEmbed `sentence-transformers/all-MiniLM-L6-v2`; no hosted model calls
- **Privacy:** 40 scored checks, no leaks

The vector-enabled run matches the preserved pre-vector baseline. “Getting better” remains unscored because the public scorer requires at least six days. The result validates only the visible pack, not hidden days. See `VECTOR_DATABASE_EVALUATION.md`.

## Failures found and fixes

1. The fresh Windows run initially failed every command because `workmate.llm` imported Gemini eagerly. Provider imports are now lazy, so deterministic mode does not depend on any model SDK.
2. Task ownership questions containing “update” were routed to the latest-client summary. The fast path now yields to owner, due, status, and task-specific questions.
3. The brief promise parser missed the supplied Hinglish patterns and relative weekdays. It now recognizes English and Hinglish commitment forms, resolves local today/tomorrow/kal/parso and weekdays using the author's timezone, and keeps the commitment clause separate from unrelated message context.
4. A shared first-name question had been answered from a loosely matched note. Person resolution now uses the caller's organization, visible records, client context, and directory roles; unresolved cases ask for clarification.
5. The private trip answer included the fixture's en dash. Output normalization now renders that date as `20-24`, which matches the public key.
6. The first complete run scored 84.96 because a commitment summary repeated a superseded billing owner from a preceding question. The extractor now emits only the promise clause. The final scorer reports no remaining item failures or honesty penalties.

## Remaining limits

- Only Days 1–5 are present, so hidden Days 6–15 and the scorer's “better over time” area cannot be validated here.
- Evaluation deliberately disabled hosted models to avoid API use. Provider adapters are optional and were not integration-tested against a live service; the tested deterministic fallback made zero calls.
- General LLM correction extraction, model-assisted brief writing, and seven-day multi-session conversation memory remain future work. See `IMPLEMENTATION_AUDIT.md`.
