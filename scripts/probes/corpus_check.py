"""Retrieval-only probe.

For each (label, query) pair prints the top-3 sources, sections, and reranker
scores straight from the Retriever, bypassing the graph. Used to inspect
whether a first-pass query MISSES a doc that a reformulation RECOVERS, i.e.
the category-token-blurring failure mode (Collision-cluster sections under-
ranked by natural-language queries, surfaced by Portuguese-token rewrites).

Run from repo root: .venv/bin/python scripts/probes/corpus_check.py
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

# Run from anywhere: put repo root on sys.path, load its .env.
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
load_dotenv(_ROOT / ".env")

from app.rag.retriever import Retriever

# (label, query) pairs. For each we want to see top-3 sources, to judge
# whether first-pass MISSES a doc that a reformulation RECOVERS.
probes = [
    ("q7 first-pass", "How are damaged items handled when the seller is at fault?"),
    ("q7 reformulated", "seller liability compliance damaged item fault listing accuracy"),
    # Alt A: category collision cluster (the documented BM25/token failure)
    ("altA first-pass", "Where should bath towels and bedsheets be categorized?"),
    ("altA reformulated", "cama_mesa_banho home_comfort bedding towels bath linens category"),
    # Alt B: english-name gap
    ("altB first-pass", "Why do some product categories have no English name?"),
    ("altB reformulated", "dim_category_translation product_category_name_english missing untranslated"),
    # Alt C: furniture boundary (uses furniture vocab, answer keyed on collision)
    ("altC first-pass", "Should a decorative vase be listed under furniture or housewares?"),
    ("altC reformulated", "moveis_decoracao furniture_decor utilidades_domesticas housewares boundary collision"),
]

r = Retriever()
for label, q in probes:
    print("\n==== [%s] %s" % (label, q))
    for c in r.retrieve(q, top_k=3):
        print("  %-42s | %-30s | rr=%.3f" % (c.source, str(c.section), c.reranker_score))
