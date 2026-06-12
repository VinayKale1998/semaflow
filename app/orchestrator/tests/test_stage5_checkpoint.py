"""
Stage 5 OFFICIAL checkpoint test.

The architectural checkpoint from the bible: "a hybrid question flows end to
end and a low-confidence answer escalates." The escalation half is covered by
the Piece 4 reviewer/loop tests (test_reviewer.py, golden_set q6 hedge demo).
This file covers the happy-path half explicitly and is THE Stage 5 checkpoint,
kept separate from test_graph.py on purpose.

It drives a single hybrid question that resolves cleanly on the first pass and
asserts a strict set of conditions: correct routing, both paths produced
content, the synthesizer answered, the reviewer approved WITHOUT firing the
revision loop (revision_count == 0), and -- the key assertion -- the answer
actually references the retrieved sources rather than just sounding coherent.

CHECKPOINT QUESTION CHOICE (read before changing it):
The brief originally recommended "top 5 product categories by revenue and
explain what kind of products those categories contain." That question was
REJECTED as the checkpoint. It reliably fires the revision loop, for a real
and correct reason: the top-5-by-revenue categories outrun the corpus's
category-doc coverage AND a 5-category "explain each" request causes retrieval
dilution against top_k=5 (five chunks cannot carry a strong description for
five categories at once). The recalibrated reviewer then correctly scores the
partial-coverage answer below 0.7 on the first pass and escalates. That is the
reviewer working as designed (it should hedge on partial-coverage answers),
not a bug, so it is the wrong shape for a clean first-pass checkpoint. The
dilution effect is logged as a Stage 6 stress-test candidate (top_k tuning).

This checkpoint instead uses a single-concept hybrid: one SQL measure
(aov_by_state) paired with one well-covered RAG concept (what customer_state
means, documented in dim_customers.md). No dilution, resolves first-pass.
Verified stable across repeated runs: route=hybrid (~0.95), grounded=True,
confidence~0.95, revision_count=0.

Note on state shape: Orchestrator.run returns the final OrchestratorState, a
plain dict whose nested values are model_dump()'d. So sql_result, synthesis,
and each rag_chunk are dicts, accessed by key, not by attribute.

Requires: semaflow_db container running, ANTHROPIC_API_KEY set (router, SQL
node, synthesizer, reviewer all call Claude).

Run from repo root:
    python -m pytest app/orchestrator/tests/test_stage5_checkpoint.py -v
"""
import re
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv()

# Make app/ importable when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.orchestrator.graph import CONFIDENCE_THRESHOLD, Orchestrator

# Single-concept hybrid: aov_by_state (SQL) + customer_state definition (RAG).
# See the module docstring for why the brief's 5-category question was rejected.
CHECKPOINT_QUERY = (
    "What is the average order value by state, and what does customer_state mean?"
)


@pytest.fixture(scope="module")
def final_state() -> dict:
    return Orchestrator().run(CHECKPOINT_QUERY)


def test_routes_hybrid_with_confidence(final_state: dict) -> None:
    assert final_state["route"] == "hybrid", (
        f"Expected hybrid route, got {final_state['route']!r} "
        f"(reason={final_state['route_reason']})"
    )
    assert final_state["route_confidence"] >= CONFIDENCE_THRESHOLD


def test_both_paths_produced_content(final_state: dict) -> None:
    sql_result = final_state["sql_result"]
    assert sql_result is not None
    assert sql_result["status"] == "success", (
        f"SQL pipeline did not succeed: {sql_result.get('failure_reason')}"
    )
    rows = sql_result["response"]["rows"]
    assert rows, "Expected non-empty SQL rows"

    rag_chunks = final_state["rag_chunks"]
    assert rag_chunks is not None
    assert len(rag_chunks) > 0, "Expected at least one retrieved chunk"


def test_synthesizer_produced_answer(final_state: dict) -> None:
    synthesis = final_state["synthesis"]
    assert synthesis is not None
    assert synthesis["answer"].strip(), "Expected a non-empty answer"
    assert synthesis["has_sql"] is True
    assert synthesis["has_rag"] is True


def test_reviewer_approved_first_pass(final_state: dict) -> None:
    assert final_state["grounded"] is True
    assert final_state["confidence"] >= CONFIDENCE_THRESHOLD
    # No loop fire: the answer resolved on the first pass.
    assert final_state["revision_count"] == 0, (
        f"Loop fired unexpectedly (revision_count="
        f"{final_state['revision_count']}, reasoning="
        f"{final_state['review_reasoning']!r})"
    )
    assert final_state["errors"] == []


def test_answer_actually_references_sources(final_state: dict) -> None:
    """The load-bearing assertion: prove the synthesizer used its sources,
    not that it produced something coherent."""
    sql_result = final_state["sql_result"]
    synthesis = final_state["synthesis"]
    rag_chunks = final_state["rag_chunks"]
    answer = synthesis["answer"]

    # SQL grounding: the top state by AOV (a two-letter code like "SP") must
    # appear in the answer as a standalone token. Word boundaries guard against
    # a code matching inside an unrelated word.
    rows = sql_result["response"]["rows"]
    top_state = rows[0]["customer_state"]
    assert re.search(rf"\b{re.escape(top_state)}\b", answer), (
        f"Top state {top_state!r} from the SQL result does not appear in the "
        f"answer:\n{answer}"
    )

    # RAG grounding: at least one retrieved chunk's source file must be among
    # the sources the synthesizer recorded as used. dim_customers.md (the
    # customer_state definition) is the expected contributor here.
    chunk_sources = {chunk["source"] for chunk in rag_chunks}
    assert chunk_sources & set(synthesis["sources_used"]), (
        f"None of the retrieved chunk sources {chunk_sources} appear in "
        f"sources_used={synthesis['sources_used']}"
    )
