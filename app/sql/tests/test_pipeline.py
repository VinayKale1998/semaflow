"""
Stage 3 pipeline facade test.

Drives run_sql_pipeline end to end: question -> measure -> SQL ->
guardrails -> execution against Postgres. Requires the semaflow_db
container to be running.

Run from repo root: python -m pytest app/sql/tests/test_pipeline.py -v
"""
import asyncio
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

# Make app/ importable when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.sql.pipeline import run_sql_pipeline


PIPELINE_CASES = [
    {
        "question": "Top 5 product categories by revenue",
        "expected_status": "success",
        "expect_rows": True,
    },
    {
        "question": "Average order value by state",
        "expected_status": "success",
        "expect_rows": True,
    },
    {
        "question": "Lowest rated sellers by state",
        "expected_status": "success",
        "expect_rows": True,
    },
    {
        "question": "What is the return rate for the toys category?",
        "expected_status": "success",
        "expect_rows": True,
    },
    {
        "question": "What is the meaning of life?",
        "expected_status": "no_measure_matched",
        "expect_rows": False,
    },
]


@pytest.mark.parametrize("case", PIPELINE_CASES)
def test_pipeline(case: dict) -> None:
    result = asyncio.run(run_sql_pipeline(case["question"]))

    assert result.status == case["expected_status"], (
        f"Expected status '{case['expected_status']}' for question "
        f"'{case['question']}', got '{result.status}' "
        f"(reason={result.failure_reason})"
    )

    if case["expect_rows"]:
        assert result.response is not None
        assert isinstance(result.response.rows, list) and result.response.rows, (
            f"Expected non-empty rows for '{case['question']}', "
            f"got {result.response.rows if result.response else None}"
        )
