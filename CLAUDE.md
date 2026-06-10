# SemaFlow

## What this project is
A governed multi-agent analytics system. Translates business questions into 
trusted SQL or document retrieval through a semantic layer. Built on real 
Olist e-commerce data (Brazilian, messy, real joins). Portfolio project, 
not production.

## Stack
- Python 3.14, Docker, Postgres + pgvector
- Gemini Flash (text-to-SQL workhorse, via google-generativeai SDK)
  - TEMPORARILY swapped for Claude Haiku because Gemini free tier has 
    limit:0 quota in India. Interface is identical, single-file change in 
    node.py when GCP billing is enabled.
- Claude (reviewer + synthesizer, later stages)
- LangGraph (orchestration, Stage 5)
- LangSmith (tracing), Streamlit (dashboard)
- Pydantic for all data models
- sqlglot for SQL parsing in guardrails
- PyYAML for semantic layer config
- sentence-transformers (all-MiniLM-L6-v2) for embeddings, Stage 4
- rank_bm25 for keyword search, Stage 4
- cross-encoder (ms-marco-MiniLM) for reranking, Stage 4

## Project structure
- `/home/ryuzaki/dev/semaflow/app/semantic/` — semantic_layer.yaml and 
  golden_set.yaml (the governed config)
- `/home/ryuzaki/dev/semaflow/app/sql/` — text-to-SQL pipeline: models, 
  prompts, node, resolver, guardrails, executor
- `/home/ryuzaki/dev/semaflow/app/corpus/` — RAG corpus authoring, 
  chunking, embedding scripts (Stage 4)
- `/home/ryuzaki/dev/semaflow/app/corpus/docs/` — source markdown 
  (data_dictionary/, policy/, categories/)
- `/home/ryuzaki/dev/semaflow/app/rag/` — retrieval interface (Stage 4)
- `/home/ryuzaki/dev/semaflow/app/llm/` — LLM client wrappers
- `/home/ryuzaki/dev/semaflow/db/` — schema and migration scripts
- `/home/ryuzaki/dev/semaflow/data/` — raw Olist CSVs
- `/home/ryuzaki/dev/semaflow/evals/` — golden set evaluation scripts (Stage 6)
- `/home/ryuzaki/dev/semaflow/.env` — DATABASE_URL, GEMINI_API_KEY, 
  ANTHROPIC_API_KEY (load with python-dotenv)

## Environment
- WSL2 Ubuntu 26.04 on Windows. Running in native WSL via VSCode Remote.
- Docker Desktop with WSL2 integration.
- Postgres + pgvector in Docker (container: semaflow_db, image: 
  pgvector/pgvector:pg16)
- Venv: `/home/ryuzaki/dev/semaflow/.venv` — activate with 
  `source /home/ryuzaki/dev/semaflow/.venv/bin/activate`
- Python: 3.14.4
- ALWAYS use `python -m pip`, never bare `pip` (system pip conflict on 
  this distro)
- All scripts use `load_dotenv()` auto-discovery. No hardcoded paths.

### Database commands (native WSL)
- Start:   `docker compose up -d` (from project root)
- Stop:    `docker compose down`
- Status:  `docker ps`
- Connect: `docker exec -it semaflow_db psql -U semaflow -d semaflow`
- Inspect: `docker exec -it semaflow_db psql -U semaflow -d semaflow -c "\d <table>"`

## File operations
Standard Write/Edit tools work. Files are owned by ryuzaki, no sudo needed. 
The old MSYS_NO_PATHCONV / wsl -u root pattern is obsolete now that Claude 
Code runs natively inside WSL.

## Architecture rules

### Core trust boundary (Stage 3)
- The LLM (Gemini/Haiku) NEVER writes SQL. It selects from declared 
  measures and extracts parameters. The resolver assembles SQL from YAML 
  templates deterministically.
- Guardrails validate SQL BEFORE execution: read-only, schema allow-list, 
  join safety, row limit. Uses sqlglot for parsing.
- The semantic layer (YAML) is the single source of truth for measures, 
  joins, glossary, terms. Code reasons against the config, not the raw 
  database schema.
- Scope discipline: only define semantic layer entries when a golden-set 
  question needs them. Do not model every column.
- All relative time terms resolve against dataset_reference_date 
  (2018-10-17), not CURRENT_DATE.

### Stage 4 (RAG) locked scope
The Stage 4 scope was decided after explicit discussion of buzzword vs 
failure-driven techniques. DO NOT reopen these decisions without a 
specific failure on the Olist corpus that justifies a new component.

### Stage 4 (RAG) locked scope
The Stage 4 scope was decided after explicit discussion of buzzword vs 
failure-driven techniques. DO NOT reopen these decisions without a 
specific failure on the Olist corpus that justifies a new component.

What is IN SCOPE for Stage 4 (designed, building now):
- Fixed-size chunking with overlap (512 tokens / 64 overlap). Markdown-header 
  aware splitting first, then fixed-size within each section.
- doc_chunks table in Postgres next to the star schema. Columns: id (uuid 
  pk), content (text), source (text), doc_type (text), chunk_index (int), 
  embedding (vector(384)).
- HNSW index on the embedding column for approximate nearest neighbor.
- Embeddings via sentence-transformers all-MiniLM-L6-v2 (384 dims, local, 
  no API cost).
