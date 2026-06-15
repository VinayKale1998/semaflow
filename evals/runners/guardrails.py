"""Guardrail eval runner (offline: no LLM, no DB).

Runs each hand-crafted adversarial SQL string in adversarial_sql.yaml through the
real guardrail (app.sql.guardrails.run) and scores whether it was rejected by
exactly its target layer, for the right reason, with the other three layers
clean. This is the trust boundary's regression check: the per-layer catch rate.

Pure functions and string parsing only. Fast (~0.03s), deterministic, runnable
anywhere the package imports.
"""
from __future__ import annotations

import logging

from app.sql.guardrails import run as run_guardrails
from app.sql.models import ResolvedSQL, SQLRequest

from evals.loader import load_adversarial_set
from evals.results_io import save_results
from evals.scorers import CaseResult, score_guardrail, summarize

logger = logging.getLogger(__name__)

_LAYERS = ("is_read_only", "schema_valid", "joins_safe", "row_limit_enforced")


def run() -> tuple[dict, list[dict]]:
    aset = load_adversarial_set()
    results: list[CaseResult] = []

    for case in aset.cases:
        # measure is a valid key but irrelevant to these checks; the SQL is
        # injected directly, bypassing the LLM and resolver.
        resolved = ResolvedSQL(
            sql=case.sql, measure="top_categories_by_revenue", parameters_applied={}
        )
        gr = run_guardrails(resolved, SQLRequest(question=case.id, max_rows=aset.max_rows))
        layer_booleans = {layer: getattr(gr, layer) for layer in _LAYERS}

        result = score_guardrail(
            case.id,
            case.fails,
            case.reason_fragments,
            passed_overall=gr.passed,
            layer_booleans=layer_booleans,
            violations=gr.violations,
        )
        results.append(result)
        logger.info("guardrail %s: passed=%s %s", case.id, result.passed, result.detail)

    summ = summarize(results)["guardrails"]
    summary = {
        "passed": summ.passed,
        "total": summ.total,
        "accuracy": summ.accuracy,
        # per-layer catch counts: how many cases targeting each layer were caught
        "by_layer": _by_layer(aset.cases, results),
    }
    case_dicts = [r.model_dump() for r in results]
    return summary, case_dicts


def _by_layer(cases, results) -> dict[str, dict]:
    res_by_id = {r.case_id: r for r in results}
    out: dict[str, dict] = {}
    for c in cases:
        bucket = out.setdefault(c.fails, {"passed": 0, "total": 0})
        bucket["total"] += 1
        if res_by_id[c.id].passed:
            bucket["passed"] += 1
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary, cases = run()
    path = save_results("guardrails", summary, cases)
    print(f"\nGuardrail eval: {summary['passed']}/{summary['total']} "
          f"({summary['accuracy']:.0%}) -> {path}")
    for layer, b in summary["by_layer"].items():
        print(f"  {layer}: {b['passed']}/{b['total']}")
    for c in cases:
        flag = "PASS" if c["passed"] else "FAIL"
        line = f"  [{flag}] {c['case_id']} expected {c['expected']}"
        if not c["passed"]:
            line += f" -- {c['detail']}"
        print(line)


if __name__ == "__main__":
    main()
