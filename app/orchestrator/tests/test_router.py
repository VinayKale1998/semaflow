"""
Stage 5, Piece 1 checkpoint test.

Eight queries (3 sql, 3 rag, 2 hybrid). Each asserts the router returns
the expected route.

Run from repo root: python -m pytest app/orchestrator/tests/test_router.py -v
"""
import sys
from pathlib import Path

import pytest

# Make app/ importable when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.orchestrator.router import Router


@pytest.fixture(scope="module")
def router() -> Router:
    return Router()


ROUTER_CASES = [
    # SQL cases
    {"query": "What was total revenue in 2018?", "expected": "sql"},
    {"query": "Top 10 sellers by order count", "expected": "sql"},
    {"query": "Average review score for delivered orders", "expected": "sql"},

    # RAG cases
    {"query": "What does order_status mean?", "expected": "rag"},
    {"query": "What is the difference between customer_id and customer_unique_id?", "expected": "rag"},
    {"query": "What are the seller compliance rules?", "expected": "rag"},

    # Hybrid cases
    {"query": "What is the cancellation rate and what does canceled mean?", "expected": "hybrid"},
    {"query": "Show me revenue by category and explain why some have no English name", "expected": "hybrid"},
]


@pytest.mark.parametrize("case", ROUTER_CASES)
def test_router_route(router: Router, case: dict) -> None:
    decision = router.classify(case["query"])
    assert decision.route == case["expected"], (
        f"Expected route '{case['expected']}' for query '{case['query']}', "
        f"got route='{decision.route}' reason='{decision.reason}'"
    )
