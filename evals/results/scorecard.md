# SemaFlow Governance Scorecard

Generated from the latest dimension runs (most recent: 2026-06-15T10:01:46+00:00). The LLM dimensions (routing, measure selection, hedge) use Claude Haiku and are nondeterministic; expect movement of about one case across runs.

This is a governance scorecard, not an answer-quality benchmark. It scores whether the system routes correctly, selects only governed measures, refuses out-of-scope questions, blocks unsafe SQL, retrieves the right document, and hedges when the corpus cannot answer.

## Summary

| Dimension | Score | Notes |
|---|---|---|
| Routing accuracy | 35/36 (97%) | out-of-scope 10/10 (100%) |
| Measure selection | 21/21 (100%) | 2 refused via confidence gate |
| Trust boundary (refuse/proceed) | 21/21 (100%) | gate threshold 0.5 |
| Glossary resolution | 16/16 (100%) |  |
| Guardrail efficacy | 7/7 (100%) | every layer isolated |
| Retrieval hit@5 | 15/16 (94%) | MRR 0.797 |
| Hedge calibration | 9/10 (90%) | resolving 5/5 (100%), hedge 4/5 (80%) |

## Routing

Classifies a question by SHAPE. Out-of-scope questions are still routed correctly even though the system will later refuse or hedge.

Confusion matrix (rows = expected, cols = actual):

| expected \ actual | sql | rag | hybrid |
|---|---|---|---|
| sql | 15 | 0 | 0 |
| rag | 1 | 14 | 0 |
| hybrid | 0 | 0 | 6 |

Misses:
- `r8` (rag_positive): expected rag, got sql (conf 0.85)

## Measure selection and the SQL trust boundary

The node selects a governed measure; a selection below the 0.5 confidence gate becomes an honest `no_measure_matched` refusal. 2 out-of-scope question(s) were refused via the gate (the rest by the node directly).

All measure, status, and glossary checks passed.

## Guardrails

Each adversarial SQL must be rejected by exactly one layer, in isolation (the other three pass).

| layer | caught |
|---|---|
| joins_safe | 1/1 (100%) |
| is_read_only | 3/3 (100%) |
| schema_valid | 1/1 (100%) |
| row_limit_enforced | 2/2 (100%) |

## Retrieval

Hybrid retrieval (pgvector + BM25, RRF, cross-encoder rerank). hit@5 = 15/16 (94%), MRR = 0.797.

Misses:
- `r8`: expected ['category_health_beauty.md'], got ['category_perfumery.md', 'category_baby.md', 'dim_category_translation.md']

## Hedge calibration

Confidence gate = 0.7. Resolving questions must clear it; unanswerable questions must trip it (the loop fires and, finding no better source, terminates with an honest hedge).

| case | category | expects hedge | confidence | revisions | result |
|---|---|---|---|---|---|
| h1 | hybrid_positive | False | 0.85 | 0 | PASS |
| h3 | hybrid_positive | False | 0.95 | 0 | PASS |
| r1 | rag_positive | False | 0.95 | 0 | PASS |
| r4 | rag_positive | False | 0.90 | 0 | PASS |
| r6 | rag_positive | False | 0.95 | 0 | PASS |
| g1 | rag_oos | True | 0.20 | 1 | PASS |
| g2 | rag_oos | True | 0.15 | 1 | PASS |
| g3 | rag_oos | True | 0.15 | 1 | PASS |
| g4 | rag_oos | True | 0.95 | 0 | FAIL |
| g5 | rag_oos | True | 0.15 | 1 | PASS |