- Hybrid search: pgvector cosine + BM25, merged via Reciprocal Rank Fusion.
- Metadata filtering by doc_type before vector search.
- Retrieve top-50, rerank to top-5 via cross-encoder.
- Retrieval interface: `Retriever.retrieve(query, top_k, doc_type) -> 
  list[Chunk]`.

What is explicitly DEFERRED (do not add, do not suggest):
- Semantic chunking with a model. Solves a failure that does not exist 
  on this corpus (controlled authorship, short docs, deliberate structure).
- Query rewriting / HyDE. Addresses query sparseness, not the actual 
  failure on this corpus (category-token blurring, addressed by hybrid 
  search).
- PDF parsing. Olist has no real policy PDFs. Adding a format dependency 
  is engineering for the resume, not for the corpus.
- Agentic / multi-hop retrieval. Stage 5 problem, lives in LangGraph 
  orchestration.
- Pinecone or alternate vector stores. Pgvector is the choice; the 
  interface stays swappable but not swapped.

### The principle that governs every decision
Every component must trace to a specific failure mode on this specific 
corpus. "It is a good technique" is not sufficient. "It solves this 
retrieval failure on Olist data" is. This is the senior signal in 
interviews. Adding components without a failure story weakens both the 
build and the narrative.

## Code style
- Type hints on all functions
- Pydantic models for all data contracts between pipeline stages
- Logging via stdlib logging, not print statements
- Load .env with python-dotenv at entry points
- Use async where the pipeline supports it (node.py is async)
- Tests go in `app/<module>/tests/` using pytest
- Single-file scripts until they hurt. Do not pre-emptively abstract.

## What NOT to do
- Do not reopen Stage 4 deferred items (semantic chunking, HyDE, PDFs, 
  agentic retrieval). They are decided.
- Do not wire up LangGraph until Stage 5.
- Do not add measures or glossary entries to semantic_layer.yaml unless 
  a golden-set question requires them.
- Do not hardcode database credentials or paths. Always read from env 
  via load_dotenv.
- Do not use f-strings for SQL template substitution (injection risk). 
  Use the resolver's safe substitution.
- Do not theorize about components not yet built. If unsure of current 
  state, ask before generating.

## Current build state
- Stage 1 (data model): COMPLETE. Star schema, 9 tables loaded with FKs.
- Stage 2 (semantic layer): COMPLETE. YAML config validated.
- Stage 3 (text-to-SQL + guardrails): COMPLETE. Both checkpoint tests 
  passing (happy path + bad-join rejection).
- Stage 4 (RAG pipeline): COMPLETE. Checkpoint passed (5/5 retrieval tests).
  - DONE: Corpus authoring. 24 markdown docs across data_dictionary/ 
    (9 files), policy/ (3 files), categories/ (12 files).
  - DONE: chunk.py. Produces app/corpus/chunks.json. 147 chunks, 
    256 tokens / 32 overlap (implemented smaller than the 512/64 spec; 
    works well for short Olist docs).
  - DONE: db/add_doc_chunks.py. Creates doc_chunks table with all 
    columns including embedding VECTOR(384). B-tree index on doc_type.
  - DONE: embed.py. Loads chunks.json, embeds via all-MiniLM-L6-v2, 
    bulk-inserts 147 rows, builds HNSW index. Smoke test passed: 
    fact_orders.md in top-3 for "What does order_status mean?".
  - DONE: app/rag/retriever.py. Hybrid Retriever: _vector_search 
    (pgvector cosine + doc_type filter) + _bm25_search + _rrf_merge 
    (RRF c=60) + _rerank (cross-encoder ms-marco-MiniLM-L-6-v2). 
    Public retrieve(query, top_k, doc_type) -> list[Chunk]. BM25 corpus 
    and both models loaded once at __init__.
    - Tokenizer keeps underscores ([^a-z0-9_\s]) so identifiers like 
      order_status and customer_unique_id survive as single BM25 tokens.
    - Tokenizer also strips a stopword set. Reason: boilerplate section 
      titles ("What it does NOT cover") were matching query words 
      what/does and flooding BM25 with chunks lacking the target 
      identifier. Real corpus failure, not buzzword hygiene.
    - Known and accepted: BM25 alone never ranks fact_orders.md top-3 
      for the order_status query (length normalization buries the long 
      column-definition chunk). BM25's role is candidate recall into the 
      top-50 pool; RRF + cross-encoder do final ranking. Do not tune the 
      BM25 b parameter to "fix" this.
  - DONE: app/rag/tests/test_stage4.py. 5 hand-picked queries, asserts 
    expected source in final top-3. All 5 pass. STAGE 4 CHECKPOINT PASSED.
- Stage 4 deps added to venv: rank-bm25, pgvector, pytest.
- Stage 5 (LangGraph orchestration + reviewer): NOT STARTED.
- Stage 6 (evals): NOT STARTED.

## Operating context
- Build pace: 90 to 120 min/day. Job hunt is the primary engine.
- Daily rhythm: 2 applications + 3 cold messages + 90 to 120 min build.
- Voice rule: no em dashes anywhere. Plain English. Direct, slightly 
  dry, never motivational.
- Push back when scope creeps. Stage 4 temptation is semantic chunking, 
  HyDE, agentic retrieval. All deferred.