"""
Stage 5, Piece 2 checkpoint test.

Drives the orchestrator end to end for each route: sql, rag, hybrid.
Asserts the route is correct, the expected result fields are populated,
the others are None, and no unexpected node errors occurred.

Requires: semaflow_db container running, ANTHROPIC_API_KEY set (router +
SQL node call Claude Haiku).

Run from repo root: python -m pytest app/orchestrator/tests/test_graph.py -v
"""
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

# Make app/ importable when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.orchestrator.graph import Orchestrator


@pytest.fixture(scope="module")
def orchestrator() -> Orchestrator:
    return Orchestrator()


ORCHESTRATOR_CASES = [
    {
        "query": "Top 5 product categories by revenue",
        "expected_route": "sql",
        "must_have": ["sql_result"],
        "must_be_none": ["rag_chunks"],
    },
    {
        "query": "What does order_status mean?",
        "expected_route": "rag",
        "must_have": ["rag_chunks"],
        "must_be_none": ["sql_result"],
    },
    {
        "query": "Show me the top 5 product categories by revenue and explain what those categories contain.",
        "expected_route": "hybrid",
        "must_have": ["sql_result", "rag_chunks"],
        "must_be_none": [],
    },
]


@pytest.mark.parametrize("case", ORCHESTRATOR_CASES)
def test_orchestrator(orchestrator: Orchestrator, case: dict) -> None:
    state = orchestrator.run(case["query"])

    assert state["route"] == case["expected_route"], (
        f"Expected route '{case['expected_route']}' for query "
        f"'{case['query']}', got '{state['route']}' "
        f"(reason={state['route_reason']})"
    )

    for key in case["must_have"]:
        assert state[key] is not None, (
            f"Expected '{key}' populated for query '{case['query']}', got None"
        )

    for key in case["must_be_none"]:
        assert state[key] is None, (
            f"Expected '{key}' to be None for query '{case['query']}', "
            f"got {state[key]!r}"
        )

    assert state["errors"] == [], (
        f"Expected no errors for query '{case['query']}', got {state['errors']}"
    )
