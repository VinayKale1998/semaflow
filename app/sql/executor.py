"""
Stage 3 execution step.

Runs a guardrail-approved ResolvedSQL against Postgres and returns a
SQLResponse with the rows. This is the production home for SQL execution,
which previously lived only inline in test_stage3.py.

Uses SQLAlchemy (same pattern as db/add_doc_chunks.py and the retriever),
not psycopg2 inline. Callers must pass SQL that has already passed
guardrails.run() — the executor does not re-validate.
"""
import logging
import os
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .models import ResolvedSQL, SQLResponse

logger = logging.getLogger(__name__)

load_dotenv()


class ExecutorError(Exception):
    pass


def execute(resolved: ResolvedSQL) -> SQLResponse:
    """Run the resolved SQL against Postgres and return a SQLResponse.

    Opens a connection per call. A global engine can be introduced later if
    the orchestrator needs to amortize connection setup.

    Raises ExecutorError on connection or execution failure.
    """
    try:
        database_url = os.environ["DATABASE_URL"]
    except KeyError as exc:
        raise ExecutorError("DATABASE_URL not set in environment") from exc

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            result = conn.execute(text(resolved.sql))
            columns: list[str] = list(result.keys())
            raw_rows = result.fetchall()
    except SQLAlchemyError as exc:
        raise ExecutorError(f"SQL execution failed: {exc}") from exc

    rows: list[dict[str, Any]] = [dict(zip(columns, row)) for row in raw_rows]
    logger.info(
        "executor: measure=%s returned %d row(s)", resolved.measure, len(rows)
    )

    return SQLResponse(
        resolved=resolved,
        rows=rows,
        columns=columns,
        row_count=len(rows),
        final_sql=resolved.sql,
        ready_to_execute=True,
    )
