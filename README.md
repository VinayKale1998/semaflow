# SemaFlow

**Governed LLM analytics where the model never writes the SQL.**

SemaFlow turns plain business questions into trusted answers over a real, messy
e-commerce data warehouse. The difference from a typical text-to-SQL demo is the
trust boundary: the language model is not allowed to write SQL. It picks from a
declared set of approved measures, and deterministic code assembles and
validates the query before anything touches the database.

The model can be wrong without being dangerous.

> Most LLM analytics projects let the model write the SQL and hope it is right.
> This one does not let it write SQL at all.

---

## Contents

- [The problem](#the-problem)
- [How SemaFlow solves it](#how-semaflow-solves-it)
- [A question, end to end](#a-question-end-to-end)
- [The trust layer](#the-trust-layer)
- [Architecture](#architecture)
- [Stack](#stack)
- [Project layout](#project-layout)
- [Quickstart](#quickstart)
- [Scope and non-goals](#scope-and-non-goals)
- [Status](#status)

---

## The problem

Ask a normal AI tool "which product categories made the most money last
quarter?" and it will write SQL for you. That is the part no serious business can
deploy. A model writing raw SQL can:

- **Invent columns or tables** that do not exist, and return confident nonsense.
- **Leak data across tables** by joining things that should never be joined.
- **Run a query nobody authorized**, including a write or a delete.
- **Hallucinate the answer** even when the query fails.

The usual response is "we will review the SQL" or "we will prompt it better."
Neither makes the risk go away. SemaFlow removes the risk by construction.

## How SemaFlow solves it

The language model is demoted from **author** to **selector**.

1. A **semantic layer** (a governed YAML file) declares every measure the system
   is allowed to compute: revenue, average order value, return rate, seller
   ratings, and so on. Each measure is a vetted SQL template with named
   parameters.
2. The model reads the question and does two narrow jobs: **pick the right
   measure** and **extract the parameters** (a category, a state, a time
   window). It never produces SQL text.
3. A deterministic **resolver** fills the chosen template. No string formatting,
   no model output in the query.
4. **Four guardrail layers** parse the assembled SQL with `sqlglot` and validate
   it before execution:

   | Guardrail | What it blocks |
   |---|---|
   | Read-only | Any write, update, delete, or DDL |
   | Schema allow-list | Tables and columns outside the approved set |
   | Join safety | Joins that cross trust boundaries between tables |
   | Row limit | Result sets above a hard ceiling |

   All four run on every query and report independently, so a failure tells you
   exactly which rule it broke.

5. Only then does the query run.

The same question can also need prose, not numbers ("what does this return rate
mean for sellers?"). Those route to a **retrieval pipeline** over a governed
document corpus. Questions that need both get a **hybrid** answer.

## A question, end to end

> **"What is the return rate in health_beauty, and what does that mean for
> sellers?"**

1. **Router** classifies this as `hybrid` (needs a number and an explanation).
2. **SQL path:** the model selects the `return_rate_by_category` measure and
   extracts `category = health_beauty`. The resolver builds the query from the
   governed template, the guardrails pass it, and it runs.
3. **Retrieval path:** hybrid search (vector + keyword) pulls the most relevant
   chunks from the seller-compliance and category documents.
4. **Synthesizer** writes one grounded answer using the SQL result and the
   retrieved text.
5. **Reviewer** checks the answer on two separate axes (below) before it is
   shown.

## The trust layer

A LangGraph orchestration layer sits on top, with a reviewer that asks two
different questions:

- **Grounded:** does every claim trace back to a real SQL row or a retrieved
  document? An honest "the sources do not cover this" is grounded, because it
  tells no lies.
- **Confident:** does the answer actually resolve the question that was asked?

These come apart on purpose. A fluent hedge can be perfectly grounded and still
useless. When confidence is low, the system **reformulates the question once and
retries**. If it still cannot answer, it **hedges honestly instead of bluffing**.

A Streamlit UI surfaces all of this as first-class signals: the route taken, the
confidence score, whether the answer is grounded, and whether the system
self-corrected. Every model call is traced end to end with LangSmith.

## Architecture

```
                         Business question
                                |
                          +-----------+
                          |  Router   |   sql / rag / hybrid
                          +-----------+
                          /     |      \
               +---------+      |       +-----------+
               | SQL path|      |       |  RAG path |
               +---------+      |       +-----------+
   model selects measure + params   hybrid retrieval
   resolver builds SQL from YAML    (vector + BM25, fused,
   4 guardrails validate            reranked top-50 -> top-5)
   query executes
                          \     |      /
                          +-----------+
                          |Synthesizer|   one grounded answer
                          +-----------+
                                |
                          +-----------+
                          | Reviewer  |   grounded? confident?
                          +-----------+
                          /            \
                 confident          low confidence
                     |               reformulate once,
                  answer            then hedge honestly
                     |               /
                  +-------------------+
                  | Streamlit trust UI|
                  +-------------------+
```

The retrieval path is itself failure-driven: documents are chunked, embedded
locally (no API cost), and searched with vector similarity **and** keyword
matching, merged with Reciprocal Rank Fusion, then reranked with a
cross-encoder. There is a visual, step-by-step walkthrough of this pipeline in
[`app/rag/walkthrough/`](app/rag/walkthrough/index.html) (open `index.html` in a
browser).

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.14 |
| Data warehouse | Postgres + pgvector (Docker) |
| Dataset | Brazilian Olist e-commerce (real joins, real data quality problems) |
| Text-to-SQL model | Claude Haiku (selector role only) |
| Synthesizer / reviewer | Claude Sonnet / Haiku |
| Orchestration | LangGraph |
| Tracing | LangSmith |
| SQL parsing | sqlglot |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2, local) |
| Keyword search | rank_bm25 |
| Reranking | cross-encoder (ms-marco-MiniLM) |
| Data contracts | Pydantic |
| Config | PyYAML (the semantic layer) |
| UI | Streamlit |

## Project layout

```
app/
  semantic/      semantic_layer.yaml + golden_set.yaml (the governed source of truth)
  sql/           text-to-SQL: models, prompts, node, resolver, guardrails, executor, pipeline
  orchestrator/  LangGraph: router, graph, synthesizer, reviewer
  corpus/        document authoring, chunking, embedding (RAG corpus)
  rag/           retrieval interface + visual pipeline walkthrough
  llm/           LLM client wrappers + LangSmith tracing
  ui/            Streamlit trust UI
db/              schema and migration scripts
data/            raw Olist CSVs (downloaded, not committed)
evals/           golden-set evaluation (planned)
scripts/probes/  diagnostic scripts (not tests)
```

## Quickstart

Requires Docker and Python 3.14.

```bash
# 1. Environment
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

# 2. Secrets: create a .env file in the project root
#    DATABASE_URL=postgresql://semaflow:semaflow_local_pw@localhost:5432/semaflow
#    ANTHROPIC_API_KEY=sk-ant-...

# 3. Database
docker compose up -d

# 4. Data: download the public Olist CSVs and build the star schema
python app/download_olist.py
python app/load_raw.py
python app/build_geo_lookup.py
python app/build_star_schema.py

# 5. RAG corpus: chunk, store, and embed the documents
python db/add_doc_chunks.py
python app/corpus/chunk.py
python app/corpus/embed.py

# 6. Run the trust UI
streamlit run app/ui/streamlit_app.py
```

Run the test suite with `pytest app/` (scope to `app/` so it does not scan the
Docker data volume).

## Lessons Learned

- **Data quality problems matter more than model quality.** A naive order-items
  to payments join inflated revenue by about 4.5% (13.59M true versus 14.21M
  fanned out on Olist). The semantic layer exists because correctness failures
  often originate in data modeling, not in model inference.
- **Grounded and confident are not the same thing.** An answer can be fully
  grounded and still fail to resolve the question. The reviewer evaluates the two
  separately, so an honest hedge scores low confidence without being marked a lie.
- **Semantic governance beats prompt engineering.** Business definitions such as
  return rate, average order value, and seller performance needed governed
  measures, with rules like a five-review minimum baked into the template, rather
  than increasingly elaborate prompts.
- **Observability changes system design.** LangSmith traces surfaced failure
  modes that were invisible from the outputs alone, which drove changes to routing
  and reviewer behavior, including the confidence-gate recalibration.
- **Every component should justify its existence.** Semantic chunking, HyDE, and
  multi-hop retrieval were evaluated and deliberately excluded because the
  observed failure modes on this corpus did not justify the added complexity.

## Scope and non-goals

Every component had to trace to a real failure on this specific corpus before it
earned a place in the build. The goal was not the longest feature list.

Some popular techniques were considered and **deliberately left out**, because
they solved problems this corpus does not have:

- **Semantic chunking with a model.** The documents are short, deliberately
  structured, and authored under control. Fixed-size chunking already works.
- **Query rewriting / HyDE.** The real retrieval failure here was category
  tokens blurring together, which hybrid search fixes directly.
- **Agentic / multi-hop retrieval.** Out of scope for the retrieval layer; the
  orchestrator handles reformulation.
- **PDF parsing and alternate vector stores.** No real PDFs in this dataset, and
  pgvector is sufficient. The interface stays swappable but is not swapped.

Knowing what to leave out is part of the design.

## Status

This is a portfolio project on a public dataset, not a production system.

- Stage 1 to 5 complete: data model, semantic layer, text-to-SQL with
  guardrails, hybrid RAG, and the LangGraph orchestrator with the reviewer and
  trust UI.
- Stage 6 (a golden-set evaluation harness) is next.
