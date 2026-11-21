# Evaluation Report

## Current continuation result

The final Windows run using the supplied harness and scorer achieved **85.0 / 85.0** on public Days 1–5. All 7 briefs and 33 asks scored fully; honesty, memory, privacy, and cost also scored fully. The runner had no failed commands or invalid JSON outputs, and the scorer found no privacy leaks. Model use was disabled (`MODEL_PROVIDER=none`), so evaluation made **0 model calls**.

The score is recorded at `runs/workmate_round3_release2/score.json` and analyzed in `docs/EVALUATION_ANALYSIS.md`.

## Historical report

The earlier `evaluation/score-day-1-to-5.json` and its associated report were produced in a different Linux workspace. Those artifacts remain unchanged for history; the result above is the fresh score for this continuation.

## Limits

The pack includes only Days 1–5, so hidden Days 6–15 and the scorer's six-day “better over time” area were not tested. Provider integration against a live model was not exercised.
