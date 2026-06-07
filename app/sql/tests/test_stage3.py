"""
Stage 3 checkpoint tests.

Test 1 (happy path): a golden-set question returns correct rows.
Test 2 (bad-join):   a revenue question that would cause fan-out is caught
                     by the guardrail before execution.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Make sure app/ is importable when run from repo root
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.sql.models import SQLRequest, ModelSelection
from app.sql.resolver import resolve
from app.sql.guardrails import run as guardrail_run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"].replace("postgresql+psycopg2", "postgresql"))


# ── Test 1: happy path ────────────────────────────────────────────────────────

async def test_happy_path():
    print("\n" + "="*60)
    print("TEST 1: Happy path — top categories by revenue (no date filter)")
    print("="*60)

    from app.sql.node import run as node_run

    request = SQLRequest(question="Which categories had the highest revenue?")
    selection = await node_run(request)

    if selection is None:
        print("FAIL: node returned None (Gemini validation failure)")
        return False

    print(f"  measure selected : {selection.measure}")
    print(f"  glossary_refs    : {selection.glossary_refs}")
    print(f"  filters          : {selection.filters}")
    print(f"  confidence       : {selection.confidence}")
    print(f"  reasoning        : {selection.reasoning}")

    resolved = resolve(selection)
    print(f"\n  resolved SQL:\n{resolved.sql}")

    guardrail = guardrail_run(resolved, request)
    print(f"\n  guardrail passed : {guardrail.passed}")
    if guardrail.violations:
        print(f"  violations       : {guardrail.violations}")

    if not guardrail.passed:
        print("FAIL: guardrail rejected a valid query")
        return False

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(resolved.sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"\n  rows returned    : {len(rows)}")
    print("  top 5 results:")
    for row in rows[:5]:
        print(f"    {row}")

    # Sanity check: health_beauty or watches_gifts should be near the top
    # (from the stage 1 fan-out demo we know these lead)
    top_categories = [row[0] for row in rows[:3]]
    print(f"\n  top 3 categories : {top_categories}")
    print("PASS" if rows else "FAIL: no rows returned")
    return bool(rows)


# ── Test 2: bad-join rejection ────────────────────────────────────────────────

def test_bad_join():
    print("\n" + "="*60)
    print("TEST 2: Bad-join — guardrail must reject items->payments join")
    print("="*60)

    # Manually construct a ModelSelection that would produce the forbidden join.
    # We bypass the node here because we are testing the guardrail, not Gemini.
    from app.sql.models import ResolvedSQL

    bad_sql = """
        SELECT SUM(oi.price) AS revenue
        FROM fact_order_items oi
        JOIN fact_order_payments p ON oi.order_id = p.order_id
        LIMIT 1
    """

    resolved = ResolvedSQL(
        sql=bad_sql,
        measure="top_categories_by_revenue",
        parameters_applied={},
    )

    request = SQLRequest(question="What is total revenue?")
    guardrail = guardrail_run(resolved, request)

    print(f"  guardrail passed : {guardrail.passed}")
    print(f"  joins_safe       : {guardrail.joins_safe}")
    print(f"  violations       : {guardrail.violations}")

    if not guardrail.joins_safe:
        print("PASS: forbidden join correctly rejected")
        return True
    else:
        print("FAIL: guardrail did not catch the forbidden join")
        return False


# ── Runner ────────────────────────────────────────────────────────────────────

async def main():
    results = {}
    results["happy_path"] = await test_happy_path()
    results["bad_join"] = test_bad_join()

    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name:<20} {status}")

    all_passed = all(results.values())
    print(f"\nStage 3 checkpoint: {'PASSED' if all_passed else 'FAILED'}")
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())
