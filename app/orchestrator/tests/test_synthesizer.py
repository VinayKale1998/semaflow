"""
Stage 5, Piece 3 checkpoint test.

Drives the full graph (router -> sql/rag/hybrid -> synthesizer) for each
route and checks the synthesized answer is grounded: it must mention known
facts that can only come from the actual rows or chunks.

Requires: semaflow_db running, ANTHROPIC_API_KEY set (router=Haiku,
SQL node=Haiku, synthesizer=Sonnet).

Run from repo root: python -m pytest app/orchestrator/tests/test_synthesizer.py -v -s
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


SYNTHESIZER_CASES = [
    {
        # Synthesizer speaks in plain business terms, not raw column tokens
        # (e.g. "health and beauty", not "health_beauty"). Assert grounding on
        # the human-readable category names the user actually sees.
        "query": "Top 5 product categories by revenue.",
        "expected_route": "sql",
        "must_mention": ["health and beauty", "watches and gifts"],
    },
    {
        "query": "What does order_status mean?",
        "expected_route": "rag",
        "must_mention": ["delivered", "canceled"],
    },
    {
        "query": "Show me the top 5 product categories by revenue and explain what those categories contain.",
        "expected_route": "hybrid",
        "must_mention": ["health and beauty", "watches and gifts", "bed"],
    },
]


@pytest.mark.parametrize("case", SYNTHESIZER_CASES)
def test_synthesizer(orchestrator: Orchestrator, case: dict) -> None:
    state = orchestrator.run(case["query"])

    assert state["route"] == case["expected_route"], (
        f"Expected route '{case['expected_route']}' for '{case['query']}', "
        f"got '{state['route']}'"
    )

    synthesis = state["synthesis"]
    assert synthesis is not None, "synthesis is None"
    answer = synthesis["answer"]
    assert isinstance(answer, str) and answer.strip(), "answer is empty"

    # Print the full answer for spot-checking voice and grounding.
    print(f"\n{'='*70}\nQUERY: {case['query']}\nROUTE: {state['route']} | "
          f"sources: {synthesis['sources_used']}\n{'-'*70}\n{answer}\n{'='*70}")

    lowered = answer.lower()
    for needle in case["must_mention"]:
        assert needle.lower() in lowered, (
            f"Expected '{needle}' in answer for '{case['query']}'. Answer: {answer}"
        )

    assert state["errors"] == [], f"errors not empty: {state['errors']}"
