"""Hedge-demo reliability check.

Runs each candidate hedge question through the full graph N times and reports
confidence + revision count per run. A good hedge-demo question must FIRE
(rev_count >= 1) AND terminate low (stay a hedge) on every run. This is the
probe that exposed crypto's instability (its reformulation pulls the
payment-types chunk and recovers above the gate on some runs) versus
q7-damaged's consistency.

RE-RUN THIS after ANY change to the reviewer prompt or confidence gate: the
scores it reports are exactly what the recalibration moves.

Run from repo root: .venv/bin/python scripts/probes/hedge_reliability.py
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

# Reliability check for the hedge-demo pick. Run each candidate N times,
# report conf + rev_count. "Fires" = rev_count >= 1 (conf < 0.7 gate).
candidates = [
    ("q7", "How are damaged items handled when the seller is at fault?"),
    ("crypto", "What is Olist's policy on cryptocurrency payments?"),
]
N = 3

o = Orchestrator()
for label, q in candidates:
    print("\n==== [%s] %s" % (label, q))
    for i in range(N):
        s = o.run(q)
        fired = s["revision_count"] >= 1
        print("  run %d: route=%s conf=%.2f rev_count=%d fired=%s" % (
            i + 1, s["route"], s["confidence"], s["revision_count"], fired))
