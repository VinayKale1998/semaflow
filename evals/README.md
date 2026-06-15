# Stage 6: Governance Evals

This is a **governance scorecard**, not a generic answer-quality benchmark. It
does not ask "is the answer good?" It asks the questions that matter for a
governed analytics system:

- Does the router send each question down the right path?
- Does the system select only **declared** measures, and **refuse** when no
  governed measure fits?
- Do the SQL guardrails block unsafe queries, each for the right reason?
- Does retrieval surface the right document?
- When the corpus cannot answer, does the system **hedge** instead of fabricate?

The senior signal is in the negative cases. An out-of-scope SQL question is still
SQL-shaped, so the router should route it to `sql`; the system must then refuse
(`no_measure_matched`) rather than bend an unrelated measure. An out-of-scope RAG
question must hedge, not invent policy. Routing (shape) and feasibility
(governance) are scored as separate dimensions on purpose: a correct refusal is a
pass.

## Layout

```
evals/
  datasets/
    eval_questions.yaml    36 labeled questions (positive + out-of-scope)
    adversarial_sql.yaml   7 SQL strings, each must trip one guardrail layer
  loader.py                pydantic models + YAML loaders
  scorers.py               pure scoring functions (no I/O)
  results_io.py            JSON result envelope read/written by every runner
  runners/                 one module per dimension
  report.py                results/*.json -> results/scorecard.md
  run_evals.py             CLI entry point
  results/                 per-dimension JSON + scorecard.md
  tests/test_scorers.py    pure unit tests for the scorers and loader
```

## Running

From the project root, venv active. The DB must be up (`docker compose up -d`)
for the retrieval and hedge dimensions.

```bash
python -m evals.run_evals --all               # run everything, write scorecard
python -m evals.run_evals guardrails routing  # run a subset
python -m evals.run_evals --report            # rebuild scorecard from saved JSONs
```

Cost per dimension: `guardrails` is offline (no LLM, no DB); `routing` and
`measure_selection` make Haiku calls; `retrieval` uses local models + pgvector;
`hedge` runs the full orchestrator and is the most expensive. The runners persist
their results, so the scorecard can be rebuilt without rerunning the LLM passes.

The LLM dimensions use Claude Haiku and are mildly nondeterministic; expect about
one case of movement across runs.

## What the eval found, and what it changed

The eval is not just a report card. It drove two fixes, each tracing to a
specific failure it surfaced. This is the point: a component is justified by a
failure, not by being a good idea.

**1. The SQL trust boundary had a hole.** The text-to-SQL node is instructed to
pick the closest measure even when none fits well, and nothing downstream gated
on its confidence. So an out-of-scope question ("total freight cost per seller")
could select a wrong measure at confidence ~0.15, pass the guardrails, execute,
and return wrong-but-valid rows. In-scope questions score ~0.95, so the signal
was clean. Fix: a measure-confidence gate in `run_sql_pipeline`
(`MEASURE_CONFIDENCE_THRESHOLD`), below which the pipeline returns an honest
`no_measure_matched`. Mirrors the reviewer's confidence gate on the RAG side.

**2. The reviewer's hedge detection was overfit.** The reviewer is supposed to
score any "the sources do not cover this" non-answer below the confidence gate so
the loop fires. It did this for the two examples worked into its prompt, but new
unanswerable topics (PII retention, chargeback disputes) scored 0.85 and slipped
through: the reviewer was rewarding the fluent "here is what the corpus DOES
contain, but not your topic" framing as partial resolution. Fix: the reviewer
prompt was rewritten from topic examples into a general decision procedure
(identify the asked-for thing; did the answer deliver it; if not, cap confidence
at 0.2). Hedge calibration went from 7/10 to 9/10, and crucially it generalized
to held-out topics, not just the ones added to the prompt.

## Known limitations (kept, not hidden)

- **`r8`** ("what kinds of products are in the health_beauty category?") fails
  both routing and retrieval. The phrasing reads as a SQL "list products" request
  to the router, and retrieval blurs across adjacent category docs. It is the
  recurring hard case and is left in as an honest stress point, not removed.
- **`g4`** ("SLA for customer support response times?") scores high confidence
  rather than hedging. The compliance docs contain seller response-time
  expectations that legitimately resemble a support SLA, so the reviewer treating
  it as partially answerable is defensible. Kept as a documented borderline.
