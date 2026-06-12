"""Smoke the four UI sample queries through Orchestrator.run and print the
fields the Streamlit UI reads. Confirms route shape, SQL/RAG content presence,
trust-layer fields, and (for the hedge demo) that the revision loop fires.

    .venv/bin/python scripts/probes/ui_smoke.py
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv(str(Path(__file__).resolve().parents[2] / ".env"))

from app.orchestrator.graph import Orchestrator

QUERIES = {
    "SQL": "Show me the top 5 product categories by revenue",
    "RAG": "What does order_status mean and what are its possible values?",
    "Hybrid": "What is the average order value by state, and what does customer_state mean?",
    "Hedge demo": "How are damaged items handled when the seller is at fault?",
}

orch = Orchestrator()
for label, q in QUERIES.items():
    s = orch.run(q)
    sql = s.get("sql_result")
    sql_status = sql.get("status") if sql else None
    sql_rows = len(sql["response"]["rows"]) if sql and sql.get("response") else 0
    chunks = s.get("rag_chunks") or []
    syn = s.get("synthesis") or {}
    print(f"\n=== {label}: {q}")
    print(f"  route={s['route']} route_conf={s['route_confidence']:.2f}")
    print(f"  sql_status={sql_status} sql_rows={sql_rows} chunks={len(chunks)}")
    print(f"  has_sql={syn.get('has_sql')} has_rag={syn.get('has_rag')} sources={syn.get('sources_used')}")
    print(f"  grounded={s['grounded']} confidence={s['confidence']:.2f} revision_count={s['revision_count']}")
    print(f"  errors={s['errors']}")
    print(f"  answer: {syn.get('answer','')[:160]!r}")
