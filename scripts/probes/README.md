# scripts/probes

Diagnostic scripts for the Stage 5 orchestrator. Not tests, not part of the
pipeline. They make live LLM calls and need the DB up (`docker compose up -d`).
Run from repo root with the venv: `.venv/bin/python scripts/probes/<name>.py`.

- `loop_probe.py` — runs a fixed 9-query set through the full graph; prints route, reviewer verdict, revision count, and answer. Re-run to sanity-check loop behavior end to end after orchestrator changes.
- `corpus_check.py` — retrieval-only; prints top-3 sources/scores for first-pass vs reformulated queries. Re-run when investigating whether a reformulation recovers a missed doc (category-token-blurring failure).
- `hedge_reliability.py` — runs each hedge candidate 3x; reports confidence + whether the loop fired. **RE-RUN AFTER ANY REVIEWER PROMPT OR CONFIDENCE-GATE CHANGE** — this is the probe that confirms hedges still fire reliably and resolving answers are unharmed.
- `crypto_answers.py` — runs the crypto question 3x and prints full answers; shows why crypto's score is unstable. Re-run only if revisiting the crypto-vs-q7 hedge-demo choice.
