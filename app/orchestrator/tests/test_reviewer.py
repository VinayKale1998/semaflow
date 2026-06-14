"""
Stage 5, Piece 4 checkpoint test.

Drives the Reviewer directly with hand-built states so each of its three
judgments is exercised in isolation, without depending on the full pipeline
to happen to produce a grounded answer, a hedge, or a hallucination:

  1. grounded + resolving  -> grounded=True, confidence >= threshold, no revision
  2. grounded but a hedge  -> grounded=True, confidence < threshold, revised_query set
  3. ungrounded (invented) -> grounded=False

Cases 1 and 2 are the confidence gate the graph depends on: a grounded
non-answer still has to score low so route_after_review sends it into the
one-shot revision pass. Case 3 is the groundedness check.

Requires: ANTHROPIC_API_KEY set (reviewer = Haiku). No DB, no retriever.

Run from repo root: python -m pytest app/orchestrator/tests/test_reviewer.py -v -s
"""
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

# Make app/ importable when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.orchestrator.graph import CONFIDENCE_THRESHOLD
from app.orchestrator.reviewer import Reviewer


@pytest.fixture(scope="module")
def reviewer() -> Reviewer:
    return Reviewer()


def _sql_state(query: str, measure: str, columns: list[str], rows: list[dict], answer: str) -> dict:
    """Minimal OrchestratorState for a successful SQL route."""
    return {
        "query": query,
        "route": "sql",
        "sql_result": {
            "status": "success",
            "response": {
                "resolved": {"measure": measure},
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            },
        },
        "rag_chunks": None,
        "synthesis": {"answer": answer},
    }


def _rag_state(query: str, chunks: list[dict], answer: str) -> dict:
    """Minimal OrchestratorState for a RAG route."""
    return {
        "query": query,
        "route": "rag",
        "sql_result": None,
        "rag_chunks": chunks,
        "synthesis": {"answer": answer},
    }


# 1. Grounded and resolving: every claim is in the chunk, the question is answered.
GROUNDED_RESOLVING = _rag_state(
    query="What does order_status mean?",
    chunks=[
        {
            "source": "fact_orders.md",
            "section": "order_status",
            "content": (
                "order_status is the lifecycle state of an order. Values: delivered "
                "(reached the customer), shipped (handed to carrier), canceled "
                "(order voided), unavailable, invoiced, processing, approved, "
                "created. Most orders in the dataset are delivered."
            ),
        }
    ],
    answer=(
        "order_status is the lifecycle state of an order. Its values are delivered, "
        "shipped, canceled, unavailable, invoiced, processing, approved, and created. "
        "Most orders are delivered."
    ),
)

# 2. Grounded but a hedge: the answer tells no lies, but the chunk does not
#    contain the figure the user asked for, so the question is not resolved.
#    The reviewer must score this LOW and propose a revised query.
GROUNDED_HEDGE = _rag_state(
    query="What is the late-shipment penalty fee charged to sellers, in reais?",
    chunks=[
        {
            "source": "policy/seller_compliance.md",
            "section": "Overview",
            "content": (
                "Sellers are expected to ship on time. Repeated late shipments affect "
                "a seller's standing on the platform. This document describes the "
                "compliance program in general terms."
            ),
        }
    ],
    answer=(
        "The retrieved documents describe the seller compliance program in general "
        "terms but do not state a specific late-shipment penalty fee amount in reais."
    ),
)

# 3. Ungrounded: the answer invents a category and a figure not in the rows.
UNGROUNDED_INVENTED = _sql_state(
    query="Top product categories by revenue.",
    measure="revenue_by_category",
    columns=["category", "revenue"],
    rows=[
        {"category": "health_beauty", "revenue": 1258681.34},
        {"category": "watches_gifts", "revenue": 1205005.68},
        {"category": "bed_bath_table", "revenue": 1036988.68},
    ],
    answer=(
        "The top category by revenue is toys, which generated 5,000,000 reais, "
        "followed by health_beauty at 1,258,681.34 reais."
    ),
)


def test_grounded_resolving_answer_scores_high(reviewer: Reviewer) -> None:
    result = reviewer.review(GROUNDED_RESOLVING)
    print(f"\n[resolving] grounded={result.grounded} conf={result.confidence:.2f} "
          f"revised={result.revised_query!r}\n  {result.reasoning}")

    assert result.grounded is True, f"expected grounded answer: {result.reasoning}"
    assert result.confidence >= CONFIDENCE_THRESHOLD, (
        f"a fully resolving answer should clear the gate, got {result.confidence:.2f}"
    )
    assert result.revised_query is None, (
        f"no revision should be proposed for a confident answer, got {result.revised_query!r}"
    )


def test_grounded_hedge_scores_low_and_proposes_revision(reviewer: Reviewer) -> None:
    result = reviewer.review(GROUNDED_HEDGE)
    print(f"\n[hedge] grounded={result.grounded} conf={result.confidence:.2f} "
          f"revised={result.revised_query!r}\n  {result.reasoning}")

    # The hedge is honest, so it is grounded, but it did not resolve the
    # question, so it must fail the confidence gate and offer a retry.
    assert result.grounded is True, (
        f"an honest non-answer is grounded, it tells no lies: {result.reasoning}"
    )
    assert result.confidence < CONFIDENCE_THRESHOLD, (
        f"a hedge should fail the gate, got {result.confidence:.2f}"
    )
    assert result.revised_query, (
        "a low-confidence review must propose a revised query for the second pass"
    )


def test_ungrounded_invented_figure_flagged(reviewer: Reviewer) -> None:
    result = reviewer.review(UNGROUNDED_INVENTED)
    print(f"\n[invented] grounded={result.grounded} conf={result.confidence:.2f} "
          f"revised={result.revised_query!r}\n  {result.reasoning}")

    assert result.grounded is False, (
        f"an answer citing a category and figure absent from the rows is not "
        f"grounded: {result.reasoning}"
    )
