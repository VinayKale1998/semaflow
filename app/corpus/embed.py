import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import sqlalchemy as sa
from dotenv import load_dotenv
from pgvector.sqlalchemy import Vector
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

CHUNKS_PATH = Path("app/corpus/chunks.json")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384
BATCH_SIZE = 32

load_dotenv()
engine = sa.create_engine(os.environ["DATABASE_URL"])

_doc_chunks = sa.Table(
    "doc_chunks",
    sa.MetaData(),
    sa.Column("id", PG_UUID(as_uuid=True)),
    sa.Column("source", sa.Text),
    sa.Column("doc_type", sa.Text),
    sa.Column("doc_title", sa.Text),
    sa.Column("section", sa.Text),
    sa.Column("chunk_index", sa.Integer),
    sa.Column("char_start", sa.Integer),
    sa.Column("char_end", sa.Integer),
    sa.Column("token_count", sa.Integer),
    sa.Column("content", sa.Text),
    sa.Column("embedding", Vector(EMBED_DIM)),
)


def load_chunks() -> list[dict[str, Any]]:
    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    log.info("Loaded %d chunks from %s", len(chunks), CHUNKS_PATH)
    return chunks


def load_model() -> SentenceTransformer:
    model = SentenceTransformer(MODEL_NAME)
    actual_dim = model.get_sentence_embedding_dimension()
    assert actual_dim == EMBED_DIM, f"Expected {EMBED_DIM} dims, got {actual_dim}"
    log.info("Model loaded: %s (%d dims)", MODEL_NAME, actual_dim)
    return model


def generate_embeddings(model: SentenceTransformer, chunks: list[dict[str, Any]]) -> np.ndarray:
    texts = [c["content"] for c in chunks]
    embeddings: np.ndarray = model.encode(texts, batch_size=BATCH_SIZE, show_progress_bar=True)
    log.info("Generated embeddings: shape=%s", embeddings.shape)
    return embeddings


def insert_chunks(chunks: list[dict[str, Any]], embeddings: np.ndarray) -> None:
    rows = [
        {
            "id": uuid.UUID(c["chunk_id"]),
            "source": c["source"],
            "doc_type": c["doc_type"],
            "doc_title": c["doc_title"],
            "section": c["section"],
            "chunk_index": c["chunk_index"],
            "char_start": c["char_start"],
            "char_end": c["char_end"],
            "token_count": c["token_count"],
            "content": c["content"],
            "embedding": emb.tolist(),
        }
        for c, emb in zip(chunks, embeddings)
    ]
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE doc_chunks"))
        conn.execute(_doc_chunks.insert(), rows)
    log.info("Inserted %d rows into doc_chunks", len(rows))


def build_hnsw_index() -> None:
    log.info("Building HNSW index")
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS idx_doc_chunks_embedding_hnsw"))
        conn.execute(text(
            "CREATE INDEX idx_doc_chunks_embedding_hnsw "
            "ON doc_chunks USING hnsw (embedding vector_cosine_ops)"
        ))
    log.info("HNSW index created")


def validate(model: SentenceTransformer) -> None:
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM doc_chunks")).scalar()
        print(f"\ntotal rows: {total}")

        type_counts = conn.execute(text(
            "SELECT doc_type, COUNT(*) FROM doc_chunks GROUP BY doc_type ORDER BY doc_type"
        )).fetchall()
        print("\nrows per doc_type:")
        for doc_type, count in type_counts:
            print(f"  {doc_type:<20} {count}")

        idx_name = conn.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'doc_chunks' "
            "AND indexname = 'idx_doc_chunks_embedding_hnsw'"
        )).scalar()
        print(f"\nHNSW index exists: {idx_name is not None}")

        query = "What does order_status mean?"
        q_emb = model.encode([query])[0].tolist()
        q_str = "[" + ",".join(map(str, q_emb)) + "]"

        hits = conn.execute(
            text(
                "SELECT source, doc_type, section, LEFT(content, 150) "
                "FROM doc_chunks "
                "ORDER BY embedding <=> CAST(:q AS vector) "
                "LIMIT 3"
            ),
            {"q": q_str},
        ).fetchall()

        print(f'\nsmoke test: "{query}"')
        for i, hit in enumerate(hits, 1):
            print(f"\n  [{i}] source={hit[0]}  doc_type={hit[1]}  section={hit[2]}")
            print(f"       {hit[3]}")

        sources = {h[0] for h in hits}
        if any("fact_orders" in s for s in sources):
            print("\nsmoke test PASSED: fact_orders.md in top-3")
        else:
            print("\nsmoke test FAILED: fact_orders.md not in top-3 -- check embeddings")


def main() -> None:
    chunks = load_chunks()
    model = load_model()
    embeddings = generate_embeddings(model, chunks)
    insert_chunks(chunks, embeddings)
    build_hnsw_index()
    validate(model)


if __name__ == "__main__":
    main()
