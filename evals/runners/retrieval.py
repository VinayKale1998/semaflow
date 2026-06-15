"""Retrieval hit-rate eval runner (local transformer models + pgvector; no LLM API).

Runs the real hybrid Retriever over every question that names an expected source
(rag_positive and hybrid_positive) and scores whether the expected document lands
in the top-k. Reports hit-rate@k and mean reciprocal rank.

Out-of-scope (rag_oos) questions are excluded here on purpose: they have no
expected source because the corpus does not cover them. Their correct behavior is
a hedge, scored by the hedge-calibration runner, not a retrieval miss.

Needs the DB up (pgvector). No Anthropic calls: embeddings, BM25, and the
cross-encoder are all local. The Retriever loads two transformer models and the
BM25 index once at init.
"""
from __future__ import annotations

import logging

from app.rag.retriever import Retriever

from evals.loader import load_eval_cases
from evals.results_io import save_results
from evals.scorers import retrieval_summary, score_retrieval

logger = logging.getLogger(__name__)

TOP_K = 5  # matches the orchestrator's retrieve(top_k=5)


def _dedupe_preserve_order(sources: list[str]) -> list[str]:
    """Collapse multiple chunks from the same doc so rank reflects the first
    appearance of each distinct source."""
    seen: set[str] = set()
    out: list[str] = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def run() -> tuple[dict, list[dict]]:
    cases = [c for c in load_eval_cases() if c.expected_sources]
    retriever = Retriever()
    scores = []
    case_dicts: list[dict] = []

    for case in cases:
        chunks = retriever.retrieve(case.text, top_k=TOP_K, doc_type=None)
        retrieved = _dedupe_preserve_order([c.source for c in chunks])
        score = score_retrieval(case.id, case.expected_sources, retrieved)
        scores.append(score)
        case_dicts.append(
            {
                "case_id": case.id,
                "category": case.category,
                "passed": score.hit,
                "rank": score.rank,
                "reciprocal_rank": score.reciprocal_rank,
                "expected_sources": score.expected_sources,
                "retrieved_sources": retrieved,
            }
        )
        logger.info(
            "[%s] %s rank=%s expected=%s",
            "HIT" if score.hit else "MISS", case.id, score.rank, score.expected_sources,
        )

    summ = retrieval_summary(scores)
    summary = {
        "passed": sum(1 for s in scores if s.hit),
        "total": len(scores),
        "accuracy": summ["hit_rate"],
        "hit_rate": summ["hit_rate"],
        "mrr": summ["mrr"],
        "top_k": TOP_K,
    }
    return summary, case_dicts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary, cases = run()
    path = save_results("retrieval", summary, cases)
    print(f"\nRetrieval eval: {summary['passed']}/{summary['total']} hit@{summary['top_k']} "
          f"({summary['hit_rate']:.0%}), MRR={summary['mrr']:.3f} -> {path}")
    for c in cases:
        if not c["passed"]:
            print(f"  [MISS] {c['case_id']} ({c['category']}) expected {c['expected_sources']} "
                  f"got {c['retrieved_sources']}")


if __name__ == "__main__":
    main()
