"""Routing eval runner (LLM: Claude Haiku, one classify call per question).

Runs the real Router over every question in the eval set and scores the chosen
route against expected_route. Out-of-scope questions are included on purpose:
their route label is the SHAPE of the question (a freight query is sql-shaped, a
crypto-policy query is rag-shaped), so the router should still classify them
correctly even though the system will later refuse or hedge. Routing accuracy and
feasibility are deliberately separate dimensions.

Also emits a confusion matrix so route-pair confusions (the usual one is
sql<->hybrid) are visible, not just a single accuracy number.
"""
from __future__ import annotations

import logging

from app.orchestrator.router import Router

from evals.loader import load_eval_cases
from evals.results_io import save_results
from evals.scorers import score_route, summarize

logger = logging.getLogger(__name__)

_ROUTES = ("sql", "rag", "hybrid")


def run() -> tuple[dict, list[dict]]:
    cases = load_eval_cases()
    router = Router()
    results = []
    case_dicts: list[dict] = []
    # confusion[expected][actual] = count
    confusion = {e: {a: 0 for a in _ROUTES} for e in _ROUTES}

    for case in cases:
        decision = router.classify(case.text)
        result = score_route(case.id, case.expected_route, decision.route)
        results.append(result)
        confusion[case.expected_route][decision.route] += 1
        case_dicts.append(
            {
                **result.model_dump(),
                "category": case.category,
                "route_confidence": decision.confidence,
                "reason": decision.reason,
            }
        )
        flag = "PASS" if result.passed else "FAIL"
        logger.info(
            "[%s] %s expected=%s got=%s conf=%.2f",
            flag, case.id, case.expected_route, decision.route, decision.confidence,
        )

    summ = summarize(results)["routing"]
    summary = {
        "passed": summ.passed,
        "total": summ.total,
        "accuracy": summ.accuracy,
        "confusion": confusion,
        # accuracy split by whether the question is in-scope or out-of-scope:
        # proves the router classifies shape even for questions it must refuse.
        "by_scope": _by_scope(cases, results),
    }
    return summary, case_dicts


def _by_scope(cases, results) -> dict[str, dict]:
    res_by_id = {r.case_id: r for r in results}
    out = {"in_scope": {"passed": 0, "total": 0}, "out_of_scope": {"passed": 0, "total": 0}}
    for c in cases:
        key = "out_of_scope" if c.category in ("sql_oos", "rag_oos") else "in_scope"
        out[key]["total"] += 1
        if res_by_id[c.id].passed:
            out[key]["passed"] += 1
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary, cases = run()
    path = save_results("routing", summary, cases)
    print(f"\nRouting eval: {summary['passed']}/{summary['total']} "
          f"({summary['accuracy']:.0%}) -> {path}")
    print(f"  in-scope: {summary['by_scope']['in_scope']['passed']}/"
          f"{summary['by_scope']['in_scope']['total']}  "
          f"out-of-scope: {summary['by_scope']['out_of_scope']['passed']}/"
          f"{summary['by_scope']['out_of_scope']['total']}")
    print("  confusion (rows=expected, cols=actual):")
    print("            " + "  ".join(f"{a:>6}" for a in _ROUTES))
    for e in _ROUTES:
        print(f"    {e:>6}  " + "  ".join(f"{summary['confusion'][e][a]:>6}" for a in _ROUTES))
    for c in cases:
        if not c["passed"]:
            print(f"  [FAIL] {c['case_id']} ({c['category']}) expected {c['expected']} "
                  f"got {c['actual']} conf={c['route_confidence']:.2f}")


if __name__ == "__main__":
    main()
