# SemaFlow Stage 4: Embed and Load

## Goal
Build `app/corpus/embed.py` that reads `app/corpus/chunks.json`, generates 
embeddings via sentence-transformers, bulk-inserts into the `doc_chunks` 
table, then builds an HNSW index. Final step of the corpus loading 
pipeline before retrieval.

## Inputs
- `app/corpus/chunks.json` (~150 chunks with all metadata fields)
- `doc_chunks` table (exists, empty)
- DATABASE_URL from `.env`

## Dependencies to install
```bash
python -m pip install sentence-transformers pgvector
```

`sentence-transformers` was already installed for chunking. `pgvector` is 
the Python package that registers the VECTOR type with SQLAlchemy and 
psycopg2 so we can insert lists of floats cleanly without manually 
formatting `'[0.1,0.2,...]'` strings.

## Pipeline

### Step 1: Load
- Read `chunks.json` into a list of dicts.
- Log: number of chunks loaded.

### Step 2: Initialize model
- Load `sentence-transformers/all-MiniLM-L6-v2`.
- Confirm `embedding_dim == 384`. Assert this matches the DB schema.
- First run will download the model (~90MB) to `~/.cache/huggingface`. 
  This is expected.

### Step 3: Generate embeddings
- Batch encode all chunk contents in batches of 32.
- Show progress (sentence-transformers has built-in tqdm; `show_progress_bar=True` 
  is fine).
- Output is a numpy array of shape (n_chunks, 384).

### Step 4: Idempotent insert
- Before insert: `TRUNCATE TABLE doc_chunks;` so reruns are clean rebuilds.
- Bulk insert using SQLAlchemy + pgvector type. One commit at the end, not 
  per row. For ~150 rows executemany is fine, no need for COPY.
- Map chunks.json fields to the table columns:
  - chunks.json `chunk_id` -> table `id`
  - All other fields named identically
  - The numpy embedding row for each chunk goes into `embedding`

### Step 5: Build HNSW index
- After insert completes, create the HNSW index:

```sql
CREATE INDEX idx_doc_chunks_embedding_hnsw 
ON doc_chunks 
USING hnsw (embedding vector_cosine_ops);
```

- Use default HNSW parameters (m=16, ef_construction=64). Do not tune yet. 
  Defaults are fine for a 150-row corpus.

### Step 6: Validation (sanity check, prints to stdout)
- Total row count in doc_chunks.
- Row count per doc_type.
- Confirm HNSW index exists (query pg_indexes).
- **Smoke retrieval test:** embed the test query 
  `"What does order_status mean?"`, run a cosine-distance query against 
  doc_chunks, return the top-3 by `embedding <=> query_embedding`. Print 
  source, doc_type, section, and the first 150 chars of content for each. 
  This is just a sanity check that the embeddings are loaded and 
  searchable. It is NOT the retrieval interface.

## Constraints
- Single file. Type hints. stdlib logging for non-validation output, 
  stdout for the validation block.
- Use the pgvector package's SQLAlchemy types for clean VECTOR handling:
  `from pgvector.sqlalchemy import Vector`
- Register the vector type on the connection if needed for psycopg2:
  `from pgvector.psycopg2 import register_vector`
- Idempotent: TRUNCATE before insert so the script can be rerun safely 
  after any chunks.json change.
- Batch encode, don't loop one-at-a-time.

## What NOT to do
- Do NOT build the retrieval interface. That is the next script 
  (app/rag/retriever.py).
- Do NOT add BM25, RRF, or the cross-encoder. Those live in the 
  retrieval interface, not here.
- Do NOT tune HNSW parameters. Defaults are correct for this scale.
- Do NOT add per-chunk retry logic or fancy error handling. If the model 
  fails to load or the insert fails, let it crash with a clear error.
- Do NOT cache embeddings to disk. The table is the cache.

## After building
1. From project root: `python app/corpus/embed.py`
2. First run will be slow (~2-3 min) due to model download. 
   Subsequent runs ~30 sec.
3. Confirm validation block:
   - Row count matches chunks.json count.
   - Per-doc_type counts look right.
   - HNSW index exists.
   - Smoke retrieval returns 3 chunks where at least one is from 
     `data_dictionary/fact_orders.md` (since the test query is about 
     order_status).
4. Stop. Do not start the retrieval interface.

## Expected smoke test output
The query `"What does order_status mean?"` should retrieve chunks like:
- A chunk from `fact_orders.md` mentioning the 8 order_status values 
  (delivered, shipped, canceled, etc.)
- Possibly a chunk from `returns_and_cancellations.md` (mentions canceled 
  status)
- Possibly another fact_orders.md chunk

If none of the top-3 are from `fact_orders.md`, something is wrong with 
either the embedding generation or the insert. Surface that as a 
failure, do not paper over it.