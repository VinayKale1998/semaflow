"""
Stage 4 checkpoint test.

Five hand-picked queries with the source document each should retrieve.
Asserts the expected source appears in the top 3 of the full hybrid
pipeline (vector + BM25 + RRF + cross-encoder rerank).

Run from repo root: python -m pytest app/rag/tests/test_stage4.py -v
"""
import sys
from pathlib import Path

import pytest

# Make app/ importable when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.rag.retriever import Retriever


@pytest.fixture(scope="module")
def retriever() -> Retriever:
    return Retriever()


TEST_CASES = [
    {
        "query": "What does order_status mean?",
        "expected_source": "fact_orders.md",
        "doc_type": None,
    },
    {
        "query": "How does the payment fan-out happen?",
        "expected_source": "fact_order_payments.md",
        "doc_type": None,
    },
    {
        "query": "What is the difference between customer_id and customer_unique_id?",
        "expected_source": "dim_customers.md",
        "doc_type": None,
    },
    {
        "query": "What are the rules for seller compliance?",
        "expected_source": "seller_compliance.md",
        "doc_type": "policy",
    },
    {
        "query": "What products are in the bed_bath_table category?",
        "expected_source": "category_home_comfort.md",
        "doc_type": "category_def",
    },
]


@pytest.mark.parametrize("case", TEST_CASES)
def test_retrieval_top3(retriever: Retriever, case: dict) -> None:
    results = retriever.retrieve(
        query=case["query"],
        top_k=3,
        doc_type=case["doc_type"],
    )
    sources = [c.source for c in results]
    assert case["expected_source"] in sources, (
        f"Expected {case['expected_source']} in top 3 for query "
        f"'{case['query']}', got {sources}"
    )
