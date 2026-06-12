# SemaFlow Stage 4: doc_chunks Migration

## Goal
Build `db/add_doc_chunks.py` that creates the `doc_chunks` table in the 
existing semaflow Postgres database. Does NOT load any data. Does NOT 
rebuild the star schema.

## Connection
- Read DATABASE_URL from environment via python-dotenv.
- Use SQLAlchemy `create_engine` and a transactional context (the same 
  pattern as the existing star schema build script).

## What this script does, in order

1. Ensure the pgvector extension is enabled:
   `CREATE EXTENSION IF NOT EXISTS vector;`

2. Drop the doc_chunks table if it exists (idempotent rebuilds):
   `DROP TABLE IF EXISTS doc_chunks CASCADE;`

3. Create the doc_chunks table:

```sql
CREATE TABLE doc_chunks (
    id              UUID PRIMARY KEY,
    source          TEXT NOT NULL,
    doc_type        TEXT NOT NULL,
    doc_title       TEXT,
    section         TEXT,
    chunk_index     INTEGER NOT NULL,
    char_start      INTEGER,
    char_end        INTEGER,
    token_count     INTEGER,
    content         TEXT NOT NULL,
    embedding       VECTOR(384),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

4. Create a B-tree index on `doc_type` for metadata filtering before 
   vector search:

```sql
CREATE INDEX idx_doc_chunks_doc_type ON doc_chunks(doc_type);
```

5. Do NOT create the HNSW index yet. HNSW builds more efficiently after 
   data is loaded. The embed.py script in the next step creates the 
   HNSW index after batch insert.

## Validation
After running, print:
- Confirmation that pgvector extension is installed (query pg_extension).
- The table's column list (query information_schema.columns).
- The current row count (should be zero).

## Constraints
- Single file, ~80 lines or less.
- Type hints. Logging via stdlib `logging`, not print, except validation 
  output to stdout.
- Use SQLAlchemy `text()` for raw DDL, executed inside `engine.begin()` 
  for transactional safety.
- No CLI args. Hardcoded behavior. Runs once per schema change.

## What NOT to do
- Do NOT load chunks.json into the table. That is embed.py's job.
- Do NOT create the HNSW index yet.
- Do NOT add foreign keys to the star schema tables. doc_chunks is 
  standalone.
- Do NOT use Alembic or any migration framework. This is a script, not 
  a managed migration.

## After building
1. Run from project root: `python db/add_doc_chunks.py`
2. Confirm validation output shows the table created with the right 
   columns and zero rows.
3. Stop. Do not move to embedding.