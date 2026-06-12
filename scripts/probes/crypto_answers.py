"""Crypto-question answer capture.

Runs the cryptocurrency-policy question through the full graph 3 times and
prints the FULL final answer plus confidence each time. Companion to
hedge_reliability.py: that one shows the scores swing, this one shows WHY (the
answer text changes run to run, sometimes a bare 'not covered' hedge,
sometimes one that lists the real payment types and reads as resolved).

Run from repo root: .venv/bin/python scripts/probes/crypto_answers.py
"""
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv

# Run from anywhere: put repo root on sys.path, load its .env.
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")

logging.disable(logging.INFO)

from app.orchestrator.graph import Orchestrator

q = "What is Olist's policy on cryptocurrency payments?"
o = Orchestrator()
for i in range(3):
    s = o.run(q)
    print("\n========== RUN %d ==========" % (i + 1))
    print("conf=%.2f  grounded=%s  rev_count=%d" % (
        s["confidence"], s["grounded"], s["revision_count"]))
    print("revised_query=%r" % s["revised_query"])
    ans = (s["synthesis"] or {}).get("answer", "(none)")
    print("FINAL ANSWER:\n%s" % ans)
