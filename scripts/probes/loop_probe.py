"""End-to-end orchestrator probe.

Runs a fixed 9-query set through the full graph and prints, per query: the
route, the reviewer verdict (grounded + confidence), the revision count, the
proposed revised query, and the answer. Used to validate that the loop fires
on low-confidence answers, reformulates, and terminates, and that resolving
answers stay above the confidence gate.

Run from repo root: .venv/bin/python scripts/probes/loop_probe.py
"""
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv

# Run from anywhere: put repo root on sys.path, load its .env.
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")

logging.disable(logging.INFO)  # quiet the chatty node logs

from app.orchestrator.graph import Orchestrator

queries = [
    ("baseline-rag", "What does order_status mean?"),
    ("baseline-sql", "Top 5 product categories by revenue"),
    ("altC-vase", "Should a decorative vase be listed under furniture or housewares?"),
    ("altA-towels", "Where should bath towels and bedsheets be categorized?"),
    ("q7-hedge", "How are damaged items handled when the seller is at fault?"),
    ("unanswerable", "What is Olist's policy on cryptocurrency payments?"),
    ("distinct-shoppers", "How do I count the number of distinct shoppers who ever bought something?"),
    ("seller-coords", "Are the seller location coordinates exact street addresses?"),
    ("category-no-english", "Why do some product categories show up with no English label?"),
]

o = Orchestrator()
for label, q in queries:
    s = o.run(q)
    print("\n==== [%s] %s" % (label, q))
    print("  route=%s grounded=%s conf=%.2f rev_count=%d" % (
        s["route"], s["grounded"], s["confidence"], s["revision_count"]))
    print("  revised_query=%r" % s["revised_query"])
    print("  reasoning=%s" % s["review_reasoning"][:200])
    ans = (s["synthesis"] or {}).get("answer", "(none)")
    print("  answer: %s" % ans[:240].replace("\n", " "))
    if s["errors"]:
        print("  ERRORS:", s["errors"])
