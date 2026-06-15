"""Hedge-calibration eval runner (LLM: full Orchestrator.run; most expensive).

Measures whether the confidence gate is well-calibrated end-to-end: resolving
questions must clear the 0.7 gate without a revision, and unanswerable questions
must trip it. This is the RAG/hybrid half of the trust boundary (the SQL half is
the measure-confidence gate scored by measure_selection.py).

Robust gate metric. The orchestrator only returns the FINAL state, and a hedge
case can occasionally recover on its one revision (the crypto question is the
known-unstable example: its reformulation pulls the payment-types chunk). So
"did the gate fire" is read as:

    gate_fired = revision_count >= 1  OR  final_confidence < 0.7

A revision happening at all means first-pass confidence was below the gate. This
captures the gate decision whether or not the case later recovered, so the metric
does not flicker red on a legitimate recovery.

Runs a balanced set: all rag_oos (should hedge) plus a sample of resolving
rag/hybrid questions (should not). Needs DB up (retrieval + hybrid SQL).
"""
from __future__ import annotations

import logging

from app.orchestrator.graph import Orchestrator

from evals.loader import load_eval_cases
from evals.results_io import save_results
from evals.scorers import CONFIDENCE_GATE, CaseResult, summarize

logger = logging.getLogger(__name__)

# Resolving cases to confirm the gate does NOT fire on answerable questions.
# A mix of rag and hybrid routes; kept small because each run is a full graph
# pass (router + retrieve + synthesize + review, + a revision loop on hedges).
_RESOLVING_SAMPLE = {"r1", "r4", "r6", "h1", "h3"}


def _select_cases():
    cases = {c.id: c for c in load_eval_cases()}
    hedge = [c for c in cases.values() if c.category == "rag_oos"]
    resolving = [cases[i] for i in sorted(_RESOLVING_SAMPLE)]
    return resolving + hedge


def run() -> tuple[dict, list[dict]]:
    cases = _select_cases()
    orch = Orchestrator()
    results = []
    case_dicts: list[dict] = []

    for case in cases:
        state = orch.run(case.text)
        confidence = state.get("confidence", 0.0)
        revision_count = state.get("revision_count", 0)
        grounded = state.get("grounded", False)
        route = state.get("route")

        gate_fired = revision_count >= 1 or confidence < CONFIDENCE_GATE
        passed = gate_fired == case.expects_hedge
        recovered = revision_count >= 1 and confidence >= CONFIDENCE_GATE

        results.append(
            CaseResult(
                dimension="hedge_calibration",
                case_id=case.id,
                passed=passed,
                expected=f"hedge={case.expects_hedge}",
                actual=f"gate_fired={gate_fired}",
                detail=f"conf={confidence:.2f} revisions={revision_count} recovered={recovered}",
            )
        )
        case_dicts.append(
            {
                "case_id": case.id,
                "category": case.category,
                "passed": passed,
                "expects_hedge": case.expects_hedge,
                "gate_fired": gate_fired,
                "confidence": confidence,
                "revision_count": revision_count,
                "recovered": recovered,
                "grounded": grounded,
                "route": route,
            }
        )
        logger.info(
            "[%s] %s expects_hedge=%s gate_fired=%s conf=%.2f rev=%d recovered=%s",
            "PASS" if passed else "FAIL", case.id, case.expects_hedge,
            gate_fired, confidence, revision_count, recovered,
        )

    summ = summarize(results)["hedge_calibration"]
    summary = {
        "passed": summ.passed,
        "total": summ.total,
        "accuracy": summ.accuracy,
        "gate": CONFIDENCE_GATE,
        "resolving_pass": sum(
            1 for c in case_dicts if not c["expects_hedge"] and c["passed"]
        ),
        "resolving_total": sum(1 for c in case_dicts if not c["expects_hedge"]),
        "hedge_pass": sum(1 for c in case_dicts if c["expects_hedge"] and c["passed"]),
        "hedge_total": sum(1 for c in case_dicts if c["expects_hedge"]),
        "recoveries": sum(1 for c in case_dicts if c["recovered"]),
    }
    return summary, case_dicts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary, cases = run()
    path = save_results("hedge_calibration", summary, cases)
    print(f"\nHedge-calibration eval: {summary['passed']}/{summary['total']} "
          f"({summary['accuracy']:.0%}) gate={summary['gate']} -> {path}")
    print(f"  resolving (must clear gate): {summary['resolving_pass']}/{summary['resolving_total']}")
    print(f"  unanswerable (must hedge):   {summary['hedge_pass']}/{summary['hedge_total']}")
    print(f"  recoveries on revision: {summary['recoveries']}")
    for c in cases:
        flag = "PASS" if c["passed"] else "FAIL"
        print(f"  [{flag}] {c['case_id']} ({c['category']}) expects_hedge={c['expects_hedge']} "
              f"conf={c['confidence']:.2f} rev={c['revision_count']} recovered={c['recovered']}")


if __name__ == "__main__":
    main()
