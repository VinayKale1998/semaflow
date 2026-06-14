import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

DDL: list[str] = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    "DROP TABLE IF EXISTS doc_chunks CASCADE",
    """
    CREATE TABLE doc_chunks (
        id          UUID PRIMARY KEY,
        source      TEXT NOT NULL,
        doc_type    TEXT NOT NULL,
        doc_title   TEXT,
        section     TEXT,
        chunk_index INTEGER NOT NULL,
        char_start  INTEGER,
        char_end    INTEGER,
        token_count INTEGER,
        content     TEXT NOT NULL,
        embedding   VECTOR(384),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX idx_doc_chunks_doc_type ON doc_chunks(doc_type)",
]


def run_migration() -> None:
    log.info("Running doc_chunks migration")
    with engine.begin() as conn:
        for stmt in DDL:
            log.info("Executing: %s", stmt.strip().splitlines()[0])
            conn.execute(text(stmt))
    log.info("Migration complete")


def validate() -> None:
    with engine.connect() as conn:
        ext = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        print("\npgvector installed: " + str(ext == "vector"))

        cols = conn.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'doc_chunks'
                ORDER BY ordinal_position
                """
            )
        ).fetchall()
        print("\ndoc_chunks columns:")
        for col in cols:
            print("  {:<16} {:<24} nullable={}".format(col[0], col[1], col[2]))

        row_count: int = conn.execute(
            text("SELECT COUNT(*) FROM doc_chunks")
        ).scalar()
        print("\nrow count: " + str(row_count))


if __name__ == "__main__":
    run_migration()
    validate()
