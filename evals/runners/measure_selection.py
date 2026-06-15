"""Measure-selection eval runner (LLM: Claude Haiku; no DB).

Scores the SQL half of the trust boundary: given a question, does the node select
the right governed measure (and the right glossary refs), and does it correctly
REFUSE when no measure fits?

Runs node.run per SQL/hybrid/OOS question and applies the same confidence gate the
pipeline uses (pipeline.MEASURE_CONFIDENCE_THRESHOLD), imported here so the two
cannot drift. A selection below the gate is treated as a refusal, exactly as
run_sql_pipeline now does. Execution is NOT run here: this dimension is about the
selection decision, and end-to-end execution of the four positive measures is
already proven by app/sql/tests/test_pipeline.py.

Three sub-scores:
  measure_selection : right measure on positives, correct refusal (None) on OOS
  glossary          : right glossary refs (positives that use glossary)
  pipeline_status   : success vs no_measure_matched (the refusal decision)
"""
from __future__ import annotations

import asyncio
import logging

from app.sql.models import SQLRequest
from app.sql.node import run as node_run
from app.sql.pipeline import MEASURE_CONFIDENCE_THRESHOLD

from evals.loader import load_eval_cases
from evals.results_io import save_results
from evals.scorers import score_glossary, score_measure, score_status, summarize

logger = logging.getLogger(__name__)


async def _select(question: str):
    return await node_run(SQLRequest(question=question))


def run() -> tuple[dict, list[dict]]:
    cases = [c for c in load_eval_cases() if c.has_sql]
    results = []
    case_dicts: list[dict] = []

    for case in cases:
        sel = asyncio.run(_select(case.text))
        raw_measure = sel.measure if sel else None
        raw_conf = sel.confidence if sel else None
        gated_out = sel is not None and sel.confidence < MEASURE_CONFIDENCE_THRESHOLD

        # Apply the pipeline's gate: a low-confidence pick is a refusal.
        if sel is None or gated_out:
            measure = None
            glossary: list[str] = []
            status = "no_measure_matched"
        else:
            measure = sel.measure
            glossary = sel.glossary_refs
            status = "success"

        m = score_measure(case.id, case.expected_measure, measure)
        s = score_status(case.id, case.expected_status or "success", status)
        results.extend([m, s])

        record = {
            "case_id": case.id,
            "category": case.category,
            "measure_passed": m.passed,
            "status_passed": s.passed,
            "expected_measure": case.expected_measure,
            "selected_measure": measure,
            "raw_measure": raw_measure,         # what the model picked before the gate
            "raw_confidence": raw_conf,
            "gated_out": gated_out,             # gate converted a pick into a refusal
            "expected_status": case.expected_status or "success",
            "actual_status": status,
        }

        # Glossary only matters for positives that declared expected glossary refs.
        if case.expected_measure is not None:
            g = score_glossary(case.id, case.expected_glossary, glossary)
            results.append(g)
            record["glossary_passed"] = g.passed
            record["glossary_detail"] = g.detail

        case_dicts.append(record)
        logger.info(
            "[%s] %s raw=%s conf=%s -> measure=%s status=%s",
            "PASS" if (m.passed and s.passed) else "FAIL",
            case.id, raw_measure, raw_conf, measure, status,
        )

    summ = summarize(results)
    summary = {
        dim: {"passed": s.passed, "total": s.total, "accuracy": s.accuracy}
        for dim, s in summ.items()
    }
    summary["gate_threshold"] = MEASURE_CONFIDENCE_THRESHOLD
    summary["refusals_via_gate"] = sum(1 for c in case_dicts if c["gated_out"])
    return summary, case_dicts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary, cases = run()
    path = save_results("measure_selection", summary, cases)
    print(f"\nMeasure-selection eval -> {path}")
    for dim in ("measure_selection", "pipeline_status", "glossary"):
        if dim in summary:
            d = summary[dim]
            print(f"  {dim}: {d['passed']}/{d['total']} ({d['accuracy']:.0%})")
    print(f"  gate threshold: {summary['gate_threshold']}, "
          f"refusals via gate: {summary['refusals_via_gate']}")
    for c in cases:
        fails = []
        if not c["measure_passed"]:
            fails.append(f"measure exp={c['expected_measure']} got={c['selected_measure']}")
        if not c["status_passed"]:
            fails.append(f"status exp={c['expected_status']} got={c['actual_status']}")
        if c.get("glossary_passed") is False:
            fails.append(f"glossary {c['glossary_detail']}")
        if fails:
            print(f"  [FAIL] {c['case_id']} ({c['category']}): " + "; ".join(fails))


if __name__ == "__main__":
    main()
